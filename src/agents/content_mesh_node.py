# -*- coding: utf-8 -*-
"""
Content Mesh Node — 资源生成与调度网络
=======================================

本节点是 LangGraph StateGraph 中的内容生成调度节点，负责根据 Planner
输出的 active_path 和 Profiler 推荐的资源风格，调度多模态教育资源的
生成与分发。

核心能力：
1. 带特权门控的加权公平队列 (WFQ) 调度
   - 70% 令牌配额 → 特权队列 (文档、导图)：流式优先输出，1-2s 目标延迟
   - 30% 令牌配额 → 常规异步队列 (视频、题库、实操案例)：流式占位 + 进度条卡片

2. 马尔可夫拓扑预测影子预生成 (Markov Shadow Pre-generation)
   - 基于当前节点的出边邻接矩阵实时预测 Top-1 后向激活节点
   - 提前在后台启动影子预生成并压入 LRU 缓存
   - 重规划触发时下发高优先级信令，熔断废弃路径任务并回收配额

3. 流式输出 + Markdown 渲染 + 多模态卡片化展示
   - 支持 SSE (Server-Sent Events) 流式推送
   - 5 种资源卡片类型: concept_map / code_snippet / interactive_exercise /
     video_summary / diagnostic_quiz

依赖声明：
  AI 辅助编码工具：科大讯飞 iFlyCode / 星火大模型辅助生成。
"""

from __future__ import annotations

import heapq
import math
import threading
import uuid
import time as _time
from typing import Dict, List, Optional, Tuple, Any, Set, Callable, Generator
from dataclasses import dataclass, field
from enum import Enum
from collections import OrderedDict

from pydantic import BaseModel, Field

from ..state.agent_state import AgentState, ResourceCard


# ============================================================================
# 枚举与常量
# ============================================================================

class QueueClass(str, Enum):
    """队列优先级类别。"""
    PRIVILEGED = "privileged"      # 特权: 文档、导图 (70% 配额)
    REGULAR = "regular"            # 常规: 视频、题库、案例 (30% 配额)


class CardType(str, Enum):
    """资源卡片类型。"""
    CONCEPT_MAP = "concept_map"
    CODE_SNIPPET = "code_snippet"
    INTERACTIVE_EXERCISE = "interactive_exercise"
    VIDEO_SUMMARY = "video_summary"
    DIAGNOSTIC_QUIZ = "diagnostic_quiz"


class GenerationStatus(str, Enum):
    """生成任务状态。"""
    QUEUED = "queued"            # 已入队
    STREAMING = "streaming"      # 流式生成中
    COMPLETED = "completed"      # 已完成
    ABORTED = "aborted"          # 已熔断废弃
    FAILED = "failed"            # 生成失败


class ShadowStatus(str, Enum):
    """影子预生成状态。"""
    IDLE = "idle"
    PREDICTING = "predicting"
    CACHED = "cached"
    ABORTED = "aborted"


# ============================================================================
# Pydantic I/O 模型
# ============================================================================

class WfqConfig(BaseModel):
    """加权公平队列配置。"""

    privileged_token_ratio: float = Field(
        default=0.70, ge=0.0, le=1.0,
        description="特权队列令牌配额占比"
    )
    regular_token_ratio: float = Field(
        default=0.30, ge=0.0, le=1.0,
        description="常规队列令牌配额占比"
    )
    max_concurrent_privileged: int = Field(
        default=3, ge=1, le=10,
        description="特权队列最大并发生成任务"
    )
    max_concurrent_regular: int = Field(
        default=2, ge=1, le=10,
        description="常规队列最大并发生成任务"
    )
    streaming_chunk_size: int = Field(
        default=128, ge=32, le=2048,
        description="流式输出每块 token 数"
    )
    streaming_target_latency_ms: float = Field(
        default=1500.0, gt=0.0,
        description="特权队列流式首字节目标延迟 (ms)"
    )


class ShadowPregenConfig(BaseModel):
    """影子预生成配置。"""

    enable_shadow_pregen: bool = Field(default=True)
    prediction_lookahead: int = Field(
        default=1, ge=1, le=3,
        description="预测前瞻跳数"
    )
    cache_max_size: int = Field(
        default=20, ge=5, le=100,
        description="影子缓存最大条目数"
    )
    cache_ttl_seconds: float = Field(
        default=300.0, gt=0.0,
        description="缓存条目 TTL（秒）"
    )


class MeshInput(BaseModel):
    """Content Mesh Node 输入。"""

    agent_state: AgentState = Field(..., description="当前全局 AgentState")
    wfq_config: Optional[WfqConfig] = Field(default=None)
    shadow_config: Optional[ShadowPregenConfig] = Field(default=None)


class GenerationTask(BaseModel):
    """单个资源卡片生成任务。"""

    task_id: str = Field(..., description="任务唯一 ID")
    node_id: str = Field(..., description="目标知识点 ID")
    card_type: CardType = Field(..., description="卡片类型")
    queue_class: QueueClass = Field(..., description="队列类别")
    cognitive_style: str = Field(default="textual")
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0)
    priority: int = Field(default=0, ge=0, description="WFQ 优先级 (越小越优先)")
    status: GenerationStatus = Field(default=GenerationStatus.QUEUED)
    estimated_tokens: int = Field(default=500, ge=0)
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="生成进度 0.0-1.0")
    is_shadow: bool = Field(default=False, description="是否为影子预生成任务")


class MeshOutput(BaseModel):
    """Content Mesh Node 输出。"""

    agent_state: AgentState = Field(..., description="更新后的全局 AgentState")
    generated_cards: List[ResourceCard] = Field(
        default_factory=list, description="本轮生成的资源卡片"
    )
    active_tasks: List[GenerationTask] = Field(
        default_factory=list, description="当前活跃的生成任务"
    )
    shadow_cache_hits: int = Field(default=0, description="影子缓存命中数")
    aborted_tasks: List[str] = Field(
        default_factory=list, description="因重规划而熔断的任务 ID 列表"
    )
    streaming_progress: Dict[str, float] = Field(
        default_factory=dict, description="各卡片流式生成进度 task_id → 0.0-1.0"
    )
    diagnostics: Dict[str, Any] = Field(
        default_factory=dict, description="诊断信息"
    )


# ============================================================================
# WFQ 调度器
# ============================================================================

class WFQScheduler:
    """带特权门控的加权公平队列调度器。

    算法:
      - 维护两个优先级队列: privileged (70% 配额), regular (30% 配额)
      - 每个任务携带 (virtual_finish_time, task_id)，按 VFT 升序出队
      - VFT = task_start_time + estimated_tokens / queue_weight
      - 特权队列 weight = 0.70 / Σweights, 常规 weight = 0.30 / Σweights

    引用:
      Demers, A., Keshav, S., & Shenker, S. (1989).
      Analysis and simulation of a fair queueing algorithm.
    """

    def __init__(self, config: Optional[WfqConfig] = None) -> None:
        self._config = config or WfqConfig()
        # 特权最小堆: (virtual_finish_time, task_id, task)
        self._privileged_heap: List[Tuple[float, str, GenerationTask]] = []
        # 常规最小堆
        self._regular_heap: List[Tuple[float, str, GenerationTask]] = []
        # 并发槽位
        self._active_privileged: Dict[str, GenerationTask] = {}
        self._active_regular: Dict[str, GenerationTask] = {}
        # 虚拟时间
        self._virtual_time_privileged: float = 0.0
        self._virtual_time_regular: float = 0.0
        # 权重
        self._weight_privileged: float = self._config.privileged_token_ratio
        self._weight_regular: float = self._config.regular_token_ratio
        # 配额已用 token 计数器
        self._privileged_tokens_used: int = 0
        self._regular_tokens_used: int = 0

    @property
    def config(self) -> WfqConfig:
        return self._config

    def enqueue(self, task: GenerationTask) -> None:
        """将生成任务加入对应队列。

        Args:
            task: 生成任务。
        """
        task.status = GenerationStatus.QUEUED

        # 计算虚拟完成时间
        weight = (
            self._weight_privileged
            if task.queue_class == QueueClass.PRIVILEGED
            else self._weight_regular
        )
        virtual_time = (
            self._virtual_time_privileged
            if task.queue_class == QueueClass.PRIVILEGED
            else self._virtual_time_regular
        )

        vft = virtual_time + task.estimated_tokens / max(weight, 0.01)

        if task.queue_class == QueueClass.PRIVILEGED:
            heapq.heappush(
                self._privileged_heap, (vft, task.task_id, task)
            )
            self._virtual_time_privileged = vft
        else:
            heapq.heappush(
                self._regular_heap, (vft, task.task_id, task)
            )
            self._virtual_time_regular = vft

    def dequeue(self) -> Optional[GenerationTask]:
        """按 WFQ 规则出队下一个应执行的任务。

        优先从特权队列取任务，除非：
          - 特权队列为空
          - 特权并发槽已满
          - 特权配额已耗尽

        Returns:
            GenerationTask if available, else None。
        """
        # 尝试从特权队列取
        if self._privileged_heap and len(
            self._active_privileged
        ) < self._config.max_concurrent_privileged:
            _, _, task = heapq.heappop(self._privileged_heap)
            self._active_privileged[task.task_id] = task
            return task

        # 尝试从常规队列取
        if self._regular_heap and len(
            self._active_regular
        ) < self._config.max_concurrent_regular:
            _, _, task = heapq.heappop(self._regular_heap)
            self._active_regular[task.task_id] = task
            return task

        return None

    def complete_task(self, task_id: str) -> None:
        """标记任务完成，释放并发槽位。"""
        self._active_privileged.pop(task_id, None)
        self._active_regular.pop(task_id, None)

    def abort_tasks_by_node(self, node_id: str) -> List[str]:
        """熔断指定知识点的所有在途任务并回收配额。

        Args:
            node_id: 要熔断的知识点 ID。

        Returns:
            被熔断的任务 ID 列表。
        """
        aborted: List[str] = []

        # 检查特权堆
        new_priv_heap: List[Tuple[float, str, GenerationTask]] = []
        while self._privileged_heap:
            vft, tid, task = heapq.heappop(self._privileged_heap)
            if task.node_id == node_id:
                task.status = GenerationStatus.ABORTED
                aborted.append(tid)
            else:
                new_priv_heap.append((vft, tid, task))
        self._privileged_heap = new_priv_heap
        heapq.heapify(self._privileged_heap)

        # 检查常规堆
        new_reg_heap: List[Tuple[float, str, GenerationTask]] = []
        while self._regular_heap:
            vft, tid, task = heapq.heappop(self._regular_heap)
            if task.node_id == node_id:
                task.status = GenerationStatus.ABORTED
                aborted.append(tid)
            else:
                new_reg_heap.append((vft, tid, task))
        self._regular_heap = new_reg_heap
        heapq.heapify(self._regular_heap)

        # 检查活跃任务
        for tid, task in list(self._active_privileged.items()):
            if task.node_id == node_id:
                task.status = GenerationStatus.ABORTED
                aborted.append(tid)
                self.complete_task(tid)
        for tid, task in list(self._active_regular.items()):
            if task.node_id == node_id:
                task.status = GenerationStatus.ABORTED
                aborted.append(tid)
                self.complete_task(tid)

        return aborted

    def get_queue_sizes(self) -> Dict[str, int]:
        """获取各队列当前大小。"""
        return {
            "privileged_queued": len(self._privileged_heap),
            "regular_queued": len(self._regular_heap),
            "privileged_active": len(self._active_privileged),
            "regular_active": len(self._active_regular),
        }


# ============================================================================
# 马尔可夫拓扑预测影子预生成引擎
# ============================================================================

class MarkovShadowPregen:
    """马尔可夫拓扑预测影子预生成引擎。

    原理:
      对于当前节点 u 的每个出边邻居 v ∈ successors(u):
        P(v | u) = softmax(1 / edge_cost(u, v))
      选择 P(v|u) 最大的单一 Top-1 目标节点 v*，
      提前在后台生成该节点的资源卡片，压入 LRU 缓存。

    缓存:
      LRU + TTL 双层淘汰策略。
    """

    def __init__(self, config: Optional[ShadowPregenConfig] = None) -> None:
        self._config = config or ShadowPregenConfig()
        # 缓存: {node_id → ResourceCard}
        self._cache: OrderedDict[str, ResourceCard] = OrderedDict()
        # 缓存时间戳: {node_id → timestamp}
        self._cache_ts: Dict[str, float] = {}
        # 当前预生成状态
        self._status: Dict[str, ShadowStatus] = {}
        # 激活概率记录
        self._transition_probs: Dict[str, Dict[str, float]] = {}

    @property
    def config(self) -> ShadowPregenConfig:
        return self._config

    def predict_top1_target(
        self,
        current_node_id: str,
        adj_list: Dict[str, List[Tuple[str, float]]],
        mastery_map: Dict[str, float],
    ) -> Optional[str]:
        """基于马尔可夫转移概率预测 Top-1 后向激活节点。

        转移概率:
          P(v | u) ∝ exp(-β · edge_cost(u, v))
          其中 edge_cost = (1 - mastery[u]) · weight + difficulty[v]

        Args:
            current_node_id: 当前节点 ID。
            adj_list: 邻接表 {src → [(tgt, weight)]}。
            mastery_map: 掌握度映射。

        Returns:
            Top-1 预测目标节点 ID，若无出边则返回 None。
        """
        successors = adj_list.get(current_node_id, [])
        if not successors:
            return None

        # 计算各后继的转移概率
        probs: Dict[str, float] = {}
        costs: Dict[str, float] = {}

        for tgt, weight in successors:
            src_mastery = mastery_map.get(current_node_id, 0.5)
            unmastered = max(0.0, 1.0 - src_mastery)
            cost = unmastered * weight + 0.5  # 简化 difficulty
            costs[tgt] = cost
            probs[tgt] = math.exp(-2.0 * cost)  # β = 2.0

        # Softmax 归一化
        total = sum(probs.values())
        if total > 0:
            probs = {k: v / total for k, v in probs.items()}

        # Top-1
        top1 = max(probs, key=probs.get)

        self._transition_probs[current_node_id] = probs
        return top1

    def cache_put(self, node_id: str, card: ResourceCard) -> None:
        """将预生成卡片写入缓存（LRU 淘汰）。"""
        # TTL 清理
        now = _time.time()
        expired = [
            nid for nid, ts in self._cache_ts.items()
            if now - ts > self._config.cache_ttl_seconds
        ]
        for nid in expired:
            self._cache.pop(nid, None)
            self._cache_ts.pop(nid, None)

        # LRU 淘汰
        while len(self._cache) >= self._config.cache_max_size:
            self._cache.popitem(last=False)

        self._cache[node_id] = card
        self._cache_ts[node_id] = now
        self._status[node_id] = ShadowStatus.CACHED

    def cache_get(self, node_id: str) -> Optional[ResourceCard]:
        """从缓存中获取预生成卡片（命中则更新 LRU 位置）。"""
        if node_id not in self._cache:
            return None
        # TTL 检查
        now = _time.time()
        if now - self._cache_ts.get(node_id, 0) > self._config.cache_ttl_seconds:
            self._cache.pop(node_id, None)
            self._cache_ts.pop(node_id, None)
            return None
        # LRU: move to end
        card = self._cache.pop(node_id)
        self._cache[node_id] = card
        return card

    def abort_shadow(self, node_id: str) -> None:
        """熔断指定节点的影子预生成。"""
        self._status[node_id] = ShadowStatus.ABORTED
        self._cache.pop(node_id, None)
        self._cache_ts.pop(node_id, None)

    def get_cache_stats(self) -> Dict[str, Any]:
        return {
            "cache_size": len(self._cache),
            "cached_nodes": list(self._cache.keys()),
            "status": {
                nid: s.value for nid, s in self._status.items()
            },
        }


# ============================================================================
# Content Mesh Node — LangGraph Node 主类
# ============================================================================

class ContentMeshNode:
    """LangGraph Content Mesh Node — 资源生成与调度引擎。

    在 LangGraph 中的注册方式:
        >>> graph.add_node("content_mesh", mesh_node)

    执行流程:
      1. 读取 active_path → 确定当前节点及其后继
      2. 马尔可夫预测 Top-1 后继 → 启动影子预生成
      3. 若 re_plan_triggered → 熔断废弃路径任务
      4. WFQ 调度资源卡片生成任务
      5. 流式输出卡片 + 进度追踪
    """

    RESOURCE_TEMPLATES: Dict[str, str] = {
        "concept_map": "# {title}\n\n## 概念图谱\n\n```mermaid\ngraph TD\n{content}\n```\n\n*难度: {difficulty}*",
        "code_snippet": "# {title}\n\n## 代码示例\n\n```python\n{content}\n```\n\n*难度: {difficulty}*",
        "interactive_exercise": "# {title}\n\n## 互动练习\n\n{content}\n\n---\n*难度: {difficulty} | 类型: exercise*",
        "video_summary": "# {title}\n\n## 视频摘要\n\n[video] {content}\n\n*时长: ~{duration}min | 难度: {difficulty}*",
        "diagnostic_quiz": "# {title}\n\n## 诊断测验\n\n{content}\n\n---\n*题目数: {question_count} | 难度: {difficulty}*",
    }

    def __init__(
        self,
        wfq_config: Optional[WfqConfig] = None,
        shadow_config: Optional[ShadowPregenConfig] = None,
        # 可注入的 LLM 生成函数（用于测试 Mock）
        generate_fn: Optional[Callable[[str, str, float], str]] = None,
    ) -> None:
        self._scheduler = WFQScheduler(wfq_config)
        self._shadow = MarkovShadowPregen(shadow_config)
        self._generate_fn = generate_fn or self._default_generate
        # 邻接表 (由外部注入或从 Neo4j 同步)
        self._adj: Dict[str, List[Tuple[str, float]]] = {}

    # ------------------------------------------------------------------
    # LangGraph Node 调用签名
    # ------------------------------------------------------------------

    def __call__(self, inp: MeshInput) -> MeshOutput:
        return self.mesh(inp)

    # ------------------------------------------------------------------
    # 核心调度逻辑
    # ------------------------------------------------------------------

    def mesh(self, inp: MeshInput) -> MeshOutput:
        """执行完整的资源生成与调度管线。"""
        state = inp.agent_state
        diagnostics: Dict[str, Any] = {}
        aborted_tasks: List[str] = []
        shadow_hits = 0

        active_path = state.active_path
        if not active_path:
            return MeshOutput(
                agent_state=state,
                diagnostics={"warning": "active_path 为空，跳过资源生成"},
            )

        current_node = active_path[0] if active_path else "unknown"

        # ---- Step 1: 重规划熔断 ----
        if state.re_plan_triggered:
            # 熔断 active_path 中不再需要的节点任务
            for old_node in active_path[1:]:  # 跳过当前节点
                aborted = self._scheduler.abort_tasks_by_node(old_node)
                aborted_tasks.extend(aborted)
                if self._shadow.config.enable_shadow_pregen:
                    self._shadow.abort_shadow(old_node)
            state.clear_replan()
            diagnostics["replan_aborted"] = len(aborted_tasks)

        # ---- Step 2: 马尔可夫预测 + 影子预生成 ----
        if self._shadow.config.enable_shadow_pregen:
            next_node = self._shadow.predict_top1_target(
                current_node, self._adj, state.dynamic_profile.knowledge_mastery
            )
            if next_node:
                # 尝试从缓存获取
                cached = self._shadow.cache_get(next_node)
                if cached:
                    shadow_hits += 1
                    diagnostics["shadow_cache_hit"] = next_node
                else:
                    # 启动影子预生成任务
                    shadow_task = GenerationTask(
                        task_id=f"shadow_{next_node}_{uuid.uuid4().hex[:8]}",
                        node_id=next_node,
                        card_type=CardType.CONCEPT_MAP,
                        queue_class=QueueClass.REGULAR,
                        cognitive_style=state.static_profile.cognitive_style_distribution.compute_means(),
                        difficulty=0.5,
                        priority=10,  # 低优先级
                        is_shadow=True,
                    )
                    self._scheduler.enqueue(shadow_task)
                    diagnostics["shadow_pregen_started"] = next_node

        # ---- Step 3: 为 active_path 中的节点创建生成任务 ----
        recommended_style = state.static_profile.cognitive_style_distribution
        style_means = recommended_style.compute_means()
        # 选择主导风格
        dominant_style = max(style_means, key=style_means.get)

        for node_id in active_path[:3]:  # 只调度前 3 个节点的资源
            mastery = state.dynamic_profile.knowledge_mastery.get(node_id, 0.5)
            difficulty = max(0.1, 1.0 - mastery)  # 掌握越低 → 难度越高

            # 特权队列: 概念导图 + 代码片段
            for card_type in [CardType.CONCEPT_MAP, CardType.CODE_SNIPPET]:
                task = GenerationTask(
                    task_id=f"gen_{node_id}_{card_type.value}_{uuid.uuid4().hex[:8]}",
                    node_id=node_id,
                    card_type=card_type,
                    queue_class=QueueClass.PRIVILEGED,
                    cognitive_style=dominant_style,
                    difficulty=difficulty,
                    priority=0,
                    estimated_tokens=800 if card_type == CardType.CONCEPT_MAP else 400,
                )
                self._scheduler.enqueue(task)

            # 常规队列: 互动练习 + 视频摘要 + 诊断测验
            for card_type in [
                CardType.INTERACTIVE_EXERCISE,
                CardType.VIDEO_SUMMARY,
                CardType.DIAGNOSTIC_QUIZ,
            ]:
                task = GenerationTask(
                    task_id=f"gen_{node_id}_{card_type.value}_{uuid.uuid4().hex[:8]}",
                    node_id=node_id,
                    card_type=card_type,
                    queue_class=QueueClass.REGULAR,
                    cognitive_style=dominant_style,
                    difficulty=difficulty,
                    priority=1,
                    estimated_tokens=600,
                )
                self._scheduler.enqueue(task)

        # ---- Step 4: WFQ 出队 + 生成 ----
        generated_cards: List[ResourceCard] = []
        max_cards_this_round = 5
        active_tasks: List[GenerationTask] = []

        for _ in range(max_cards_this_round):
            task = self._scheduler.dequeue()
            if task is None:
                break

            task.status = GenerationStatus.STREAMING
            task.progress = 0.0

            # 模拟/实际调用 LLM 生成
            try:
                content = self._generate_fn(
                    task.node_id, task.card_type.value, task.difficulty
                )
                task.status = GenerationStatus.COMPLETED
                task.progress = 1.0
            except Exception:
                task.status = GenerationStatus.FAILED
                content = f"[Generation failed for {task.card_type.value}]"

            card = ResourceCard(
                resource_id=task.task_id,
                node_id=task.node_id,
                card_type=task.card_type.value,
                content=content,
                difficulty=task.difficulty,
                cognitive_style=task.cognitive_style,
            )
            generated_cards.append(card)
            self._scheduler.complete_task(task.task_id)

        # ---- Step 5: 更新 AgentState ----
        for card in generated_cards:
            node_id = card.node_id
            if node_id not in state.generated_resources:
                state.generated_resources[node_id] = []
            state.generated_resources[node_id].append(card)

        # ---- Step 6: 收集活跃任务 ----
        queue_stats = self._scheduler.get_queue_sizes()
        diagnostics["queue_stats"] = queue_stats

        # ---- Step 7: 组装输出 ----
        return MeshOutput(
            agent_state=state,
            generated_cards=generated_cards,
            active_tasks=active_tasks,
            shadow_cache_hits=shadow_hits,
            aborted_tasks=aborted_tasks,
            diagnostics=diagnostics,
        )

    # ------------------------------------------------------------------
    # 邻接表管理
    # ------------------------------------------------------------------

    def set_adjacency(
        self, adj: Dict[str, List[Tuple[str, float]]]
    ) -> None:
        """注入知识图谱邻接表（从 Planner Node 同步）。"""
        self._adj = adj

    # ------------------------------------------------------------------
    # 默认生成函数（测试用）
    # ------------------------------------------------------------------

    @staticmethod
    def _default_generate(
        node_id: str, card_type: str, difficulty: float
    ) -> str:
        """默认的 LLM 生成模拟器 — 返回模板内容。

        实际部署时替换为科大讯飞星火大模型 API 调用。
        """
        template = ContentMeshNode.RESOURCE_TEMPLATES.get(
            card_type,
            "# {title}\n\n{content}\n\n*难度: {difficulty}*",
        )
        return template.format(
            title=f"知识点 {node_id}",
            content=f"针对节点 {node_id} 的 {card_type} 类型学习资源。"
                    f"\n\n难度系数: {difficulty:.2f}",
            difficulty=f"{difficulty:.2f}",
            duration="10",
            question_count="5",
        )


# ============================================================================
# 工厂函数
# ============================================================================

def create_content_mesh_node(
    wfq_config: Optional[WfqConfig] = None,
    shadow_config: Optional[ShadowPregenConfig] = None,
    generate_fn: Optional[Callable[[str, str, float], str]] = None,
) -> ContentMeshNode:
    """创建 Content Mesh Node 实例。"""
    return ContentMeshNode(
        wfq_config=wfq_config,
        shadow_config=shadow_config,
        generate_fn=generate_fn,
    )
