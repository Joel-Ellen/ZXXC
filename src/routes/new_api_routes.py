# -*- coding: utf-8 -*-
"""
Legacy/internal API routes.

These routes are retained for testing and debugging. Official learning flows now
enter through frontend/server.py -> src.application services -> orchestration runtime.

The old synchronous BaseAgent chain (profile build / learning-path / resource
generation / evaluation report) was removed together with the BaseAgent family;
the canonical session API owns those flows now.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


def build_health_response() -> dict:
    return {"status": "ok"}


async def api_health(request: Request) -> JSONResponse:
    return JSONResponse(build_health_response(), headers={"Cache-Control": "no-store"})


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


async def api_retired_agent_chain(request: Request) -> JSONResponse:
    """Tombstone the removed synchronous BaseAgent-chain endpoints.

    Keeps a deterministic 404 (instead of a static-mount 405) so stale
    callers cannot fall through to the SPA or silently revive the chain.
    """
    return JSONResponse({"detail": "NOT_FOUND"}, status_code=404, headers={"Cache-Control": "no-store"})


new_routes = [
    Route("/api/health", api_health, methods=["GET"]),
    Route("/api/profile/me", api_profile_me, methods=["GET"]),
    Route("/api/profile/build", api_retired_agent_chain, methods=["POST"]),
    Route("/api/learning/generate-path", api_retired_agent_chain, methods=["POST"]),
    Route("/api/evaluation/generate-report", api_retired_agent_chain, methods=["POST"]),
    Route("/api/agents/status", api_agents_status, methods=["GET"]),
    Route("/api/knowledge/search", api_knowledge_search, methods=["POST"]),
    Route("/api/knowledge/stats", api_knowledge_stats, methods=["GET"]),
]
