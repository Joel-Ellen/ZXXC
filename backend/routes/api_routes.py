"""
AI Learning Assistant - API Routes
FastAPI路由 - 所有API端点

Route Groups:
- /api/auth/*      认证
- /api/profile/*   学习画像
- /api/learning/*  学习路径
- /api/resources/* 资源生成
- /api/tutoring/*  智能辅导
- /api/evaluation/* 学习评估
- /api/agents/*    多智能体状态
- /api/knowledge/* 知识库管理
"""
import json
import uuid
import asyncio
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from models.database import get_db, User, StudentProfile, LearningPath, LearningTask, \
    GeneratedResource, ConversationHistory, QuizRecord, EvaluationReport
from models.schemas import *
from services.llm_service import get_llm_service, ContentFilter, get_hallucination_checker
from services.rag_service import get_rag_service
from agents.orchestrator import get_orchestrator
from utils.security import (
    hash_password, verify_password, create_access_token, decode_access_token,
    get_rate_limiter, get_prompt_defense,
)
from config import COURSE_CONFIG, LLM_PROVIDER

# Create router
router = APIRouter(prefix="/api")

# ============================================================
# Dependencies
# ============================================================
async def get_current_user(
    authorization: str = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current authenticated user from JWT token"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.split(" ")[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # Query user from database
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


# ============================================================
# Auth Routes
# ============================================================
@router.post("/auth/register", response_model=APIResponse)
async def register(req: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register new user"""
    from sqlalchemy import select

    # Check existing user
    result = await db.execute(select(User).where(
        (User.username == req.username) | (User.email == req.email)
    ))
    if result.scalar_one_or_none():
        return APIResponse(success=False, message="Username or email already exists")

    # Create user
    user = User(
        id=str(uuid.uuid4()),
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
    )
    db.add(user)
    await db.commit()

    # Create empty profile
    profile = StudentProfile(user_id=user.id)
    db.add(profile)
    await db.commit()

    token = create_access_token({"sub": user.id, "username": user.username})

    return APIResponse(
        success=True,
        message="Registration successful",
        data={
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "created_at": user.created_at.isoformat(),
            }
        }
    )


@router.post("/auth/login", response_model=APIResponse)
async def login(req: UserLogin, db: AsyncSession = Depends(get_db)):
    """User login"""
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.password_hash):
        return APIResponse(success=False, message="Invalid username or password")

    token = create_access_token({"sub": user.id, "username": user.username})

    return APIResponse(
        success=True,
        message="Login successful",
        data={
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "created_at": user.created_at.isoformat(),
            }
        }
    )


# ============================================================
# Profile Routes (Conversational Profile Building)
# ============================================================
@router.post("/profile/build", response_model=APIResponse)
async def build_profile(
    req: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Build/update student profile through conversation.
    This is the CORE innovation: dialogue-based profile building.
    """
    # Security check
    prompt_defense = get_prompt_defense()
    is_injection, reason = prompt_defense.detect_injection(req.message)
    if is_injection:
        return APIResponse(success=False, message=f"Content rejected: {reason}")

    # Content safety
    is_safe, unsafe_reason = ContentFilter.check_content(req.message)
    if not is_safe:
        return APIResponse(success=False, message=f"Content filtered: {unsafe_reason}")

    orchestrator = get_orchestrator()
    await orchestrator.initialize()

    # Get existing profile
    from sqlalchemy import select
    result = await db.execute(select(StudentProfile).where(StudentProfile.user_id == user.id))
    profile = result.scalar_one_or_none()

    existing_profile = {}
    if profile:
        existing_profile = {
            "major": profile.major,
            "grade": profile.grade,
            "university": profile.university,
            "learning_goal": profile.learning_goal,
            "learning_habits": profile.learning_habits,
            "weekly_study_hours": profile.weekly_study_hours,
            "knowledge_level": profile.knowledge_level,
            "learning_preference": profile.learning_preference,
            "weak_points": profile.weak_points,
            "interest_direction": profile.interest_direction,
            "career_goal": profile.career_goal,
            "profile_version": profile.profile_version,
        }

    # Execute profiling
    result = await orchestrator.execute_single_agent(
        "StudentProfiler",
        {
            "mode": "extract",
            "message": req.message,
            "existing_profile": existing_profile,
        }
    )

    # Update profile in database
    profile_update = result.get("profile_update", {})
    if profile_update and profile:
        dimensions = profile_update.get("dimensions", {})
        profile.major = profile_update.get("major") or profile.major
        profile.grade = profile_update.get("grade") or profile.grade
        profile.university = profile_update.get("university") or profile.university
        profile.learning_goal = profile_update.get("learning_goal") or profile.learning_goal
        profile.weekly_study_hours = profile_update.get("weekly_study_hours") or profile.weekly_study_hours
        profile.mastered_knowledge = profile_update.get("mastered_knowledge") or profile.mastered_knowledge
        profile.major_background = dimensions.get("major_background")
        profile.knowledge_level = dimensions.get("knowledge_level")
        profile.learning_ability = dimensions.get("learning_ability")
        profile.learning_preference = dimensions.get("learning_preference")
        profile.cognitive_style = dimensions.get("cognitive_style")
        profile.weak_points = dimensions.get("weak_points")
        profile.interest_direction = dimensions.get("interest_direction")
        profile.career_goal = dimensions.get("career_goal")
        profile.profile_version = profile_update.get("profile_version", profile.profile_version + 1)
        profile.confidence_score = profile_update.get("confidence_score")
        profile.last_updated = datetime.utcnow()
        await db.commit()

    # Save conversation
    if req.session_id:
        conv = ConversationHistory(
            id=str(uuid.uuid4()),
            user_id=user.id,
            session_id=req.session_id,
            role="user",
            content=req.message,
            message_type="text",
        )
        db.add(conv)
        # Also save assistant response
        assistant_msg = ConversationHistory(
            id=str(uuid.uuid4()),
            user_id=user.id,
            session_id=req.session_id,
            role="assistant",
            content=json.dumps(result, ensure_ascii=False),
            message_type="system",
        )
        db.add(assistant_msg)
        await db.commit()

    return APIResponse(
        success=True,
        message="Profile updated",
        data={
            "profile_update": result,
            "next_question": result.get("next_question"),
            "agent_activity": orchestrator.get_all_agent_statuses(),
        }
    )


@router.get("/profile/me", response_model=APIResponse)
async def get_my_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's learning profile"""
    from sqlalchemy import select
    result = await db.execute(select(StudentProfile).where(StudentProfile.user_id == user.id))
    profile = result.scalar_one_or_none()

    if not profile:
        return APIResponse(success=False, message="Profile not found")

    return APIResponse(success=True, data={
        "id": profile.id,
        "user_id": profile.user_id,
        "major": profile.major,
        "grade": profile.grade,
        "university": profile.university,
        "learning_goal": profile.learning_goal,
        "learning_habits": profile.learning_habits,
        "weekly_study_hours": profile.weekly_study_hours,
        "dimensions": {
            "major_background": profile.major_background,
            "knowledge_level": profile.knowledge_level,
            "learning_ability": profile.learning_ability,
            "learning_preference": profile.learning_preference,
            "cognitive_style": profile.cognitive_style,
            "weak_points": profile.weak_points,
            "interest_direction": profile.interest_direction,
            "career_goal": profile.career_goal,
        },
        "mastered_knowledge": profile.mastered_knowledge,
        "profile_version": profile.profile_version,
        "confidence_score": profile.confidence_score,
        "last_updated": profile.last_updated.isoformat() if profile.last_updated else None,
    })


# ============================================================
# Learning Path Routes
# ============================================================
@router.post("/learning/generate-path", response_model=APIResponse)
async def generate_learning_path(
    req: LearningPathRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate personalized learning path"""
    orchestrator = get_orchestrator()
    await orchestrator.initialize()

    # Execute pipeline: Profile -> Knowledge Analysis -> Resource Plan
    results = await orchestrator.execute_workflow(
        "learning_path",
        {
            "course_name": req.course_name,
            "weekly_hours": req.weekly_hours,
            "duration_weeks": req.duration_weeks,
            "target_level": req.target_level,
        },
        user_id=user.id,
    )

    # Extract the learning path from ResourcePlanner result
    learning_path_data = results.get("results", {}).get("ResourcePlanner", {})

    # Save learning path to database
    if learning_path_data and "error" not in learning_path_data:
        path = LearningPath(
            id=str(uuid.uuid4()),
            user_id=user.id,
            course_name=req.course_name,
            current_stage="基础知识",
            total_weeks=req.duration_weeks,
            path_data=learning_path_data,
            roadmap_url=learning_path_data.get("roadmap_mermaid"),
        )
        db.add(path)

        # Create weekly tasks
        for stage in learning_path_data.get("stages", []):
            for week_plan in stage.get("weekly_plan", []):
                task = LearningTask(
                    id=str(uuid.uuid4()),
                    path_id=path.id,
                    week_number=week_plan.get("week", 1),
                    stage=stage.get("stage_name", ""),
                    title=week_plan.get("focus", f"Week {week_plan.get('week', 1)}"),
                    tasks=week_plan.get("tasks", []),
                )
                db.add(task)

        await db.commit()

    return APIResponse(
        success=True,
        message="Learning path generated",
        data={
            "learning_path": learning_path_data,
            "agent_workflow": orchestrator.get_agent_workflow_diagram(),
        }
    )


@router.get("/learning/my-paths", response_model=APIResponse)
async def get_my_paths(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's learning paths"""
    from sqlalchemy import select
    result = await db.execute(
        select(LearningPath).where(LearningPath.user_id == user.id)
    )
    paths = result.scalars().all()

    return APIResponse(success=True, data=[
        {
            "id": p.id,
            "course_name": p.course_name,
            "current_stage": p.current_stage,
            "total_weeks": p.total_weeks,
            "completed_weeks": p.completed_weeks,
            "created_at": p.created_at.isoformat(),
        }
        for p in paths
    ])


# ============================================================
# Resource Generation Routes
# ============================================================
@router.post("/resources/generate", response_model=APIResponse)
async def generate_resource(
    req: ResourceGenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a learning resource using the appropriate agent.
    Supports: lecture_note, ppt, mindmap, exercise, project, study_note, video_script
    """
    orchestrator = get_orchestrator()
    await orchestrator.initialize()

    # Map resource type to agent
    agent_map = {
        "lecture_note": "PPTGenerator",  # PPT agent handles markdown notes too
        "ppt": "PPTGenerator",
        "mindmap": "MindMapGenerator",
        "exercise": "QuestionGenerator",
        "project": "CodingPractice",
        "study_note": "PPTGenerator",
        "video_script": "VideoScript",
    }

    agent_name = agent_map.get(req.resource_type)
    if not agent_name:
        return APIResponse(success=False, message=f"Unsupported resource type: {req.resource_type}")

    result = await orchestrator.execute_single_agent(
        agent_name,
        {
            "topic": req.topic,
            "course_name": req.course_name,
            "difficulty": req.difficulty,
            "knowledge_points": req.knowledge_points,
            "style": req.style_preference,
        }
    )

    # Save generated resource
    resource = GeneratedResource(
        id=str(uuid.uuid4()),
        user_id=user.id,
        resource_type=req.resource_type,
        title=result.get("title", req.topic) if isinstance(result, dict) else req.topic,
        course_name=req.course_name,
        knowledge_points=req.knowledge_points,
        content=json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result),
        difficulty=req.difficulty,
        agent_generated=agent_name,
        resource_metadata=result.get("metadata") if isinstance(result, dict) else None,
    )
    db.add(resource)
    await db.commit()

    return APIResponse(
        success=True,
        message=f"{req.resource_type} generated successfully",
        data={
            "resource_id": resource.id,
            "resource_type": req.resource_type,
            "content": result,
        }
    )


@router.post("/resources/generate-all", response_model=APIResponse)
async def generate_all_resources(
    course_name: str = "人工智能",
    topic: str = "机器学习基础",
    difficulty: str = "basic",
    user: User = Depends(get_current_user),
):
    """
    Generate ALL resource types for a topic in one call.
    Uses multi-agent parallel execution.
    """
    orchestrator = get_orchestrator()
    await orchestrator.initialize()

    params = {
        "course_name": course_name,
        "topic": topic,
        "difficulty": difficulty,
    }

    # Execute full resource generation workflow
    results = await orchestrator.execute_workflow(
        "generate_all_resources",
        params,
        user_id=user.id,
    )

    return APIResponse(
        success=True,
        message="All resources generated",
        data={
            "results": results.get("results", {}),
            "agent_statuses": orchestrator.get_all_agent_statuses(),
        }
    )


@router.get("/resources/my-resources", response_model=APIResponse)
async def get_my_resources(
    resource_type: Optional[str] = None,
    course_name: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's generated resources"""
    from sqlalchemy import select, and_

    conditions = [GeneratedResource.user_id == user.id]
    if resource_type:
        conditions.append(GeneratedResource.resource_type == resource_type)
    if course_name:
        conditions.append(GeneratedResource.course_name == course_name)

    result = await db.execute(
        select(GeneratedResource).where(and_(*conditions)).order_by(GeneratedResource.created_at.desc())
    )
    resources = result.scalars().all()

    return APIResponse(success=True, data=[
        {
            "id": r.id,
            "resource_type": r.resource_type,
            "title": r.title,
            "course_name": r.course_name,
            "difficulty": r.difficulty,
            "agent_generated": r.agent_generated,
            "quality_score": r.quality_score,
            "created_at": r.created_at.isoformat(),
        }
        for r in resources
    ])


# ============================================================
# Tutoring Routes
# ============================================================
@router.post("/tutoring/ask", response_model=APIResponse)
async def ask_tutor(
    req: TutoringRequest,
    user: User = Depends(get_current_user),
):
    """Ask the AI tutor a question"""
    # Security checks
    prompt_defense = get_prompt_defense()
    is_injection, reason = prompt_defense.detect_injection(req.question)
    if is_injection:
        return APIResponse(success=False, message=f"Content rejected: {reason}")

    orchestrator = get_orchestrator()
    await orchestrator.initialize()

    result = await orchestrator.execute_single_agent(
        "LearningCoach",
        {
            "question": req.question,
            "context_type": req.context_type,
            "course_name": req.course_name,
            "code_snippet": req.code_snippet,
            "error_message": req.error_message,
        }
    )

    # Hallucination check on factual claims
    if isinstance(result, dict) and result.get("detailed_explanation"):
        checker = get_hallucination_checker()
        # Extract key claims and verify
        claims = [result.get("core_definition", "")]
        claims.extend(result.get("common_misconceptions", [])[:2])
        verification = await checker.verify_factual_claims(
            [c for c in claims if c],
            context=result.get("detailed_explanation", ""),
        )

        result["fact_check"] = verification

    return APIResponse(
        success=True,
        data={
            "tutoring_result": result,
        }
    )


@router.post("/tutoring/stream")
async def ask_tutor_stream(
    req: TutoringRequest,
):
    """Stream tutoring response (SSE)"""
    async def generate():
        orchestrator = get_orchestrator()
        await orchestrator.initialize()

        agent = orchestrator.agents.get("LearningCoach")
        if not agent:
            yield f"data: {json.dumps({'error': 'Agent not found'})}\n\n"
            return

        async for chunk in agent.chat_llm_stream(
            req.question,
            system_prompt=agent.system_prompt,
        ):
            yield f"data: {json.dumps({'content': chunk})}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ============================================================
# Evaluation Routes
# ============================================================
@router.post("/evaluation/generate-report", response_model=APIResponse)
async def generate_evaluation_report(
    req: EvaluationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate learning evaluation report"""
    orchestrator = get_orchestrator()
    await orchestrator.initialize()

    # Gather learning data from database
    from sqlalchemy import select, and_

    # Get quiz records
    result = await db.execute(
        select(QuizRecord).where(
            and_(
                QuizRecord.user_id == user.id,
                QuizRecord.course_name == req.course_name,
            )
        )
    )
    quiz_records = [
        {
            "score": q.score,
            "total_score": q.total_score,
            "feedback": q.feedback,
            "created_at": q.created_at.isoformat(),
        }
        for q in result.scalars().all()
    ]

    # Execute evaluation workflow
    eval_result = await orchestrator.execute_workflow(
        "evaluation",
        {
            "course_name": req.course_name,
            "period_days": req.period_days,
            "quiz_records": quiz_records,
            "study_logs": [],  # TODO: integrate study time tracking
        },
        user_id=user.id,
    )

    # Save report
    report_data = eval_result.get("results", {}).get("Evaluation", {})
    if report_data:
        metrics = report_data.get("metrics", {})
        report = EvaluationReport(
            id=str(uuid.uuid4()),
            user_id=user.id,
            course_name=req.course_name,
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow(),
            metrics=metrics,
            current_level=report_data.get("current_level", {}).get("level", "unknown"),
            weak_areas=report_data.get("weak_areas", []),
            strengths=report_data.get("strengths", []),
            suggestions=report_data.get("suggestions", []),
            next_plan=report_data.get("next_stage_plan", {}),
            report_content=report_data.get("report_content", ""),
        )
        db.add(report)
        await db.commit()

    return APIResponse(
        success=True,
        data={"report": report_data}
    )


# ============================================================
# Agent Status Routes (for UI display)
# ============================================================
@router.get("/agents/status", response_model=APIResponse)
async def get_agents_status():
    """Get all agents' current status for UI display"""
    orchestrator = get_orchestrator()
    await orchestrator.initialize()

    return APIResponse(
        success=True,
        data={
            "agents": orchestrator.get_all_agent_statuses(),
            "orchestrator": orchestrator.get_orchestrator_status(),
            "workflow_diagram": orchestrator.get_agent_workflow_diagram(),
        }
    )


@router.get("/agents/workflow-diagram", response_model=APIResponse)
async def get_workflow_diagram():
    """Get Mermaid agent workflow diagram"""
    orchestrator = get_orchestrator()
    await orchestrator.initialize()

    return APIResponse(
        success=True,
        data={"mermaid": orchestrator.get_agent_workflow_diagram()}
    )


# ============================================================
# Knowledge Base & RAG Routes
# ============================================================
@router.post("/knowledge/ingest", response_model=APIResponse)
async def ingest_knowledge(
    course_name: str,
    documents: List[dict],
):
    """Ingest course materials into RAG knowledge base"""
    rag = get_rag_service()
    count = await rag.ingest_documents(course_name, documents)

    return APIResponse(
        success=True,
        message=f"Ingested {count} chunks for {course_name}",
        data={"chunks_ingested": count}
    )


@router.post("/knowledge/search", response_model=APIResponse)
async def search_knowledge(
    course_name: str,
    query: str,
    top_k: int = 5,
):
    """Search knowledge base with hybrid search"""
    rag = get_rag_service()
    results = await rag.hybrid_search(course_name, query, top_k)

    return APIResponse(success=True, data={"results": results})


@router.get("/knowledge/stats", response_model=APIResponse)
async def knowledge_stats(course_name: str):
    """Get knowledge base statistics"""
    rag = get_rag_service()
    stats = rag.get_collection_stats(course_name)

    return APIResponse(success=True, data=stats)


# ============================================================
# WebSocket for Real-time Agent Communication
# ============================================================
@router.websocket("/ws/agent-stream")
async def agent_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time agent status streaming.
    Frontend can connect to see live agent activity.
    """
    await websocket.accept()
    orchestrator = get_orchestrator()
    await orchestrator.initialize()

    try:
        while True:
            # Send current agent statuses
            status_data = {
                "type": "agent_status",
                "agents": orchestrator.get_all_agent_statuses(),
                "orchestrator": orchestrator.get_orchestrator_status(),
                "timestamp": datetime.utcnow().isoformat(),
            }
            await websocket.send_json(status_data)

            # Wait before next update
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


# ============================================================
# Health Check
# ============================================================
@router.get("/health", response_model=APIResponse)
async def health_check():
    """System health check"""
    return APIResponse(
        success=True,
        message="AI Learning Assistant is running",
        data={
            "version": "1.0.0",
            "llm_provider": LLM_PROVIDER,
            "courses": COURSE_CONFIG["available_courses"],
            "timestamp": datetime.utcnow().isoformat(),
        }
    )
