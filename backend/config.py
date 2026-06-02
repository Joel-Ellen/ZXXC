"""
AI Learning Assistant - Global Configuration
多智能体个性化学习资源生成系统 - 全局配置
"""
import os
from pathlib import Path

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
KB_DIR = DATA_DIR / "knowledge_base"
VECTOR_DB_DIR = DATA_DIR / "vector_db"

# Ensure directories exist
for d in [DATA_DIR, KB_DIR, VECTOR_DB_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============================================================
# LLM Configuration (Multi-provider support)
# ============================================================
LLM_CONFIG = {
    # Primary: XunFei Spark (讯飞星火) - Priority for competition
    "spark": {
        "api_url": os.getenv("SPARK_API_URL", "https://spark-api-open.xf-yun.com/v1"),
        "api_key": os.getenv("SPARK_API_KEY", ""),
        "api_secret": os.getenv("SPARK_API_SECRET", ""),
        "app_id": os.getenv("SPARK_APP_ID", ""),
        "model": "spark-pro",
        "max_tokens": 4096,
        "temperature": 0.7,
    },
    # DeepSeek
    "deepseek": {
        "api_url": os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1"),
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "model": "deepseek-chat",
        "max_tokens": 4096,
        "temperature": 0.7,
    },
    # Qwen (Tongyi Qianwen)
    "qwen": {
        "api_url": os.getenv("QWEN_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "api_key": os.getenv("DASHSCOPE_API_KEY", ""),
        "model": "qwen-plus",
        "max_tokens": 4096,
        "temperature": 0.7,
    },
    # Qwen-Plus (128K context window — with overflow strategy)
    "qwen-plus": {
        "api_url": os.getenv("QWEN_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "api_key": os.getenv("DASHSCOPE_API_KEY", ""),
        "model": "qwen-plus",
        "max_tokens": 4096,
        "temperature": 0.7,
        "max_input_tokens": 128000,  # 128K context limit
        "overflow_strategy": "map_reduce",  # map_reduce | smart_truncate | sliding_window
    },
    # GPT (OpenAI compatible)
    "openai": {
        "api_url": os.getenv("OPENAI_API_URL", "https://api.openai.com/v1"),
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "model": "gpt-4o",
        "max_tokens": 4096,
        "temperature": 0.7,
    },
}

# Active LLM provider
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "qwen-plus")

# ============================================================
# Embedding Configuration
# ============================================================
EMBEDDING_CONFIG = {
    "model_name": "paraphrase-multilingual-MiniLM-L12-v2",
    "dimension": 384,
    "batch_size": 32,
    "max_seq_length": 512,
}

# ============================================================
# Vector Database Configuration (Chroma)
# ============================================================
CHROMA_CONFIG = {
    "persist_directory": str(VECTOR_DB_DIR / "chroma"),
    "collection_name": "course_knowledge",
    "distance_metric": "cosine",
}

# ============================================================
# RAG Configuration
# ============================================================
RAG_CONFIG = {
    "max_retrieval_chunks": 5,
    "similarity_threshold": 0.70,
    "max_context_tokens": 2000,
    "chunk_size": 500,
    "chunk_overlap": 100,
    "rerank_enabled": True,
    "hybrid_search_weight": 0.5,  # 0.5 = equal weight for dense + sparse
}

# ============================================================
# Database Configuration
# ============================================================
DATABASE_CONFIG = {
    "url": os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DATA_DIR}/learning_assistant.db"),
    "echo": False,
}

# ============================================================
# Redis Configuration (for caching & session)
# ============================================================
REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", 6379)),
    "db": int(os.getenv("REDIS_DB", 0)),
    "password": os.getenv("REDIS_PASSWORD", None),
    "cache_ttl": 3600,  # 1 hour default
}

# ============================================================
# Agent Configuration
# ============================================================
AGENT_CONFIG = {
    "max_concurrent_agents": 5,
    "agent_timeout": 120,  # seconds
    "memory_shared": True,
    "verbose_logging": True,
}

# ============================================================
# Security Configuration
# ============================================================
SECURITY_CONFIG = {
    "content_filter_enabled": True,
    "prompt_defense_enabled": True,
    "hallucination_check_enabled": True,
    "sensitive_keywords": [
        "违法", "暴力", "色情", "歧视", "政治敏感",
        "hack", "exploit", "attack", "illegal",
    ],
    "max_prompt_length": 4000,
    "rate_limit_per_minute": 30,
}

# ============================================================
# Learning Path Configuration
# ============================================================
LEARNING_CONFIG = {
    "stages": ["基础知识", "核心知识", "综合应用", "项目实践", "能力提升"],
    "default_weekly_hours": 10,
    "max_path_duration_weeks": 16,
    "difficulty_levels": ["入门", "基础", "进阶", "高级", "专家"],
}

# ============================================================
# Course Configuration
# ============================================================
COURSE_CONFIG = {
    "default_course": "人工智能",
    "available_courses": [
        "人工智能",
        "机器学习",
        "深度学习",
        "数据结构",
        "操作系统",
        "计算机网络",
        "大模型应用开发",
    ],
}

# ============================================================
# Server Configuration
# ============================================================
SERVER_CONFIG = {
    "host": "0.0.0.0",
    "port": int(os.getenv("PORT", 8000)),
    "debug": os.getenv("DEBUG", "true").lower() == "true",
    "cors_origins": ["*"],
}
