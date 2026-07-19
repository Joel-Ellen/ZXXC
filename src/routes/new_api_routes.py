# -*- coding: utf-8 -*-
"""
Liveness route.

``/api/health`` is the container/k8s liveness probe. All learning flows enter
through frontend/server.py -> src.application services -> orchestration runtime.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


def build_health_response() -> dict:
    return {"status": "ok"}


async def api_health(request: Request) -> JSONResponse:
    return JSONResponse(build_health_response(), headers={"Cache-Control": "no-store"})


new_routes = [
    Route("/api/health", api_health, methods=["GET"]),
]
