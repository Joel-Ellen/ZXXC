# -*- coding: utf-8 -*-
"""
Assessment reporter node.

This cleaned version preserves the original public API while centralizing
LLM-based report generation through the prompt adapter layer.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
from pydantic import BaseModel, Field

from .prompt_adapters import patch_assessment_node_class


RADAR_DIM_CONCEPT = 0
RADAR_DIM_CODE = 1
RADAR_DIM_LOGIC = 2
RADAR_DIM_RESILIENCE = 3
RADAR_DIM_TIME = 4

RADAR_DIM_NAMES = [
    "概念理解力",
    "代码工程力",
    "逻辑推理力",
    "错题抗挫力",
    "时间管理力",
]

STRATEGY_STANDARD = "STANDARD_PATH"
STRATEGY_SCAFFOLD = "SCAFFOLD_HELP"
STRATEGY_EDGE_CASE = "EDGE_CASE_DRILL"


class AssessmentInput(BaseModel):
    agent_state: Any = Field(..., description="Current agent state snapshot")


class AssessmentOutput(BaseModel):
    agent_state: Any = Field(..., description="Updated agent state")


class CapabilityRadar(BaseModel):
    concept_understanding: float = Field(default=0.5, ge=0.0, le=1.0)
    code_engineering: float = Field(default=0.5, ge=0.0, le=1.0)
    logical_reasoning: float = Field(default=0.5, ge=0.0, le=1.0)
    error_resilience: float = Field(default=0.5, ge=0.0, le=1.0)
    time_management: float = Field(default=0.5, ge=0.0, le=1.0)

    def to_list(self) -> List[float]:
        return [
            self.concept_understanding,
            self.code_engineering,
            self.logical_reasoning,
            self.error_resilience,
            self.time_management,
        ]

    @classmethod
    def from_list(cls, values: List[float]) -> "CapabilityRadar":
        if len(values) != 5:
            raise ValueError(f"能力雷达必须包含 5 个值，实际收到 {len(values)} 个")
        return cls(
            concept_understanding=values[0],
            code_engineering=values[1],
            logical_reasoning=values[2],
            error_resilience=values[3],
            time_management=values[4],
        )

    def compute_mean(self) -> float:
        return float(np.mean(self.to_list()))

    def describe(self) -> str:
        labels = []
        for name, val in zip(RADAR_DIM_NAMES, self.to_list()):
            if val >= 0.80:
                label = "[A] 优秀"
            elif val >= 0.60:
                label = "[B] 良好"
            elif val >= 0.40:
                label = "[C] 待提升"
            else:
                label = "[D] 亟需加强"
            labels.append(f"{name}={val:.2f}({label})")
        return ", ".join(labels)


class HysteresisStrategyController:
    T_LOW: float = 0.40
    T_HIGH: float = 0.75
    FAIL_GATE: int = 2
    BOUNDARY_EMA_WINDOW: int = 3
    BOUNDARY_EMA_THRESHOLD: float = 0.5

    def decide(
        self,
        a_mix: float,
        current_strategy: str,
        fail_counter: int,
        boundary_miss_ema_sequence: List[float],
    ) -> str:
        new_strategy = current_strategy

        if (
            current_strategy != STRATEGY_SCAFFOLD
            and a_mix < self.T_LOW
            and fail_counter >= self.FAIL_GATE
        ):
            new_strategy = STRATEGY_SCAFFOLD
        elif (
            current_strategy in (STRATEGY_SCAFFOLD, STRATEGY_EDGE_CASE)
            and a_mix > self.T_HIGH
        ):
            new_strategy = STRATEGY_STANDARD
        elif current_strategy == STRATEGY_STANDARD and len(boundary_miss_ema_sequence) >= self.BOUNDARY_EMA_WINDOW:
            recent = boundary_miss_ema_sequence[-self.BOUNDARY_EMA_WINDOW:]
            if all(v > self.BOUNDARY_EMA_THRESHOLD for v in recent):
                new_strategy = STRATEGY_EDGE_CASE

        return new_strategy


class AssessmentReporterNode:
    DEFAULT_ALPHA: float = 0.2

    def __init__(
        self,
        alpha: float = 0.2,
        t_low: float = 0.40,
        t_high: float = 0.75,
        llm_client: Any = None,
    ) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError(f"alpha must be in (0, 1], got {alpha}")
        if not 0.0 <= t_low < t_high <= 1.0:
            raise ValueError("thresholds must satisfy 0 <= t_low < t_high <= 1")

        self.alpha = alpha
        self._llm = llm_client
        self._controller = HysteresisStrategyController()
        self._controller.T_LOW = t_low
        self._controller.T_HIGH = t_high

    @property
    def t_low(self) -> float:
        return self._controller.T_LOW

    @property
    def t_high(self) -> float:
        return self._controller.T_HIGH

    def __call__(self, inp: AssessmentInput) -> AssessmentOutput:
        return self.execute_evaluation(inp.agent_state)

    def execute_evaluation(self, state: Any) -> AssessmentOutput:
        dynamic_profile = state.dynamic_profile
        latest_behavior = state.latest_behavior

        x1 = getattr(latest_behavior, "accuracy_rate", 0.5) if latest_behavior else 0.5
        x2 = getattr(latest_behavior, "code_pass_rate", 0.5) if latest_behavior else 0.5
        x3 = getattr(latest_behavior, "duration_ratio", 1.0) if latest_behavior else 1.0

        current_radar = list(getattr(dynamic_profile, "capability_radar", [0.5, 0.5, 0.5, 0.5, 0.5]))
        if len(current_radar) != 5:
            current_radar = [0.5, 0.5, 0.5, 0.5, 0.5]

        scores = self._compute_dimension_scores(x1, x2, x3)

        updated_radar: List[float] = []
        for i in range(5):
            new_val = self.alpha * scores[i] + (1.0 - self.alpha) * current_radar[i]
            updated_radar.append(float(np.clip(new_val, 0.0, 1.0)))

        boundary_miss_seq = list(getattr(dynamic_profile, "boundary_miss_ema_sequence", []) or [])
        boundary_current = 0.0
        if latest_behavior and hasattr(latest_behavior, "error_types"):
            error_types = latest_behavior.error_types or []
            boundary_current = 1.0 if "boundary_miss" in error_types else 0.0
        boundary_ema = self._update_boundary_ema(boundary_miss_seq, boundary_current)
        if len(boundary_ema) > 10:
            boundary_ema = boundary_ema[-10:]

        a_mix = float(np.mean(updated_radar))
        current_strategy = getattr(state, "pedagogical_strategy", STRATEGY_STANDARD) or STRATEGY_STANDARD
        fail_counter = getattr(dynamic_profile, "continuous_fail_counter", 0) or 0

        new_strategy = self._controller.decide(
            a_mix=a_mix,
            current_strategy=current_strategy,
            fail_counter=fail_counter,
            boundary_miss_ema_sequence=boundary_ema,
        )

        diagnostic_report = self._generate_diagnostic_report(
            updated_radar, a_mix, new_strategy, current_strategy
        )

        dynamic_profile.capability_radar = updated_radar
        dynamic_profile.diagnostic_report_md = diagnostic_report
        dynamic_profile.boundary_miss_ema_sequence = boundary_ema
        state.pedagogical_strategy = new_strategy

        return AssessmentOutput(agent_state=state)

    def _compute_dimension_scores(
        self,
        accuracy: float,
        code_pass: float,
        duration_ratio: float,
    ) -> List[float]:
        logic_score = 1.0 - abs(1.0 - min(duration_ratio, 2.0))
        logic_score = max(0.0, min(1.0, logic_score))

        resilience_score = accuracy * 0.6 + code_pass * 0.4

        time_score = 1.0 - abs(1.0 - min(duration_ratio, 2.0)) * 0.5
        time_score = max(0.0, min(1.0, time_score))

        return [
            accuracy,
            code_pass,
            logic_score,
            resilience_score,
            time_score,
        ]

    def _update_boundary_ema(self, history: List[float], current: float) -> List[float]:
        if not history:
            return [current]
        smoothed = self.alpha * current + (1.0 - self.alpha) * history[-1]
        return history + [smoothed]

    def _generate_diagnostic_report(
        self,
        radar: List[float],
        a_mix: float,
        new_strategy: str,
        old_strategy: str,
    ) -> str:
        strategy_desc = {
            STRATEGY_STANDARD: "[标准] 标准进阶路径",
            STRATEGY_SCAFFOLD: "[辅助] 脚手架辅助模式",
            STRATEGY_EDGE_CASE: "[强化] 边界用例强化模式",
        }
        strategy_change = ""
        if new_strategy != old_strategy:
            strategy_change = f"\n* **策略切换**: `{old_strategy}` -> `{new_strategy}`"

        dim_lines = []
        for name, val in zip(RADAR_DIM_NAMES, radar):
            if val >= 0.80:
                diagnosis = "已达优秀水平，可适当增加挑战。"
            elif val >= 0.60:
                diagnosis = "处于良好区间，建议保持当前节奏。"
            elif val >= 0.40:
                diagnosis = "存在提升空间，建议增加针对性练习。"
            else:
                diagnosis = "亟需加强，系统建议降低难度并加强引导。"
            dim_lines.append(f"* **{name}**: {val:.2f} - {diagnosis}")

        if a_mix >= 0.75:
            grade = "[A] 优秀"
        elif a_mix >= 0.60:
            grade = "[B] 良好"
        elif a_mix >= 0.40:
            grade = "[C] 待提升"
        else:
            grade = "[D] 亟需加强"

        return (
            "### 学术能力综合评估报告\n\n"
            "#### 能力雷达分布\n"
            f"{chr(10).join(dim_lines)}\n\n"
            "#### 系统综合效能指数\n"
            f"* **A_mix**: {a_mix:.2f}（{grade}）\n\n"
            "#### 当前下发调控策略\n"
            f"* **策略**: `{new_strategy}` - {strategy_desc.get(new_strategy, '未知策略')}{strategy_change}"
        ).strip()

    def generate_llm_report(
        self,
        radar: List[float],
        a_mix: float,
        strategy: str,
        course_name: str = "",
        quiz_records: Any = None,
        study_time: float = 0,
        completed_tasks: int = 0,
    ) -> Dict[str, Any]:
        fallback_markdown = self._generate_diagnostic_report(radar, a_mix, strategy, strategy)
        return {
            "metrics": {"knowledge_mastery": a_mix},
            "current_level": strategy,
            "weak_areas": [RADAR_DIM_NAMES[i] for i, v in enumerate(radar) if v < 0.4],
            "strengths": [RADAR_DIM_NAMES[i] for i, v in enumerate(radar) if v >= 0.7],
            "suggestions": [],
            "radar_data": {"labels": RADAR_DIM_NAMES, "values": radar},
            "report_markdown": fallback_markdown,
        }

    def inject_llm(self, llm_client: Any):
        self._llm = llm_client


def create_assessment_node(
    alpha: float = 0.2,
    t_low: float = 0.40,
    t_high: float = 0.75,
    llm_client: Any = None,
) -> AssessmentReporterNode:
    return AssessmentReporterNode(alpha=alpha, t_low=t_low, t_high=t_high, llm_client=llm_client)


patch_assessment_node_class(AssessmentReporterNode)
