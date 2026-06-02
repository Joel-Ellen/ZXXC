"""
AI Learning Assistant - Base Agent Class
多智能体系统 - 基础Agent类

Provides:
- Common agent interface
- Shared memory access
- LLM interaction
- Task logging
- Inter-agent messaging
- Status reporting
"""
import json
import time
import uuid
import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger
from services.llm_service import LLMService, get_llm_service


@dataclass
class AgentMessage:
    """Message passed between agents"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: str = ""
    receiver: str = ""
    msg_type: str = "task"  # task / result / query / notification
    content: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentState:
    """Agent's current state"""
    agent_name: str
    status: str = "idle"  # idle / working / completed / error / waiting
    current_task: Optional[str] = None
    progress: float = 0.0  # 0-100
    last_active: Optional[datetime] = None
    messages_sent: int = 0
    messages_received: int = 0
    tokens_used: int = 0
    errors: List[str] = field(default_factory=list)


class BaseAgent(ABC):
    """
    Abstract base class for all agents.

    Each agent has:
    - A unique name and role
    - Access to shared memory
    - LLM service for generation
    - Message passing to other agents
    - Task logging
    """

    def __init__(
        self,
        name: str,
        role: str,
        llm_service: Optional[LLMService] = None,
        verbose: bool = True,
    ):
        self.name = name
        self.role = role
        self.llm = llm_service or get_llm_service()
        self.verbose = verbose

        # Agent state
        self.state = AgentState(agent_name=name)

        # Shared memory reference (set by orchestrator)
        self.shared_memory: Dict[str, Any] = {}

        # Message handlers
        self._message_handlers: Dict[str, Callable] = {}

        # Output queue (read by orchestrator for inter-agent communication)
        self.output_queue: List[AgentMessage] = []

        # System prompt template (overridden by subclasses)
        self.system_prompt = f"你是{self.role}，名为{self.name}。"

        self._log(f"Agent initialized: {name} ({role})")

    def _log(self, message: str, level: str = "INFO"):
        """Internal logging with agent prefix"""
        if self.verbose:
            try:
                logger.log(level.upper(), f"[{self.name}] {message}")
            except ValueError:
                logger.info(f"[{self.name}] {message}")

    def update_shared_memory(self, key: str, value: Any):
        """Write to shared memory"""
        self.shared_memory[key] = value
        self._log(f"Shared memory updated: {key}")

    def read_shared_memory(self, key: str, default: Any = None) -> Any:
        """Read from shared memory"""
        return self.shared_memory.get(key, default)

    def send_message(
        self,
        receiver: str,
        content: Any,
        msg_type: str = "task",
        metadata: Optional[Dict] = None,
    ):
        """Send a message to another agent"""
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
        """Receive and process a message from another agent"""
        self.state.messages_received += 1

        # Call registered handler if any
        handler = self._message_handlers.get(message.msg_type)
        if handler:
            return handler(message)

        # Default: store in state
        self._log(f"Message received from {message.sender}: {message.msg_type}")
        return message.content

    def register_handler(self, msg_type: str, handler: Callable):
        """Register a message handler"""
        self._message_handlers[msg_type] = handler

    async def chat_llm(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> Dict[str, Any]:
        """Convenience method for LLM chat"""
        messages = [
            {"role": "system", "content": system_prompt or self.system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        self.state.status = "working"
        self.state.last_active = datetime.utcnow()

        start_time = time.time()
        result = await self.llm.chat(messages, temperature=temperature, json_mode=json_mode)
        elapsed = time.time() - start_time

        self.state.tokens_used += result.get("usage", {}).get("total_tokens", 0)
        self.state.status = "idle"
        self.state.last_active = datetime.utcnow()

        return result

    async def chat_llm_stream(self, user_prompt: str, system_prompt: Optional[str] = None):
        """Convenience method for streaming LLM chat"""
        messages = [
            {"role": "system", "content": system_prompt or self.system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        self.state.status = "working"
        self.state.last_active = datetime.utcnow()

        async for chunk in self.llm.chat_stream(messages):
            yield chunk

        self.state.status = "idle"
        self.state.last_active = datetime.utcnow()

    def set_progress(self, progress: float):
        """Update agent progress (0-100)"""
        self.state.progress = min(100, max(0, progress))

    @abstractmethod
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main execution method. Each agent implements its core logic here.

        Args:
            task: Task parameters

        Returns:
            Task results
        """
        pass

    def get_status(self) -> Dict[str, Any]:
        """Get current agent status (for UI display)"""
        return {
            "agent_name": self.state.agent_name,
            "status": self.state.status,
            "current_task": self.state.current_task,
            "progress": self.state.progress,
            "last_active": self.state.last_active.isoformat() if self.state.last_active else None,
            "tokens_used": self.state.tokens_used,
        }

    def __repr__(self):
        return f"<Agent: {self.name} ({self.role}) [{self.state.status}]>"
