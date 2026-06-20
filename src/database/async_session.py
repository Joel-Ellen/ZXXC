# -*- coding: utf-8 -*-
"""
Async Session — 异步数据库会话管理
===================================

来源: backend/models/database.py (merged)
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from .models_sqlalchemy import Base

_engine = None
_async_session = None

# 从环境变量读取数据库 URL，默认使用 SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/eduagent.db")


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            DATABASE_URL,
            echo=False,
        )
    return _engine


def get_async_session():
    global _async_session
    if _async_session is None:
        engine = get_engine()
        _async_session = async_sessionmaker(engine, expire_on_commit=False)
    return _async_session


async def init_db():
    """初始化数据库表（若不存在则创建）。"""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """FastAPI 路由依赖 — 生成异步 session。"""
    session_maker = get_async_session()
    async with session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
