"""
AI Learning Assistant - Main Server Entry Point
多智能体个性化学习资源生成系统 - FastAPI主入口
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from config import SERVER_CONFIG
from models.database import init_db
from routes.api_routes import router as api_router

logger.add("logs/ai_learning_assistant.log", rotation="10 MB", retention="7 days", level="INFO")
Path("logs").mkdir(exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("AI Learning Assistant - Multi-Agent System Starting...")
    logger.info("=" * 60)
    await init_db()
    logger.info("Database initialized")
    try:
        from agents.orchestrator import get_orchestrator
        orchestrator = get_orchestrator()
        await orchestrator.initialize()
        logger.info(f"Multi-agent orchestrator ready: {len(orchestrator.agents)} agents")
    except Exception as e:
        logger.warning(f"Orchestrator pre-init skipped: {e}")
    logger.info(f"Server starting on {SERVER_CONFIG['host']}:{SERVER_CONFIG['port']}")
    yield
    logger.info("Shutting down...")

app = FastAPI(
    title="AI Learning Assistant",
    description="基于大模型的个性化资源生成与学习多智能体系统",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(api_router)

@app.get("/")
async def root():
    return {"name": "AI Learning Assistant", "version": "1.0.0", "docs": "/docs", "health": "/api/health"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=SERVER_CONFIG["host"], port=SERVER_CONFIG["port"], reload=SERVER_CONFIG["debug"])
