# -*- coding: utf-8 -*-
"""
BaseAgent — 多智能体基类（合并自 backend/）
============================================

提供通用接口：
  - LLM 对话（chat_llm / chat_llm_stream）
  - 并发安全的共享内存读写
  - 消息传递（send_message / receive_message）
  - 状态跟踪与任务日志
  - 进度报告

来源: backend/agents/base_agent.py (merged, adapted for src.llm.LLMClientV2)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

try:
    from loguru import logger
except ModuleNotFoundError:
    logger = logging.getLogger(__name__)


@dataclass
class AgentMessage:
    """Agent 间传递的消息。"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: str = ""
    receiver: str = ""
    msg_type: str = "task"  # task / result / query / notification
    content: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class BaseAgentState:
    """Agent 当前状态。"""
    agent_name: str = ""
    status: str = "idle"  # idle / working / completed / error / waiting
    current_task: Optional[str] = None
    progress: float = 0.0
    last_active: Optional[datetime] = None
    messages_sent: int = 0
    messages_received: int = 0
    tokens_used: int = 0
    errors: List[str] = field(default_factory=list)


class BaseAgent(ABC):
    """所有 Agent 的抽象基类。

    每个 Agent 有：
      - 唯一名称和角色
      - 共享内存访问（并发安全）
      - LLM 服务用于内容生成
      - 向其他 Agent 发送消息
      - 任务日志
    """

    def __init__(
        self,
        name: str,
        role: str,
        llm_client = None,
        verbose: bool = True,
    ):
        self.name = name
        self.role = role
        self.llm = llm_client  # LLMClientV2 或兼容实例
        self.verbose = verbose

        self.state = BaseAgentState(agent_name=name)
        self.shared_memory: Dict[str, Any] = {}
        self._memory_lock: asyncio.Lock = asyncio.Lock()
        self._message_handlers: Dict[str, Callable] = {}
        self.output_queue: List[AgentMessage] = []
        self.system_prompt = f"你是{self.role}，名为{self.name}。"

        self._log(f"Agent initialized: {name} ({role})")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(self, message: str, level: str = "INFO"):
        if self.verbose:
            try:
                logger.log(level.upper(), f"[{self.name}] {message}")
            except (TypeError, ValueError):
                log_method = getattr(logger, level.lower(), logger.info)
                log_method(f"[{self.name}] {message}")

    # ------------------------------------------------------------------
    # Shared Memory (并发安全)
    # ------------------------------------------------------------------

    async def update_shared_memory(self, key: str, value: Any):
        async with self._memory_lock:
            self.shared_memory[key] = value
        self._log(f"Shared memory updated: {key}")

    async def read_shared_memory(self, key: str, default: Any = None) -> Any:
        async with self._memory_lock:
            return self.shared_memory.get(key, default)

    def read_shared_memory_sync(self, key: str, default: Any = None) -> Any:
        return self.shared_memory.get(key, default)

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    def send_message(
        self,
        receiver: str,
        content: Any,
        msg_type: str = "task",
        metadata: Optional[Dict] = None,
    ):
        msg = AgentMessage(
            sender=self.name,
            receiver=receiver,
            msg_type=msg_type,
            content=content,
            metadata=metadata or {},
        )
        self.output_queue.append(msg)
        self.state.messages_sent += 1
        self._log(f"Message sent -> {receiver}: {msg_type}")

    def receive_message(self, message: AgentMessage):
        self.state.messages_received += 1
        handler = self._message_handlers.get(message.msg_type)
        if handler:
            return handler(message)
        self._log(f"Message received from {message.sender}: {message.msg_type}")
        return message.content

    def register_handler(self, msg_type: str, handler: Callable):
        self._message_handlers[msg_type] = handler

    # ------------------------------------------------------------------
    # LLM Chat
    # ------------------------------------------------------------------

    async def chat_llm(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> Dict[str, Any]:
        """便捷 LLM 对话方法。"""
        messages = [
            {"role": "system", "content": system_prompt or self.system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        self.state.status = "working"
        self.state.last_active = datetime.utcnow()

        if self.llm is None:
            return {"content": "[LLM not available]", "usage": {}}

        # LLMClientV2 的 chat 方法是 async
        if hasattr(self.llm, 'chat') and asyncio.iscoroutinefunction(self.llm.chat):
            result = await self.llm.chat(messages, temperature=temperature, json_mode=json_mode)
        else:
            # 兼容同步 LLMClient
            result = {"content": self.llm.chat(messages), "usage": {}}

        self.state.tokens_used += result.get("usage", {}).get("total_tokens", 0)
        self.state.status = "idle"
        self.state.last_active = datetime.utcnow()

        return result

    async def chat_llm_stream(self, user_prompt: str, system_prompt: Optional[str] = None):
        """便捷流式 LLM 对话方法。"""
        messages = [
            {"role": "system", "content": system_prompt or self.system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        self.state.status = "working"
        self.state.last_active = datetime.utcnow()

        if self.llm and hasattr(self.llm, 'chat_stream'):
            async for chunk in self.llm.chat_stream(messages):
                yield chunk

        self.state.status = "idle"
        self.state.last_active = datetime.utcnow()

    # ------------------------------------------------------------------
    # Progress & Status
    # ------------------------------------------------------------------

    def set_progress(self, progress: float):
        self.state.progress = min(100, max(0, progress))

    def get_status(self) -> Dict[str, Any]:
        return {
            "agent_name": self.state.agent_name,
            "status": self.state.status,
            "current_task": self.state.current_task,
            "progress": self.state.progress,
            "last_active": self.state.last_active.isoformat() if self.state.last_active else None,
            "tokens_used": self.state.tokens_used,
        }

    # ------------------------------------------------------------------
    # Abstract execute
    # ------------------------------------------------------------------

    @abstractmethod
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """主执行方法。每个 Agent 在这里实现核心逻辑。"""
        pass

    def __repr__(self):
        return f"<Agent: {self.name} ({self.role}) [{self.state.status}]>"
