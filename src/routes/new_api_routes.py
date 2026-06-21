# -*- coding: utf-8 -*-
"""
Additional API routes with unified agent creation.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .content_normalizer import (
    build_evaluation_response,
    build_learning_path_response,
    build_profile_response,
    normalize_agent_output,
)
from src.agents import (
    AssessmentReporterNode,
    CodingPracticeAgent,
    KnowledgeAnalysisAgent,
    MindMapGeneratorAgent,
    PPTGeneratorAgent,
    QuestionGeneratorAgent,
    ResourcePlannerAgent,
    StudentProfilerAgent,
    VideoScriptAgent,
)
from src.agents.agent_factory import build_agent, get_default_llm


def build_health_response() -> dict:
    return {"status": "ok", "version": "2.1.0", "docs": "/docs"}


async def api_health(request: Request) -> JSONResponse:
    import os

    api_key = (
        os.environ.get("DASHSCOPE_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    return JSONResponse(
        {
            "status": "ok",
            "version": "2.1.0",
            "llm_available": bool(api_key),
            "provider": os.environ.get("LLM_PROVIDER", "auto") if api_key else "none",
        }
    )


async def api_profile_build(request: Request) -> JSONResponse:
    try:
        from src.auth.prompt_defense import get_prompt_defense

        body = await request.json()
        message = body.get("message", "")

        defense = get_prompt_defense()
        is_injection, reason = defense.detect_injection(message)
        if is_injection:
            return JSONResponse({"error": reason}, status_code=400)

        agent = build_agent(StudentProfilerAgent)
        result = await agent.execute(
            {
                "mode": body.get("mode", "extract"),
                "message": message,
                "conversation_history": body.get("conversation_history", []),
                "existing_profile": body.get("existing_profile", {}),
            }
        )
        return JSONResponse(build_profile_response(result))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_profile_me(request: Request) -> JSONResponse:
    try:
        return JSONResponse(
            {
                "content_type": "structured",
                "content_subtype": "profile",
                "profile": {},
            }
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_generate_learning_path(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        course_name = body.get("course_name", "")

        profiler = build_agent(StudentProfilerAgent)
        knowledge = build_agent(KnowledgeAnalysisAgent)
        planner = build_agent(ResourcePlannerAgent)

        profile_result = await profiler.execute(
            {
                "mode": "extract",
                "message": body.get("profile_message", ""),
                "existing_profile": body.get("existing_profile", {}),
            }
        )

        knowledge.shared_memory["student_profile"] = profile_result.get("profile_update", {})
        knowledge_result = await knowledge.execute(
            {
                "mode": "full_analysis",
                "course_name": course_name,
                "topic": body.get("topic", ""),
            }
        )

        planner.shared_memory["student_profile"] = profile_result.get("profile_update", {})
        planner.shared_memory["knowledge_structure"] = knowledge_result
        path_result = await planner.execute({"course_name": course_name})

        return JSONResponse(build_learning_path_response(path_result))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def _resource_agent_map():
    return {
        "ppt": PPTGeneratorAgent,
        "lecture_note": PPTGeneratorAgent,
        "study_note": PPTGeneratorAgent,
        "quiz": QuestionGeneratorAgent,
        "exercise": QuestionGeneratorAgent,
        "mindmap": MindMapGeneratorAgent,
        "coding": CodingPracticeAgent,
        "project": CodingPracticeAgent,
        "video": VideoScriptAgent,
        "video_script": VideoScriptAgent,
        "animation_script": VideoScriptAgent,
    }


def _resource_normalizer_name(resource_type: str) -> str:
    mapping = {
        "exercise": "quiz",
        "lecture_note": "ppt",
        "study_note": "ppt",
        "project": "coding",
        "video_script": "video",
        "animation_script": "video",
    }
    return mapping.get(resource_type, resource_type)


async def api_generate_resource(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        resource_type = body.get("resource_type", "ppt")
        agent_cls = _resource_agent_map().get(resource_type, PPTGeneratorAgent)
        agent = build_agent(agent_cls)

        result = await agent.execute(
            {
                "topic": body.get("topic", ""),
                "course_name": body.get("course_name", ""),
                "difficulty": body.get("difficulty", "basic"),
                "style": body.get("style", "visual"),
                "slide_count": body.get("slide_count", 15),
                "question_count": body.get("question_count", 10),
                "question_types": body.get("question_types", ["choice", "true_false", "short_answer"]),
                "language": body.get("language", "python"),
                "count": body.get("count", 3),
                "duration_minutes": body.get("duration_minutes", 15),
            }
        )

        normalized = normalize_agent_output(result, _resource_normalizer_name(resource_type))
        return JSONResponse(normalized)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_generate_all_resources(request: Request) -> JSONResponse:
    try:
        import asyncio

        body = await request.json()
        topic = body.get("topic", "")
        course_name = body.get("course_name", "")

        agents = {
            "ppt": build_agent(PPTGeneratorAgent),
            "quiz": build_agent(QuestionGeneratorAgent),
            "mindmap": build_agent(MindMapGeneratorAgent),
            "coding": build_agent(CodingPracticeAgent),
            "video": build_agent(VideoScriptAgent),
        }

        async def run_agent(name, agent):
            try:
                result = await agent.execute(
                    {
                        "topic": topic,
                        "course_name": course_name,
                        "difficulty": body.get("difficulty", "basic"),
                    }
                )
                return name, normalize_agent_output(result, name)
            except Exception as e:
                return name, {"error": str(e)}

        tasks = [run_agent(name, agent) for name, agent in agents.items()]
        results = dict(await asyncio.gather(*tasks))
        return JSONResponse({"resources": results, "topic": topic})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_generate_evaluation(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        llm = get_default_llm()
        agent = AssessmentReporterNode(llm_client=llm)
        result = agent.generate_llm_report(
            radar=[0.7, 0.6, 0.75, 0.5, 0.8],
            a_mix=0.65,
            strategy="STANDARD_PATH",
            course_name=body.get("course_name", ""),
            study_time=body.get("study_time", 0),
            completed_tasks=body.get("completed_tasks", 0),
        )
        return JSONResponse(
            build_evaluation_response({"report": result, "report_markdown": result.get("report_markdown", "")})
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_agents_status(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "agents": [],
            "orchestrator_status": "idle",
            "workflow_mermaid": "graph TD\n  A[Ready] --> B[Prompt Registry + Unified Resource Generation]",
        }
    )


async def api_knowledge_search(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        query = body.get("query", "")
        top_k = body.get("top_k", 5)

        try:
            from src.vector.elasticsearch_knowledge_base import ElasticsearchKnowledgeBaseClient
            import os

            es = ElasticsearchKnowledgeBaseClient(
                hosts=[os.getenv("ES_HOSTS", "http://127.0.0.1:9200")],
                user=os.getenv("ES_USER", ""),
                password=os.getenv("ES_PASSWORD", ""),
            )
            results = es.hybrid_search(query, top_k=top_k)
            return JSONResponse({"results": results, "query": query})
        except Exception:
            return JSONResponse({"results": [], "query": query, "note": "ES not available"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_knowledge_stats(request: Request) -> JSONResponse:
    try:
        import os

        if os.getenv("ES_HOSTS"):
            return JSONResponse({"status": "connected", "index": "knowledge_base"})
        return JSONResponse({"status": "not_configured"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


new_routes = [
    Route("/api/health", api_health, methods=["GET"]),
    Route("/api/profile/build", api_profile_build, methods=["POST"]),
    Route("/api/profile/me", api_profile_me, methods=["GET"]),
    Route("/api/learning/generate-path", api_generate_learning_path, methods=["POST"]),
    Route("/api/resources/generate", api_generate_resource, methods=["POST"]),
    Route("/api/resources/generate-all", api_generate_all_resources, methods=["POST"]),
    Route("/api/evaluation/generate-report", api_generate_evaluation, methods=["POST"]),
    Route("/api/agents/status", api_agents_status, methods=["GET"]),
    Route("/api/knowledge/search", api_knowledge_search, methods=["POST"]),
    Route("/api/knowledge/stats", api_knowledge_stats, methods=["GET"]),
]
