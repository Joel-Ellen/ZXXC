# -*- coding: utf-8 -*-
"""
冷启动交互辅助组件 (辅助算法三扩展)
=====================================

冷启动状态机 + 情境探针 (Situation Probe) + 贝叶斯先验融合。

核心机制：
1. 状态机驱动的情境探针发问 — 逐维度收集 6 维用户画像
2. 硬上限熔断降级 — c_epoch 达到 3 轮若仍未集齐全部维度，
   触发贝叶斯先验概率分布融合，强制进入正式学习阶段
3. 贝叶斯融合公式：
     P(profile | background, education) ∝ P(background | profile) · P(education | profile) · P(profile)

6 维用户画像维度:
  1. 认知风格偏好 (视觉/文本/实践)     — Beta 分布
  2. 学习动机 (考试/认证/项目/兴趣)    — Categorical 分布
  3. 专业背景 (计算机/电子/机械/数学/...) — Categorical 分布
  4. 学历层次 (本科/硕士/博士/自学)      — Categorical 分布
  5. 每周可用时间                       — Gamma 分布
  6. 已有知识基础                       — 多选题向量

依赖声明：
  AI 辅助编码工具：科大讯飞 iFlyCode / 星火大模型辅助生成。
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from enum import Enum, auto
from collections import OrderedDict

from pydantic import BaseModel, Field, field_validator

from ..state.agent_state import (
    AgentState,
    StaticProfile,
    DynamicProfile,
    CognitiveStyleDistribution,
    ErrorTypeDistribution,
)


# ============================================================================
# 枚举与常量
# ============================================================================

class ColdStartPhase(str, Enum):
    """冷启动状态机阶段枚举。"""
    INIT = "init"                          # 初始欢迎
    PROBE_COGNITIVE_STYLE = "probe_cognitive_style"     # 维度 1: 认知风格
    PROBE_MOTIVATION = "probe_motivation"               # 维度 2: 学习动机
    PROBE_BACKGROUND = "probe_background"               # 维度 3: 专业背景
    PROBE_EDUCATION = "probe_education"                 # 维度 4: 学历层次
    PROBE_TIME_BUDGET = "probe_time_budget"             # 维度 5: 时间预算
    PROBE_KNOWLEDGE_BASE = "probe_knowledge_base"       # 维度 6: 已有知识
    FUSION_FALLBACK = "fusion_fallback"      # 熔断降级: 贝叶斯融合
    COMPLETE = "complete"                    # 冷启动完成


class BackgroundField(str, Enum):
    """专业背景分类。"""
    CS = "computer_science"
    EE = "electrical_engineering"
    ME = "mechanical_engineering"
    MATH = "mathematics"
    PHYSICS = "physics"
    BIOLOGY = "biology"
    BUSINESS = "business"
    LIBERAL_ARTS = "liberal_arts"
    OTHER = "other"


class EducationLevel(str, Enum):
    """学历层次分类。"""
    BACHELOR = "bachelor"
    MASTER = "master"
    PHD = "phd"
    SELF_TAUGHT = "self_taught"
    HIGH_SCHOOL = "high_school"


class MotivationType(str, Enum):
    """学习动机分类。"""
    ACADEMIC_EXAM = "academic_exam"
    SKILL_CERTIFICATION = "skill_certification"
    PROJECT_DRIVEN = "project_driven"
    CURIOSITY = "curiosity"


# ============================================================================
# Pydantic 数据模型
# ============================================================================

class SituationProbe(BaseModel):
    """情境探针 — 一个维度探测问题。"""

    dimension: int = Field(..., ge=1, le=6, description="画像维度编号 (1-6)")
    phase: ColdStartPhase = Field(..., description="对应的状态机阶段")
    question: str = Field(..., description="向用户展示的问题文本")
    options: List[str] = Field(default_factory=list, description="可选答案列表")
    option_values: List[Any] = Field(default_factory=list, description="选项对应的内部值")
    is_multi_select: bool = Field(default=False, description="是否支持多选")
    probe_metadata: Dict[str, str] = Field(default_factory=dict)


class DimensionStatus(BaseModel):
    """单维度收集状态。"""

    dimension: int = Field(..., ge=1, le=6)
    label: str = Field(..., description="维度名称")
    collected: bool = Field(default=False, description="是否已收集")
    value: Optional[Any] = Field(default=None, description="收集到的值")
    probe_count: int = Field(default=0, ge=0, description="已发送的探针次数")


class ColdStartState(BaseModel):
    """冷启动会话状态 — 在 cold_start 流程中维护。"""

    user_id: str = Field(..., description="用户 ID")
    current_phase: ColdStartPhase = Field(default=ColdStartPhase.INIT)
    dimensions_status: Dict[int, DimensionStatus] = Field(
        default_factory=lambda: {
            1: DimensionStatus(dimension=1, label="认知风格偏好"),
            2: DimensionStatus(dimension=2, label="学习动机"),
            3: DimensionStatus(dimension=3, label="专业背景"),
            4: DimensionStatus(dimension=4, label="学历层次"),
            5: DimensionStatus(dimension=5, label="每周可用时间"),
            6: DimensionStatus(dimension=6, label="已有知识基础"),
        }
    )
    collected_dimensions: int = Field(default=0, ge=0, le=6)
    epoch_counter: int = Field(default=0, ge=0, le=3, description="轮次计数 (0-3)")
    fusion_triggered: bool = Field(default=False, description="是否触发贝叶斯融合")
    current_probe: Optional[SituationProbe] = Field(default=None)
    responses_history: List[Dict[str, Any]] = Field(default_factory=list)

    def mark_dimension_collected(self, dim: int, value: Any) -> None:
        """标记某维度已收集。"""
        if dim in self.dimensions_status:
            status = self.dimensions_status[dim]
            if not status.collected:
                status.collected = True
                status.value = value
                self.collected_dimensions += 1

    def all_dimensions_collected(self) -> bool:
        """检查是否所有 6 个维度均已收集。"""
        return self.collected_dimensions >= 6

    def missing_dimensions(self) -> List[int]:
        """返回尚未收集的维度编号列表。"""
        return [
            dim for dim, status in self.dimensions_status.items()
            if not status.collected
        ]

    def increment_epoch(self) -> None:
        """递增轮次计数器。"""
        self.epoch_counter += 1

    def should_fuse(self) -> bool:
        """判断是否应触发贝叶斯融合熔断。"""
        return (
            self.epoch_counter >= 3
            and not self.all_dimensions_collected()
            and not self.fusion_triggered
        )


# ============================================================================
# 贝叶斯先验分布融合引擎
# ============================================================================

class BayesianPriorFusion:
    """贝叶斯先验概率分布融合计算引擎。

    当冷启动计数器 c_epoch 达到硬上限 3，但仍有维度未收集时，
    利用已收集的维度（专业背景、学历层次）作为环境特征 (evidence)，
    对未收集维度进行先验概率分布推断。

    贝叶斯公式:
      P(profile_dim | background, education) =
        P(background | profile_dim) · P(education | profile_dim) · P(profile_dim) / Z

    其中 Z 为归一化常数 Σ P(background | d) · P(education | d) · P(d)。

    先验表格基于教育学/认知科学文献构建，支持在线更新。
    """

    # ---- 条件概率表 (Conditional Probability Tables) ----

    # P(background | cognitive_style) — 专业背景与认知风格的关联
    # 认知风格: visual, textual, practical
    BACKGROUND_GIVEN_COGNITIVE: Dict[str, Dict[str, float]] = {
        "visual": {
            "computer_science": 0.35, "electrical_engineering": 0.20,
            "mechanical_engineering": 0.15, "mathematics": 0.08,
            "physics": 0.07, "biology": 0.05, "business": 0.04,
            "liberal_arts": 0.04, "other": 0.02,
        },
        "textual": {
            "computer_science": 0.20, "electrical_engineering": 0.10,
            "mechanical_engineering": 0.05, "mathematics": 0.15,
            "physics": 0.08, "biology": 0.07, "business": 0.15,
            "liberal_arts": 0.15, "other": 0.05,
        },
        "practical": {
            "computer_science": 0.30, "electrical_engineering": 0.25,
            "mechanical_engineering": 0.20, "mathematics": 0.05,
            "physics": 0.08, "biology": 0.05, "business": 0.03,
            "liberal_arts": 0.02, "other": 0.02,
        },
    }

    # P(education | cognitive_style) — 学历与认知风格的关联
    EDUCATION_GIVEN_COGNITIVE: Dict[str, Dict[str, float]] = {
        "visual": {
            "bachelor": 0.40, "master": 0.30, "phd": 0.15,
            "self_taught": 0.10, "high_school": 0.05,
        },
        "textual": {
            "bachelor": 0.30, "master": 0.25, "phd": 0.25,
            "self_taught": 0.10, "high_school": 0.10,
        },
        "practical": {
            "bachelor": 0.35, "master": 0.30, "phd": 0.10,
            "self_taught": 0.20, "high_school": 0.05,
        },
    }

    # P(background | motivation) — 专业背景与学习动机的关联
    BACKGROUND_GIVEN_MOTIVATION: Dict[str, Dict[str, float]] = {
        "academic_exam": {
            "computer_science": 0.30, "electrical_engineering": 0.15,
            "mechanical_engineering": 0.10, "mathematics": 0.18,
            "physics": 0.12, "biology": 0.05, "business": 0.05,
            "liberal_arts": 0.03, "other": 0.02,
        },
        "skill_certification": {
            "computer_science": 0.40, "electrical_engineering": 0.20,
            "mechanical_engineering": 0.10, "mathematics": 0.05,
            "physics": 0.05, "biology": 0.03, "business": 0.10,
            "liberal_arts": 0.04, "other": 0.03,
        },
        "project_driven": {
            "computer_science": 0.35, "electrical_engineering": 0.20,
            "mechanical_engineering": 0.15, "mathematics": 0.08,
            "physics": 0.07, "biology": 0.05, "business": 0.05,
            "liberal_arts": 0.03, "other": 0.02,
        },
        "curiosity": {
            "computer_science": 0.15, "electrical_engineering": 0.10,
            "mechanical_engineering": 0.08, "mathematics": 0.12,
            "physics": 0.10, "biology": 0.10, "business": 0.10,
            "liberal_arts": 0.15, "other": 0.10,
        },
    }

    # P(education | motivation)
    EDUCATION_GIVEN_MOTIVATION: Dict[str, Dict[str, float]] = {
        "academic_exam": {
            "bachelor": 0.50, "master": 0.30, "phd": 0.10,
            "self_taught": 0.05, "high_school": 0.05,
        },
        "skill_certification": {
            "bachelor": 0.40, "master": 0.35, "phd": 0.10,
            "self_taught": 0.10, "high_school": 0.05,
        },
        "project_driven": {
            "bachelor": 0.35, "master": 0.35, "phd": 0.10,
            "self_taught": 0.15, "high_school": 0.05,
        },
        "curiosity": {
            "bachelor": 0.25, "master": 0.25, "phd": 0.15,
            "self_taught": 0.20, "high_school": 0.15,
        },
    }

    # 先验 P(profile_dim) — 无信息时的均匀/常识先验
    COGNITIVE_STYLE_PRIOR: Dict[str, float] = {
        "visual": 0.35, "textual": 0.40, "practical": 0.25,
    }
    MOTIVATION_PRIOR: Dict[str, float] = {
        "academic_exam": 0.35, "skill_certification": 0.25,
        "project_driven": 0.25, "curiosity": 0.15,
    }
    TIME_BUDGET_PRIOR: Dict[str, float] = {
        "low": 0.25,    # <5h/week
        "medium": 0.50,  # 5-15h/week
        "high": 0.25,    # >15h/week
    }

    # ---- 公开融合方法 ----

    def fuse_cognitive_style(
        self, background: Optional[str], education: Optional[str]
    ) -> Dict[str, float]:
        """贝叶斯融合推断认知风格分布。

        Args:
            background: 专业背景 (若已收集)。
            education: 学历层次 (若已收集)。

        Returns:
            {visual: p, textual: p, practical: p} 归一化后验概率。
        """
        styles = list(self.COGNITIVE_STYLE_PRIOR.keys())
        posteriors: Dict[str, float] = {}

        for style in styles:
            posterior = math.log(self.COGNITIVE_STYLE_PRIOR.get(style, 1.0 / len(styles)) + 1e-10)

            if background:
                bg_prob = self.BACKGROUND_GIVEN_COGNITIVE.get(style, {}).get(background, 0.01)
                posterior += math.log(bg_prob + 1e-10)

            if education:
                edu_prob = self.EDUCATION_GIVEN_COGNITIVE.get(style, {}).get(education, 0.01)
                posterior += math.log(edu_prob + 1e-10)

            posteriors[style] = math.exp(posterior)

        # 归一化
        total = sum(posteriors.values())
        if total > 0:
            posteriors = {k: v / total for k, v in posteriors.items()}

        return posteriors

    def fuse_motivation(
        self, background: Optional[str], education: Optional[str]
    ) -> Dict[str, float]:
        """贝叶斯融合推断学习动机分布。"""
        motivations = list(self.MOTIVATION_PRIOR.keys())
        posteriors: Dict[str, float] = {}

        for mot in motivations:
            posterior = math.log(self.MOTIVATION_PRIOR.get(mot, 1.0 / len(motivations)) + 1e-10)

            if background:
                bg_prob = self.BACKGROUND_GIVEN_MOTIVATION.get(mot, {}).get(background, 0.01)
                posterior += math.log(bg_prob + 1e-10)

            if education:
                edu_prob = self.EDUCATION_GIVEN_MOTIVATION.get(mot, {}).get(education, 0.01)
                posterior += math.log(edu_prob + 1e-10)

            posteriors[mot] = math.exp(posterior)

        # 归一化
        total = sum(posteriors.values())
        if total > 0:
            posteriors = {k: v / total for k, v in posteriors.items()}

        return posteriors

    def fuse_time_budget(
        self, background: Optional[str], education: Optional[str]
    ) -> Dict[str, float]:
        """贝叶斯融合推断时间预算分布。

        基于学历与背景的先验：
          - 本科/硕士 CS 学生: 倾向 medium-high
          - 博士/在职: 倾向 low-medium
          - 自学: 倾向 medium
        """
        # 从先验出发
        posteriors = dict(self.TIME_BUDGET_PRIOR)

        if education == "phd":
            posteriors["low"] *= 1.5
            posteriors["high"] *= 0.5
        elif education in ("bachelor", "master"):
            posteriors["medium"] *= 1.3
            posteriors["high"] *= 1.2
        elif education == "self_taught":
            posteriors["medium"] *= 1.4
        elif education == "high_school":
            posteriors["high"] *= 1.5

        if background == "computer_science":
            posteriors["high"] *= 1.3

        # 归一化
        total = sum(posteriors.values())
        if total > 0:
            posteriors = {k: v / total for k, v in posteriors.items()}

        return posteriors

    def infer_knowledge_categories(
        self, background: Optional[str], education: Optional[str]
    ) -> List[str]:
        """基于背景与学历推断已有知识的高概率类别。

        Returns:
            推荐的知识分类标签列表 (如 ["python_basics", "data_structures", ...])。
        """
        knowledge_map: Dict[str, Dict[str, List[str]]] = {
            "computer_science": {
                "bachelor": ["python_basics", "data_structures", "algorithms_intro", "database_basics"],
                "master": ["machine_learning_basics", "deep_learning_intro", "distributed_systems"],
                "phd": ["advanced_ml", "research_methods", "linear_algebra_advanced"],
                "self_taught": ["practical_coding", "web_dev_basics"],
                "high_school": ["intro_to_programming", "math_fundamentals"],
            },
            "electrical_engineering": {
                "bachelor": ["circuit_analysis", "signal_processing", "python_basics"],
                "master": ["embedded_systems", "dsp_advanced"],
                "phd": ["research_methods", "advanced_signal_processing"],
                "self_taught": ["practical_electronics", "arduino"],
                "high_school": ["physics_basics", "math_fundamentals"],
            },
            "mathematics": {
                "bachelor": ["calculus", "linear_algebra", "probability_theory"],
                "master": ["advanced_statistics", "optimization_theory"],
                "phd": ["research_methods", "topology"],
                "self_taught": ["practical_math", "statistics_for_ds"],
                "high_school": ["algebra", "geometry"],
            },
        }

        # 默认回退
        default_knowledge = ["intro_to_programming", "math_fundamentals"]

        if not background or background not in knowledge_map:
            return default_knowledge

        bg_map = knowledge_map[background]
        if not education or education not in bg_map:
            return bg_map.get("bachelor", default_knowledge)

        return bg_map.get(education, default_knowledge)

    def execute_full_fusion(
        self,
        collected_dimensions: Dict[int, DimensionStatus],
    ) -> Dict[int, Any]:
        """执行完整的贝叶斯融合 — 对所有缺失维度进行先验推断。

        Args:
            collected_dimensions: 已收集的维度状态字典。

        Returns:
            {dimension_number: inferred_value} 映射。
        """
        # 提取环境特征
        background: Optional[str] = None
        education: Optional[str] = None

        if collected_dimensions.get(3) and collected_dimensions[3].collected:
            background = collected_dimensions[3].value
        if collected_dimensions.get(4) and collected_dimensions[4].collected:
            education = collected_dimensions[4].value

        fused: Dict[int, Any] = {}

        # 维度 1: 认知风格
        if not collected_dimensions.get(1) or not collected_dimensions[1].collected:
            style_probs = self.fuse_cognitive_style(background, education)
            # 选择 MAP (最大后验) 估计
            best_style = max(style_probs, key=style_probs.get)
            fused[1] = {
                "preferred_style": best_style,
                "distribution": style_probs,
                "inferred": True,
            }

        # 维度 2: 学习动机
        if not collected_dimensions.get(2) or not collected_dimensions[2].collected:
            mot_probs = self.fuse_motivation(background, education)
            best_mot = max(mot_probs, key=mot_probs.get)
            fused[2] = {
                "motivation": best_mot,
                "distribution": mot_probs,
                "inferred": True,
            }

        # 维度 5: 时间预算
        if not collected_dimensions.get(5) or not collected_dimensions[5].collected:
            time_probs = self.fuse_time_budget(background, education)
            # 将分类映射到具体小时数
            time_mapping = {"low": 4.0, "medium": 10.0, "high": 18.0}
            best_time_cat = max(time_probs, key=time_probs.get)
            fused[5] = {
                "time_budget_hours_per_week": time_mapping[best_time_cat],
                "time_category": best_time_cat,
                "distribution": time_probs,
                "inferred": True,
            }

        # 维度 6: 已有知识基础
        if not collected_dimensions.get(6) or not collected_dimensions[6].collected:
            knowledge = self.infer_knowledge_categories(background, education)
            fused[6] = {
                "knowledge_base": knowledge,
                "inferred": True,
            }

        return fused


# ============================================================================
# 情境探针工厂 — 生成 6 维探测问题
# ============================================================================

class ProbeFactory:
    """情境探针工厂 — 为 6 个维度生成标准化探测问题。"""

    @staticmethod
    def create_probe(dimension: int) -> SituationProbe:
        """根据维度编号生成情境探针。

        Args:
            dimension: 维度编号 (1-6)。

        Returns:
            SituationProbe。
        """
        probes: Dict[int, SituationProbe] = {
            1: SituationProbe(
                dimension=1,
                phase=ColdStartPhase.PROBE_COGNITIVE_STYLE,
                question=(
                    "当学习一个新概念时，你更倾向于哪种方式？"
                ),
                options=[
                    "📊 看图/视频演示，直观理解",
                    "📖 阅读文字说明，逻辑推导",
                    "🛠️ 动手实践，写代码/做实验",
                ],
                option_values=["visual", "textual", "practical"],
                is_multi_select=False,
            ),
            2: SituationProbe(
                dimension=2,
                phase=ColdStartPhase.PROBE_MOTIVATION,
                question="你学习这门课程的主要目标是什么？",
                options=[
                    "🎓 应对学校考试/考研",
                    "📜 获取技能认证/证书",
                    "🚀 完成一个实际项目",
                    "🤔 纯粹的好奇心驱动",
                ],
                option_values=["academic_exam", "skill_certification", "project_driven", "curiosity"],
                is_multi_select=False,
            ),
            3: SituationProbe(
                dimension=3,
                phase=ColdStartPhase.PROBE_BACKGROUND,
                question="你的专业背景是什么？",
                options=[
                    "💻 计算机科学与技术",
                    "⚡ 电子信息/电气工程",
                    "🔧 机械/自动化工程",
                    "📐 数学/统计学",
                    "🔬 物理学",
                    "🧬 生物/医学",
                    "💼 商科/管理",
                    "📚 人文社科",
                    "🔹 其他",
                ],
                option_values=[
                    "computer_science", "electrical_engineering",
                    "mechanical_engineering", "mathematics",
                    "physics", "biology", "business",
                    "liberal_arts", "other",
                ],
                is_multi_select=False,
            ),
            4: SituationProbe(
                dimension=4,
                phase=ColdStartPhase.PROBE_EDUCATION,
                question="你当前的学历层次是？",
                options=[
                    "🎒 高中及以下",
                    "🎓 本科在读/已毕业",
                    "📖 硕士在读/已毕业",
                    "🔬 博士在读/已毕业",
                    "💪 自学成才",
                ],
                option_values=["high_school", "bachelor", "master", "phd", "self_taught"],
                is_multi_select=False,
            ),
            5: SituationProbe(
                dimension=5,
                phase=ColdStartPhase.PROBE_TIME_BUDGET,
                question="你平均每周能投入多少小时学习？",
                options=[
                    "⏰ 少于 5 小时（碎片时间）",
                    "📅 5-15 小时（规律学习）",
                    "🚀 超过 15 小时（高强度投入）",
                ],
                option_values=[3.0, 10.0, 20.0],
                is_multi_select=False,
            ),
            6: SituationProbe(
                dimension=6,
                phase=ColdStartPhase.PROBE_KNOWLEDGE_BASE,
                question="以下哪些内容你已经有一定基础？（可多选）",
                options=[
                    "Python 基础编程",
                    "数据结构与算法",
                    "线性代数/概率论",
                    "机器学习基础概念",
                    "深度学习框架 (PyTorch/TensorFlow)",
                    "数据库与 SQL",
                    "Linux / Git 基本操作",
                    "以上都没有，我想从零开始",
                ],
                option_values=[
                    "python_basics", "data_structures", "linear_algebra",
                    "ml_basics", "deep_learning", "databases",
                    "dev_tools", "none",
                ],
                is_multi_select=True,
                probe_metadata={"allow_empty": "true"},
            ),
        }
        return probes.get(
            dimension,
            SituationProbe(dimension=dimension, phase=ColdStartPhase.INIT, question=""),
        )


# ============================================================================
# 冷启动状态机主引擎
# ============================================================================

class ColdStartEngine:
    """冷启动交互状态机引擎。

    设计模式:
      - 状态机驱动 6 轮情境探针发问
      - c_epoch 达到硬上限 3 若未集齐全部维度 → 触发贝叶斯融合熔断
      - 融合后标记 fusion_triggered = True，进入 COMPLETE 阶段

    使用示例:
        >>> engine = ColdStartEngine()
        >>> state = engine.initialize("user_001")
        >>> while state.current_phase != ColdStartPhase.COMPLETE:
        ...     probe = engine.get_next_probe(state)
        ...     print(probe.question)
        ...     user_answer_index = 0  # 模拟用户回答
        ...     state = engine.process_response(state, user_answer_index)
        ... # state 已就绪，可注入 AgentState.static_profile
    """

    # c_epoch 硬上限
    HARD_EPOCH_LIMIT: int = 3

    def __init__(self) -> None:
        self._probe_factory = ProbeFactory()
        self._fusion_engine = BayesianPriorFusion()
        self._phase_order: List[ColdStartPhase] = [
            ColdStartPhase.INIT,
            ColdStartPhase.PROBE_COGNITIVE_STYLE,
            ColdStartPhase.PROBE_MOTIVATION,
            ColdStartPhase.PROBE_BACKGROUND,
            ColdStartPhase.PROBE_EDUCATION,
            ColdStartPhase.PROBE_TIME_BUDGET,
            ColdStartPhase.PROBE_KNOWLEDGE_BASE,
        ]

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def initialize(self, user_id: str) -> ColdStartState:
        """初始化冷启动会话状态。

        Args:
            user_id: 用户唯一 ID。

        Returns:
            ColdStartState: 初始状态。
        """
        return ColdStartState(
            user_id=user_id,
            current_phase=ColdStartPhase.INIT,
        )

    # ------------------------------------------------------------------
    # 获取下一轮探针
    # ------------------------------------------------------------------

    def get_next_probe(self, state: ColdStartState) -> Optional[SituationProbe]:
        """根据当前状态获取当前阶段的情境探针。不推进状态机。

        状态机转移逻辑（仅由 process_response 推进）:
          1. INIT → 返回第一个探针，推进到 PROBE_COGNITIVE_STYLE
          2. 其他阶段 → 返回当前阶段对应的探针
          3. COMPLETE / FUSION_FALLBACK → 返回 None

        熔断检查: 若 should_fuse() 为 True，设置 FUSION_FALLBACK 并返回 None。

        Args:
            state: 当前冷启动状态。

        Returns:
            SituationProbe if 需要发问, None if 完成或需熔断。
        """
        # 检查是否应触发熔断
        if state.should_fuse():
            state.current_phase = ColdStartPhase.FUSION_FALLBACK
            state.fusion_triggered = True
            return None

        if state.current_phase == ColdStartPhase.COMPLETE:
            return None

        if state.current_phase == ColdStartPhase.FUSION_FALLBACK:
            return None

        # INIT → 推进到第一维探测 (不递增 epoch: epoch 由 handle_cold_start_interaction 管理)
        if state.current_phase == ColdStartPhase.INIT:
            state.current_phase = ColdStartPhase.PROBE_COGNITIVE_STYLE
            state.current_probe = self._probe_factory.create_probe(1)
            return state.current_probe

        # 当前 phase 对应某个维度，返回其探针
        dim = self._phase_to_dimension(state.current_phase)
        if dim > 0:
            dim_status = state.dimensions_status.get(dim)
            if dim_status and not dim_status.collected:
                state.current_probe = self._probe_factory.create_probe(dim)
                dim_status.probe_count += 1
                return state.current_probe
            else:
                # 防御: 当前维度的探针不应出现 "已收集" 状态
                # 若出现说明 process_response 未正确推进状态机
                next_phase = self._get_next_phase(state.current_phase)
                if next_phase == ColdStartPhase.COMPLETE:
                    state.current_phase = ColdStartPhase.COMPLETE
                    return None
                state.current_phase = next_phase
                return self.get_next_probe(state)

        return None

    # ------------------------------------------------------------------
    # 处理用户回答
    # ------------------------------------------------------------------

    def process_response(
        self, state: ColdStartState, answer_value: Any
    ) -> ColdStartState:
        """处理用户对当前探针的回答并推进状态机。

        调用流程:
          1. 标记当前阶段对应维度为已收集，记录回答
          2. 检查全部维度是否齐备 → COMPLETE
          3. 检查熔断条件 → FUSION_FALLBACK
          4. 推进到下一阶段，epoch+1

        Args:
            state: 当前冷启动状态。
            answer_value: 用户回答值。

        Returns:
            更新后的 ColdStartState。
        """
        current_dim = self._phase_to_dimension(state.current_phase)
        if current_dim > 0:
            state.mark_dimension_collected(current_dim, answer_value)
            state.responses_history.append({
                "epoch": state.epoch_counter,
                "dimension": current_dim,
                "phase": state.current_phase.value,
                "answer": answer_value,
            })

        # 检查是否所有维度已收集
        if state.all_dimensions_collected():
            state.current_phase = ColdStartPhase.COMPLETE
            return state

        # 检查是否应触发熔断
        if state.should_fuse():
            state.current_phase = ColdStartPhase.FUSION_FALLBACK
            state.fusion_triggered = True
            return state

        # 前进到下一阶段（epoch 不递增，由 handle_cold_start_interaction 管理轮次）
        next_phase = self._get_next_phase(state.current_phase)
        if next_phase == ColdStartPhase.COMPLETE:
            state.current_phase = ColdStartPhase.COMPLETE
        else:
            state.current_phase = next_phase

        return state

    # ------------------------------------------------------------------
    # 熔断降级: 贝叶斯融合
    # ------------------------------------------------------------------

    def execute_fusion(self, state: ColdStartState) -> Dict[int, Any]:
        """执行贝叶斯先验融合，填补缺失维度。

        Args:
            state: 当前冷启动状态。

        Returns:
            {dim: inferred_value} 映射。
        """
        fused = self._fusion_engine.execute_full_fusion(state.dimensions_status)

        # 将融合结果标记到各维度
        for dim, value in fused.items():
            state.mark_dimension_collected(dim, value)
            state.responses_history.append({
                "epoch": state.epoch_counter,
                "dimension": dim,
                "phase": "fusion_fallback",
                "answer": value,
                "inferred": True,
            })

        state.current_phase = ColdStartPhase.COMPLETE
        state.fusion_triggered = True

        return fused

    # ------------------------------------------------------------------
    # 将 ColdStartState 的结果注入 AgentState
    # ------------------------------------------------------------------

    def apply_to_agent_state(
        self, cold_state: ColdStartState, agent_state: AgentState
    ) -> AgentState:
        """将冷启动收集/融合的 6 维画像应用到 AgentState。

        执行映射:
          - 维度 1 (认知风格) → StaticProfile.cognitive_style_distribution
          - 维度 2 (动机)     → StaticProfile.motivation
          - 维度 5 (时间)     → StaticProfile.time_budget_hours_per_week
          - 维度 6 (知识基础) → StaticProfile.knowledge_base

        Args:
            cold_state: 已完成的冷启动状态。
            agent_state: 待填充的 AgentState。

        Returns:
            填充后的 AgentState。
        """
        sp = agent_state.static_profile

        # 维度 1: 认知风格 → Beta 分布 alpha/beta 参数化
        dim1 = cold_state.dimensions_status.get(1)
        if dim1 and dim1.collected and dim1.value:
            value = dim1.value
            # 检查是否是贝叶斯融合的结果
            if isinstance(value, dict) and "distribution" in value:
                dist = value["distribution"]
                style = value.get("preferred_style", "textual")
            else:
                style = str(value) if isinstance(value, str) else "textual"
                dist = {"visual": 0.33, "textual": 0.33, "practical": 0.34}

            # 将概率映射到 Beta 参数 (alpha = strength*10, beta = (1-strength)*10)
            vis_strength = dist.get("visual", 0.33)
            txt_strength = dist.get("textual", 0.33)
            prac_strength = dist.get("practical", 0.34)

            sp.cognitive_style_distribution = CognitiveStyleDistribution(
                visual_alpha=max(1.0, vis_strength * 15),
                visual_beta=max(1.0, (1 - vis_strength) * 15),
                textual_alpha=max(1.0, txt_strength * 15),
                textual_beta=max(1.0, (1 - txt_strength) * 15),
                practical_alpha=max(1.0, prac_strength * 15),
                practical_beta=max(1.0, (1 - prac_strength) * 15),
            )

        # 维度 2: 动机
        dim2 = cold_state.dimensions_status.get(2)
        if dim2 and dim2.collected and dim2.value:
            if isinstance(dim2.value, dict) and "motivation" in dim2.value:
                sp.motivation = dim2.value["motivation"]
            elif isinstance(dim2.value, str):
                sp.motivation = dim2.value

        # 维度 5: 时间预算
        dim5 = cold_state.dimensions_status.get(5)
        if dim5 and dim5.collected and dim5.value:
            if isinstance(dim5.value, dict) and "time_budget_hours_per_week" in dim5.value:
                sp.time_budget_hours_per_week = dim5.value["time_budget_hours_per_week"]
            elif isinstance(dim5.value, (int, float)):
                sp.time_budget_hours_per_week = float(dim5.value)

        # 维度 6: 已有知识基础
        dim6 = cold_state.dimensions_status.get(6)
        if dim6 and dim6.collected and dim6.value:
            if isinstance(dim6.value, dict) and "knowledge_base" in dim6.value:
                sp.knowledge_base = dim6.value["knowledge_base"]
            elif isinstance(dim6.value, list):
                sp.knowledge_base = dim6.value

        # 同步 c_epoch
        agent_state.c_epoch = cold_state.epoch_counter

        return agent_state

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _phase_to_dimension(phase: ColdStartPhase) -> int:
        """将阶段映射到维度编号。"""
        mapping = {
            ColdStartPhase.PROBE_COGNITIVE_STYLE: 1,
            ColdStartPhase.PROBE_MOTIVATION: 2,
            ColdStartPhase.PROBE_BACKGROUND: 3,
            ColdStartPhase.PROBE_EDUCATION: 4,
            ColdStartPhase.PROBE_TIME_BUDGET: 5,
            ColdStartPhase.PROBE_KNOWLEDGE_BASE: 6,
        }
        return mapping.get(phase, -1)

    @staticmethod
    def _get_next_phase(current: ColdStartPhase) -> ColdStartPhase:
        """获取下一个冷启动阶段。"""
        order = [
            ColdStartPhase.INIT,
            ColdStartPhase.PROBE_COGNITIVE_STYLE,
            ColdStartPhase.PROBE_MOTIVATION,
            ColdStartPhase.PROBE_BACKGROUND,
            ColdStartPhase.PROBE_EDUCATION,
            ColdStartPhase.PROBE_TIME_BUDGET,
            ColdStartPhase.PROBE_KNOWLEDGE_BASE,
            ColdStartPhase.COMPLETE,
        ]
        try:
            idx = order.index(current)
            return order[idx + 1] if idx + 1 < len(order) else ColdStartPhase.COMPLETE
        except ValueError:
            return ColdStartPhase.COMPLETE


# ============================================================================
# 顶层入口函数: handle_cold_start_interaction
# ============================================================================

def handle_cold_start_interaction(
    agent_state: AgentState,
    user_response: Optional[Any] = None,
) -> Tuple[AgentState, Optional[SituationProbe], bool]:
    """冷启动交互入口函数 — 供 LangGraph Coordinator Node 调用。

    每轮调用执行一次状态机转移：
      1. 若首次调用 (c_epoch==0) → 初始化冷启动引擎，返回第一个探针
      2. 若传入 user_response → 处理回答，前进状态机
      3. 检查是否完成或触发熔断

    Args:
        agent_state: 当前 LangGraph AgentState。
        user_response: 用户对上一轮探针的回答 (None if 首次调用)。

    Returns:
        (agent_state, next_probe, is_complete) 三元组:
          - agent_state: 更新后的状态。
          - next_probe: 下一轮探针 (若 is_complete=False) 或 None。
          - is_complete: 冷启动是否已完成。

    Raises:
        ValueError: 如果 user_response 格式不合法。
    """
    engine: ColdStartEngine
    cold_state: ColdStartState
    cold_start_key = "__cold_start_state__"

    if cold_start_key not in agent_state.internal_state:
        # 首次初始化
        engine = ColdStartEngine()
        cold_state = engine.initialize(agent_state.user_id)
        agent_state.internal_state[cold_start_key] = cold_state.model_dump()
        agent_state.c_epoch = 0
    else:
        # 恢复冷启动状态
        engine = ColdStartEngine()
        cold_state = ColdStartState(**agent_state.internal_state[cold_start_key])

    # ---- 同步 AgentState epoch 到冷启动状态 ----
    cold_state.epoch_counter = agent_state.c_epoch

    # ---- 处理用户回答 ----
    if user_response is not None and cold_state.current_probe is not None:
        cold_state = engine.process_response(cold_state, user_response)
        # 成功回答后不递增 epoch（epoch 由上层在用户无应答/跳过时手动驱动）
    elif user_response is not None and cold_state.current_probe is None:
        # 用户尝试回答但无待处理探针 → 可能处于 INIT 或已完成
        # 递增 epoch 以追踪无效应答
        agent_state.c_epoch += 1
        cold_state.epoch_counter = agent_state.c_epoch

    # ---- 检查是否需要熔断 (epoch >= 3 且维度未齐) ----
    if cold_state.should_fuse():
        fused = engine.execute_fusion(cold_state)
        agent_state.record_error(
            f"冷启动熔断降级: c_epoch={cold_state.epoch_counter}, "
            f"已收集={cold_state.collected_dimensions}/6, "
            f"贝叶斯融合维度={list(fused.keys())}"
        )
        agent_state = engine.apply_to_agent_state(cold_state, agent_state)
        agent_state.internal_state[cold_start_key] = cold_state.model_dump()
        return agent_state, None, True

    # ---- 检查完成 ----
    if cold_state.current_phase == ColdStartPhase.COMPLETE:
        agent_state = engine.apply_to_agent_state(cold_state, agent_state)
        agent_state.internal_state.pop(cold_start_key, None)
        return agent_state, None, True

    # ---- 获取下一轮探针 ----
    next_probe = engine.get_next_probe(cold_state)
    if next_probe is None:
        # 可能触发了熔断（get_next_probe 内部检测 should_fuse）
        if cold_state.fusion_triggered:
            fused = engine.execute_fusion(cold_state)
            agent_state.record_error(
                f"冷启动熔断降级 (probe阶段): c_epoch={cold_state.epoch_counter}, "
                f"已收集={cold_state.collected_dimensions}/6"
            )
        agent_state = engine.apply_to_agent_state(cold_state, agent_state)
        agent_state.internal_state.pop(cold_start_key, None)
        return agent_state, None, True

    # ---- 持久化冷启动状态 ----
    agent_state.internal_state[cold_start_key] = cold_state.model_dump()
    agent_state.c_epoch = cold_state.epoch_counter

    return agent_state, next_probe, False
