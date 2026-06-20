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
    if not authorization:
        logger.warning("[Auth] 401 — No Authorization header in request")
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not authorization.startswith("Bearer "):
        logger.warning(f"[Auth] 401 — Authorization header malformed: {authorization[:30]}...")
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.split(" ")[1]
    payload = decode_access_token(token)
    if not payload:
        logger.warning("[Auth] 401 — Token decode failed (expired or invalid signature)")
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        logger.warning("[Auth] 401 — Token payload missing 'sub' field")
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # Query user from database — wrapped in try/except for resilience
    from sqlalchemy import select, exc as sa_exc
    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
    except sa_exc.OperationalError as e:
        logger.error(f"[Auth] Database operational error: {e}")
        raise HTTPException(status_code=503, detail="Database temporarily unavailable")
    except sa_exc.TimeoutError as e:
        logger.error(f"[Auth] Database query timed out: {e}")
        raise HTTPException(status_code=503, detail="Request timed out, please retry")
    except Exception as e:
        logger.error(f"[Auth] Unexpected database error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="Internal authentication error")

    if not user:
        logger.warning(f"[Auth] 401 — User not found in DB: {user_id}")
        raise HTTPException(status_code=401, detail="User not found")

    logger.debug(f"[Auth] User authenticated: {user.username} ({user.id})")
    return user


# ============================================================
# Content Normalization Helpers
# 将 Agent 原始输出统一规范化为 MarkdownContent 或 StructuredXxx，
# 消除所有 `json.dumps(...) if isinstance(...) else str(...)` 模糊处理。
# ============================================================

def _ensure_markdown(raw: Any) -> str:
    """Ensure raw agent output becomes a clean Markdown string."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        # If the dict has a 'full_markdown' or 'markdown' field, return that
        for key in ("full_markdown", "markdown", "report_content", "content"):
            if key in raw and isinstance(raw[key], str) and len(raw[key]) > 50:
                return raw[key]
        # Otherwise pretty-print the dict as a Markdown code block
        return "```json\n" + json.dumps(raw, ensure_ascii=False, indent=2) + "\n```"
    return str(raw)


def _build_markdown_response(raw: Any, title: Optional[str] = None) -> Dict[str, Any]:
    """Build a standardized MarkdownContent response dict."""
    md = _ensure_markdown(raw)
    result: Dict[str, Any] = {
        "content_type": "markdown",
        "markdown": md,
    }
    if title:
        result["title"] = title
    if isinstance(raw, dict):
        # Pass through relevant metadata keys
        meta = {}
        for k in ("course_name", "topic", "difficulty", "slide_count",
                   "estimated_duration_minutes", "usage", "model"):
            if k in raw:
                meta[k] = raw[k]
        if meta:
            result["metadata"] = meta
    return result


def _build_mindmap_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Build a standardized StructuredMindMap response dict."""
    mermaid_code = raw.get("mermaid_code", "")
    # Parse Mermaid mindmap to build a simple recursive node tree
    root_node = _parse_mermaid_to_tree(mermaid_code, raw.get("topic", "中心主题"))

    return {
        "content_type": "structured",
        "content_subtype": "mindmap",
        "title": raw.get("title", ""),
        "topic": raw.get("topic", ""),
        "mermaid_code": mermaid_code,
        "root": root_node,
        "key_concepts": raw.get("key_concepts", []),
        "total_nodes": raw.get("structure_summary", {}).get("total_nodes", 0) if isinstance(raw.get("structure_summary"), dict) else 0,
        "max_depth": raw.get("structure_summary", {}).get("max_depth", 3) if isinstance(raw.get("structure_summary"), dict) else 3,
        "usage_tips": raw.get("usage_tips", ""),
        "metadata": {
            "course_name": raw.get("course_name", ""),
        },
    }


def _parse_mermaid_to_tree(mermaid: str, root_label: str) -> Optional[Dict[str, Any]]:
    """
    Parse Mermaid mindmap syntax into a recursive MindMapNode tree.
    Mermaid mindmap uses indentation (2 spaces per level) to denote hierarchy.

    Example input:
        mindmap
          root((中心主题))
            分支A
              子节点A1
              子节点A2
            分支B
              子节点B1

    Returns: {"id": "root", "label": "中心主题", "children": [...]}
    """
    if not mermaid:
        return {"id": "root", "label": root_label, "children": []}

    lines = mermaid.strip().split("\n")
    # Skip the "mindmap" header line if present
    if lines and lines[0].strip() == "mindmap":
        lines = lines[1:]

    # Build a stack-based tree parser
    import re
    node_id_counter = [0]

    def new_id() -> str:
        node_id_counter[0] += 1
        return f"node_{node_id_counter[0]}"

    root: Dict[str, Any] = {"id": new_id(), "label": root_label, "children": []}
    stack: List[Dict[str, Any]] = [root]  # stack[0] = root, stack[1] = level-1 parent, etc.

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Calculate indent level (2 spaces = 1 level in Mermaid mindmap)
        indent = len(line) - len(line.lstrip(" "))
        level = indent // 2 + 1  # level 1 = first indent under root

        # Clean node label: remove Mermaid syntax markers
        label = re.sub(r'[\(\)\[\]\{\}]+', '', stripped).strip()
        # Remove icon emojis in the form ::icon(...)
        label = re.sub(r'::icon\([^)]*\)', '', label).strip()
        if not label:
            continue

        node: Dict[str, Any] = {"id": new_id(), "label": label, "children": []}

        # Pop stack until we find the parent at the correct level
        while len(stack) > level:
            stack.pop()
        # Ensure stack has enough entries for this level
        while len(stack) < level:
            # If missing intermediate levels, use the last node as parent
            if len(stack) >= 2:
                stack.append(stack[-1])
            else:
                stack.append(root)

        parent = stack[level - 1] if level - 1 < len(stack) else root
        parent["children"].append(node)
        # Push this node as the potential parent for the next line
        if len(stack) <= level:
            stack.append(node)
        else:
            stack[level] = node

        # Trim stack to current level + 1
        stack = stack[:level + 1]

    return root


def _build_quiz_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Build a standardized StructuredQuiz response dict."""
    quiz_meta = raw.get("quiz_metadata", {}) if isinstance(raw.get("quiz_metadata"), dict) else {}
    questions_raw = raw.get("questions", []) if isinstance(raw.get("questions"), list) else []

    typed_questions = []
    for q in questions_raw:
        if not isinstance(q, dict):
            continue
        typed_questions.append({
            "id": q.get("id", f"Q{len(typed_questions)+1:03d}"),
            "type": q.get("type", "choice"),
            "difficulty": q.get("difficulty", "basic"),
            "points": float(q.get("points", 10)),
            "question_text": q.get("question", ""),
            "options": q.get("options"),
            "correct_answer": q.get("correct_answer"),
            "explanation": q.get("explanation"),
            "knowledge_tested": q.get("knowledge_tested", []) if isinstance(q.get("knowledge_tested"), list) else [],
            "hints": q.get("hints", []) if isinstance(q.get("hints"), list) else [],
        })

    return {
        "content_type": "structured",
        "content_subtype": "quiz",
        "title": quiz_meta.get("knowledge_point", raw.get("topic", "")),
        "course_name": quiz_meta.get("course_name", raw.get("course_name", "")),
        "knowledge_point": quiz_meta.get("knowledge_point", ""),
        "total_questions": quiz_meta.get("total_questions", len(typed_questions)),
        "total_score": float(quiz_meta.get("total_score", 100)),
        "estimated_time_minutes": int(quiz_meta.get("estimated_time_minutes", 30)),
        "difficulty": quiz_meta.get("difficulty", "basic"),
        "questions": typed_questions,
        "metadata": {
            "quiz_meta": quiz_meta,
        },
    }


def _build_learning_path_response(raw: Dict[str, Any], roadmap_mermaid: Optional[str] = None) -> Dict[str, Any]:
    """Build a standardized StructuredLearningPath response dict."""
    plan_overview = raw.get("plan_overview", {}) if isinstance(raw.get("plan_overview"), dict) else {}
    stages_raw = raw.get("stages", []) if isinstance(raw.get("stages"), list) else []

    typed_stages = []
    for s in stages_raw:
        if not isinstance(s, dict):
            continue
        weekly_plan_raw = s.get("weekly_plan", []) if isinstance(s.get("weekly_plan"), list) else []
        typed_weekly = []
        for wp in weekly_plan_raw:
            if isinstance(wp, dict):
                typed_weekly.append({
                    "week": wp.get("week", 0),
                    "focus": wp.get("focus", ""),
                    "tasks": wp.get("tasks", []) if isinstance(wp.get("tasks"), list) else [],
                    "milestone": wp.get("milestone"),
                })

        typed_stages.append({
            "stage_id": s.get("stage_id", 0),
            "stage_name": s.get("stage_name", ""),
            "weeks": s.get("weeks", ""),
            "description": s.get("description", ""),
            "goals": s.get("goals", []) if isinstance(s.get("goals"), list) else [],
            "topics": s.get("topics", []) if isinstance(s.get("topics"), list) else [],
            "weekly_plan": typed_weekly,
            "assessment": s.get("assessment"),
        })

    # Build overview markdown from plan_overview
    overview_parts = [
        f"## {raw.get('course_name', '')} 学习路径",
        "",
        f"- **总周数**：{plan_overview.get('total_weeks', 0)} 周",
        f"- **每周学时**：{plan_overview.get('weekly_hours', 0)} 小时",
        f"- **目标水平**：{plan_overview.get('target_level', '')}",
        f"- **起始水平**：{plan_overview.get('start_level', '')}",
        f"- **学习策略**：{plan_overview.get('learning_strategy', '')}",
    ]

    return {
        "content_type": "structured",
        "content_subtype": "learning_path",
        "course_name": raw.get("course_name", ""),
        "total_weeks": plan_overview.get("total_weeks", 0),
        "target_level": plan_overview.get("target_level", "advanced"),
        "overview_markdown": "\n".join(overview_parts),
        "stages": typed_stages,
        "roadmap_mermaid": roadmap_mermaid or raw.get("roadmap_mermaid"),
        "personalized_tips": raw.get("personalized_tips", []) if isinstance(raw.get("personalized_tips"), list) else [],
        "metadata": {
            "resource_strategy": raw.get("resource_recommendation_strategy"),
        },
    }


def _build_tutoring_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a standardized TutoringStructuredResponse dict.

    The LearningCoach agent returns various answer_types. This normalizer
    always produces a `markdown_body` field (for the main readable content)
    plus type-specific fields for frontend component rendering.
    """
    answer_type = raw.get("answer_type", "general_tutoring")

    # Build a rich markdown body from all text fields
    md_parts = []

    if raw.get("core_definition"):
        md_parts.append(f"### 💡 核心定义\n\n{raw['core_definition']}")

    if raw.get("analogy"):
        md_parts.append(f"### 🔗 生活化类比\n\n{raw['analogy']}")

    if raw.get("detailed_explanation"):
        md_parts.append(f"### 📖 详细解释\n\n{raw['detailed_explanation']}")

    if raw.get("response"):
        md_parts.append(raw["response"])

    if raw.get("answer"):
        md_parts.append(raw["answer"])

    if raw.get("analysis"):
        md_parts.append(f"### 📊 学习分析\n\n{raw['analysis']}")

    if raw.get("error_analysis"):
        md_parts.append(f"### 🔍 错误分析\n\n{raw['error_analysis']}")

    if raw.get("root_cause"):
        md_parts.append(f"> **根本原因**：{raw['root_cause']}")

    if raw.get("fix_guidance"):
        md_parts.append(f"### 🛠️ 修复引导\n\n{raw['fix_guidance']}")

    if raw.get("review_strategy"):
        md_parts.append(f"### 📝 复习策略\n\n{raw['review_strategy']}")

    if raw.get("cheat_sheet"):
        md_parts.append(f"### 📋 速记要点\n\n{raw['cheat_sheet']}")

    # Collect hints, mistakes, extension questions into the body
    hints = raw.get("hints") if isinstance(raw.get("hints"), list) else []
    if hints:
        md_parts.append("### 💭 提示\n" + "\n".join(f"- {h}" for h in hints))

    mistakes = raw.get("common_mistakes") if isinstance(raw.get("common_mistakes"), list) else []
    if mistakes:
        md_parts.append("### ⚠️ 常见误区\n" + "\n".join(f"- {m}" for m in mistakes))

    ext_qs = raw.get("extension_questions") if isinstance(raw.get("extension_questions"), list) else []
    if ext_qs:
        md_parts.append("### 🤔 延伸思考\n" + "\n".join(f"- {q}" for q in ext_qs))

    advice_list = raw.get("advice") if isinstance(raw.get("advice"), list) else []
    if advice_list:
        md_parts.append("### 🎯 学习建议\n" + "\n".join(f"- {a}" for a in advice_list))

    key_topics = raw.get("key_topics") if isinstance(raw.get("key_topics"), list) else []
    if key_topics:
        md_parts.append("### ⭐ 重点主题\n" + "\n".join(f"- {t}" for t in key_topics))

    suggestions = raw.get("suggestions") if isinstance(raw.get("suggestions"), list) else []
    if suggestions:
        md_parts.append("### 📌 建议\n" + "\n".join(f"- {s}" for s in suggestions))

    fallback = raw.get("content", "")
    if not md_parts and isinstance(fallback, str):
        md_parts.append(fallback)

    if not md_parts:
        md_parts.append(json.dumps(raw, ensure_ascii=False, indent=2))

    markdown_body = "\n\n".join(md_parts)

    return {
        "content_type": "structured",
        "content_subtype": "tutoring",
        "answer_type": answer_type,
        "markdown_body": markdown_body,
        "diagram": raw.get("diagram"),
        "code_example": raw.get("code_example") or raw.get("improved_code_snippet"),
        "hints": hints,
        "common_mistakes": mistakes,
        "extension_questions": ext_qs,
        "references": raw.get("references") if isinstance(raw.get("references"), list) else [],
        "metadata": {
            "course_name": raw.get("course_name", ""),
            "fact_check": raw.get("fact_check"),
            "learning_tip": raw.get("learning_tip"),
        },
    }


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
        # Save assistant response — serialize result as clean JSON
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

    # ── Standardized response ──
    # summary_markdown: Markdown text for chat bubble rendering
    # dimensions: structured profile dimensions for the profile card
    summary_md = result.get("summary", "")
    if not summary_md and result.get("next_question"):
        summary_md = f"💬 {result['next_question']}"

    return APIResponse(
        success=True,
        message="Profile updated",
        data={
            "content_type": "structured",
            "content_subtype": "profile_update",
            "summary_markdown": summary_md,
            "next_question": result.get("next_question"),
            "profile_update": result.get("profile_update", {}),
            "missing_info": result.get("missing_info", []),
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

    # ── Standardized structured learning path response ──
    normalized_path = _build_learning_path_response(
        learning_path_data,
        roadmap_mermaid=learning_path_data.get("roadmap_mermaid"),
    )

    return APIResponse(
        success=True,
        message="Learning path generated",
        data={
            "learning_path": normalized_path,
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

    # ── Classify & normalize output ──
    resource_type = req.resource_type
    title = result.get("title", req.topic) if isinstance(result, dict) else req.topic

    if resource_type == "mindmap":
        normalized = _build_mindmap_response(result) if isinstance(result, dict) else _build_markdown_response(result, title)
    elif resource_type in ("exercise",):
        normalized = _build_quiz_response(result) if isinstance(result, dict) else _build_markdown_response(result, title)
    elif resource_type in ("lecture_note", "ppt", "study_note", "video_script", "project"):
        normalized = _build_markdown_response(result, title)
    else:
        normalized = _build_markdown_response(result, title)

    # Serialize for DB storage — always use clean JSON
    db_content = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)

    # Save generated resource
    resource = GeneratedResource(
        id=str(uuid.uuid4()),
        user_id=user.id,
        resource_type=resource_type,
        title=title,
        course_name=req.course_name,
        knowledge_points=req.knowledge_points,
        content=db_content,
        difficulty=req.difficulty,
        agent_generated=agent_name,
        resource_metadata=result.get("metadata") if isinstance(result, dict) else None,
    )
    db.add(resource)
    await db.commit()

    return APIResponse(
        success=True,
        message=f"{resource_type} generated successfully",
        data={
            "resource_id": resource.id,
            "resource_type": resource_type,
            "content": normalized,
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

    # ── Normalize each agent's result ──
    raw_results = results.get("results", {})
    normalized_results = {}
    for agent_name, agent_result in raw_results.items():
        if not isinstance(agent_result, dict):
            normalized_results[agent_name] = _build_markdown_response(agent_result)
            continue
        # Classify by agent type
        if agent_name == "MindMapGenerator":
            normalized_results[agent_name] = _build_mindmap_response(agent_result)
        elif agent_name == "QuestionGenerator":
            normalized_results[agent_name] = _build_quiz_response(agent_result)
        elif agent_name == "KnowledgeAnalysis":
            normalized_results[agent_name] = {
                "content_type": "structured",
                "content_subtype": "knowledge_analysis",
                "data": agent_result,
            }
        elif agent_name == "ResourcePlanner":
            normalized_results[agent_name] = _build_learning_path_response(agent_result)
        else:
            # PPTGenerator, VideoScript, CodingPractice → Markdown
            title = agent_result.get("title", "") if isinstance(agent_result, dict) else ""
            normalized_results[agent_name] = _build_markdown_response(agent_result, title)

    return APIResponse(
        success=True,
        message="All resources generated",
        data={
            "results": normalized_results,
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

    # ── Standardized tutoring response ──
    normalized = _build_tutoring_response(result) if isinstance(result, dict) else _build_markdown_response(result)

    return APIResponse(
        success=True,
        data={
            "tutoring_result": normalized,
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

    # ── Normalize evaluation report ──
    if isinstance(report_data, dict):
        report_md = report_data.get("report_content", "")
        if not report_md:
            # Fallback: build markdown summary from structured data
            lines = [f"# {report_data.get('report_metadata', {}).get('course_name', '')} 学习评估报告"]
            overall = report_data.get("report_metadata", {})
            if overall:
                lines.append(f"- **综合评级**：{overall.get('overall_grade', 'N/A')}")
                lines.append(f"- **综合评分**：{overall.get('overall_score', 'N/A')}")
            metrics = report_data.get("metrics", {})
            if metrics:
                lines.append("\n## 学习指标")
                for k, v in metrics.items():
                    lines.append(f"- **{k}**：{v}")
            report_md = "\n".join(lines)

        normalized_report = _build_markdown_response(
            {"full_markdown": report_md, "report_content": report_md,
             "title": report_data.get("report_metadata", {}).get("course_name", "") + " 评估报告"},
        )
        normalized_report["content_subtype"] = "evaluation_report"
        normalized_report["content_type"] = "structured"
        normalized_report["metrics"] = report_data.get("metrics", {})
        normalized_report["suggestions"] = report_data.get("suggestions", [])
        normalized_report["weak_areas"] = report_data.get("weak_areas", [])
        normalized_report["strengths"] = report_data.get("strengths", [])
        normalized_report["radar_chart_data"] = report_data.get("radar_chart_data")
    else:
        normalized_report = _build_markdown_response(report_data)

    return APIResponse(
        success=True,
        data={"report": normalized_report}
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
