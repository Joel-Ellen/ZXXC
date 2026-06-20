# -*- coding: utf-8 -*-
"""
New API Routes — 新增端点（合并自 backend/routes/api_routes.py）
===============================================================
"""
import json
import uuid
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .content_normalizer import (
    normalize_agent_output,
    build_mindmap_response,
    build_quiz_response,
    build_learning_path_response,
    build_tutoring_response,
    build_profile_response,
    build_evaluation_response,
)


def build_health_response() -> dict:
    return {"status": "ok", "version": "2.0.0-merged", "docs": "/docs"}


# ============================================================================
# 处理函数
# ============================================================================

async def api_health(request: Request) -> JSONResponse:
    """健康检查。"""
    import os
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    return JSONResponse({
        "status": "ok",
        "version": "2.0.0-merged",
        "llm_available": bool(api_key),
        "provider": "dashscope" if api_key else "none",
    })


async def api_profile_build(request: Request) -> JSONResponse:
    """构建学生画像（对话式）。"""
    try:
        from src.agents import StudentProfilerAgent
        from src.auth.prompt_defense import get_prompt_defense

        body = await request.json()
        message = body.get("message", "")

        # Prompt 注入检测
        defense = get_prompt_defense()
        is_injection, reason = defense.detect_injection(message)
        if is_injection:
            return JSONResponse({"error": reason}, status_code=400)

        agent = StudentProfilerAgent()
        result = await agent.execute({
            "mode": body.get("mode", "extract"),
            "message": message,
            "conversation_history": body.get("conversation_history", []),
            "existing_profile": body.get("existing_profile", {}),
        })

        from .content_normalizer import build_profile_response
        return JSONResponse(build_profile_response(result))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_profile_me(request: Request) -> JSONResponse:
    """获取当前用户画像。"""
    try:
        # 暂从内存返回 — 后续对接数据库
        return JSONResponse({
            "content_type": "structured",
            "content_subtype": "profile",
            "profile": {},
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_generate_learning_path(request: Request) -> JSONResponse:
    """生成个性化学习路径。"""
    try:
        from src.agents import StudentProfilerAgent, KnowledgeAnalysisAgent, ResourcePlannerAgent

        body = await request.json()
        course_name = body.get("course_name", "")

        profiler = StudentProfilerAgent()
        knowledge = KnowledgeAnalysisAgent()
        planner = ResourcePlannerAgent()

        # 执行分析链
        profile_result = await profiler.execute({
            "mode": "extract",
            "message": body.get("profile_message", ""),
            "existing_profile": body.get("existing_profile", {}),
        })

        knowledge_result = await knowledge.execute({
            "mode": "full_analysis",
            "course_name": course_name,
        })

        path_result = await planner.execute({
            "course_name": course_name,
        })

        from .content_normalizer import build_learning_path_response
        return JSONResponse(build_learning_path_response(path_result))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_generate_resource(request: Request) -> JSONResponse:
    """生成单个资源。"""
    try:
        from src.agents import (
            PPTGeneratorAgent, QuestionGeneratorAgent,
            MindMapGeneratorAgent, CodingPracticeAgent, VideoScriptAgent,
        )

        body = await request.json()
        resource_type = body.get("resource_type", "ppt")
        topic = body.get("topic", "")
        course_name = body.get("course_name", "")

        agent_map = {
            "ppt": PPTGeneratorAgent,
            "quiz": QuestionGeneratorAgent,
            "mindmap": MindMapGeneratorAgent,
            "coding": CodingPracticeAgent,
            "video": VideoScriptAgent,
        }

        agent_cls = agent_map.get(resource_type, PPTGeneratorAgent)
        agent = agent_cls()
        result = await agent.execute({
            "topic": topic,
            "course_name": course_name,
            "difficulty": body.get("difficulty", "basic"),
            "style": body.get("style", "visual"),
        })

        normalized = normalize_agent_output(result, resource_type)
        return JSONResponse(normalized)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_generate_all_resources(request: Request) -> JSONResponse:
    """并行生成所有类型资源。"""
    try:
        import asyncio
        from src.agents import (
            PPTGeneratorAgent, QuestionGeneratorAgent,
            MindMapGeneratorAgent, CodingPracticeAgent, VideoScriptAgent,
        )

        body = await request.json()
        topic = body.get("topic", "")
        course_name = body.get("course_name", "")

        agents = {
            "ppt": PPTGeneratorAgent(),
            "quiz": QuestionGeneratorAgent(),
            "mindmap": MindMapGeneratorAgent(),
            "coding": CodingPracticeAgent(),
            "video": VideoScriptAgent(),
        }

        async def run_agent(name, agent):
            try:
                result = await agent.execute({
                    "topic": topic,
                    "course_name": course_name,
                    "difficulty": body.get("difficulty", "basic"),
                })
                return name, normalize_agent_output(result, name)
            except Exception as e:
                return name, {"error": str(e)}

        tasks = [run_agent(name, agent) for name, agent in agents.items()]
        results = dict(await asyncio.gather(*tasks))

        return JSONResponse({"resources": results, "topic": topic})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_generate_evaluation(request: Request) -> JSONResponse:
    """生成学习评估报告。"""
    try:
        from src.agents import EvaluationAgent

        body = await request.json()
        agent = EvaluationAgent()
        result = await agent.execute({
            "course_name": body.get("course_name", ""),
            "quiz_records": body.get("quiz_records", []),
            "study_time": body.get("study_time", 0),
            "completed_tasks": body.get("completed_tasks", 0),
        })

        from .content_normalizer import build_evaluation_response
        return JSONResponse(build_evaluation_response(result))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_agents_status(request: Request) -> JSONResponse:
    """获取所有 Agent 状态。"""
    return JSONResponse({
        "agents": [],
        "orchestrator_status": "idle",
        "workflow_mermaid": "graph TD\n  A[Ready] --> B[Waiting for task]",
    })


async def api_knowledge_search(request: Request) -> JSONResponse:
    """知识库混合搜索。"""
    try:
        body = await request.json()
        query = body.get("query", "")
        top_k = body.get("top_k", 5)

        # 尝试使用 ES 知识库搜索
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
    """知识库统计信息。"""
    try:
        import os
        if os.getenv("ES_HOSTS"):
            return JSONResponse({"status": "connected", "index": "knowledge_base"})
        return JSONResponse({"status": "not_configured"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ============================================================================
# 路由列表
# ============================================================================

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
