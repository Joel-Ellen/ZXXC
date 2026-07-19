"""Structured model invocation, parsing and deterministic fallback generation."""

from __future__ import annotations

import concurrent.futures
import json
import inspect
import re
import time
from dataclasses import dataclass, replace
from typing import Any

from src.validation.language import (
    is_chinese_learning_content,
    non_chinese_resource_fields,
)

from .context import ResourceContext
from .prompts import TOKEN_BUDGETS, build_card_messages, build_supporting_bundle_messages, render_markdown
from .validator import ResourcePayloadValidation, validate_resource_payload


# 模板回退卡片的可见标识。resource_service 与 orchestration_runtime 复用同一
# 常量做前缀判断，不要在别处重新定义这段文本。
TEMPLATE_NOTICE = "> 生成状态：本地回退模板。此卡片并非由模型生成。\n\n"


@dataclass(frozen=True)
class GeneratedResourcePayload:
    card_type: str
    structured_payload: dict[str, Any]
    body_markdown: str
    source: str
    provider: str | None = None
    model: str | None = None
    attempt_count: int = 1
    fallback_reason: str | None = None
    validation_issues: tuple[str, ...] = ()
    elapsed_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0

    def generation_metadata(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source": self.source,
            "attempt_count": self.attempt_count,
            "elapsed_ms": self.elapsed_ms,
        }
        if self.provider:
            data["provider"] = self.provider
        if self.model:
            data["model"] = self.model
        if self.fallback_reason:
            data["fallback_reason"] = self.fallback_reason
        if self.validation_issues:
            data["validation_issue_codes"] = list(self.validation_issues)
        return data


def extract_json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return dict(value)
    raw = str(value or "").strip()
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _model_name(llm: Any) -> str | None:
    config = getattr(llm, "config", None)
    if isinstance(config, dict):
        name = str(config.get("model") or "").strip()
        return name or None
    return None


def _usage_tokens(result: Any) -> tuple[int, int]:
    usage = result.get("usage") if isinstance(result, dict) else None
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0))
    output_tokens = usage.get(
        "completion_tokens",
        usage.get("output_tokens", 0),
    )
    try:
        safe_input = max(0, int(input_tokens or 0))
    except (TypeError, ValueError):
        safe_input = 0
    try:
        safe_output = max(0, int(output_tokens or 0))
    except (TypeError, ValueError):
        safe_output = 0
    return safe_input, safe_output


def _source_ref_ids(context: ResourceContext) -> list[str]:
    return context.grounding_ref_ids[:3] or [f"course:{context.course_id}:{context.node_id}"]


def _bind_source_ref_ids(payload: dict[str, Any], context: ResourceContext) -> list[str]:
    """Retain only server-known citations and require supplied grounding refs.

    A provider may select among retrieved source IDs, but it cannot replace
    those citations with the synthetic course-node ID or an invented reference.
    When it fails to nominate a retrieved source, the service attaches the
    bounded default evidence set instead of allowing a weak ``setdefault``
    escape hatch.
    """
    raw_ids = payload.get("source_ref_ids")
    proposed = raw_ids if isinstance(raw_ids, list) else []
    known = set(context.grounding_ref_ids)
    selected = list(dict.fromkeys(
        str(ref_id).strip()
        for ref_id in proposed
        if str(ref_id).strip() in known
    ))
    if known:
        if context.content_version.startswith("resource-v4"):
            return selected[:5]
        return selected[:5] or _source_ref_ids(context)

    # A context without retrieved evidence remains compatible with legacy
    # course-node-only generation, but unknown provider IDs are still removed.
    course_id = f"course:{context.course_id}:{context.node_id}"
    return [course_id] if course_id in {
        str(ref.get("id") or "").strip()
        for ref in context.source_refs
        if isinstance(ref, dict)
    } else _source_ref_ids(context)


def _mastery_bucket_label(bucket: str) -> str:
    """Map internal mastery bucket keys to Chinese display labels."""
    return {
        "foundational": "基础",
        "developing": "发展",
        "proficient": "熟练",
        "advanced": "进阶",
    }.get(bucket, bucket)


def _template_display_name(value: Any, fallback: str) -> str:
    """Localize context-owned labels without treating English prose as a name."""
    raw = str(value or "").strip()
    if not raw:
        return fallback
    if is_chinese_learning_content(raw, allow_name_only=True):
        return raw
    localized = f"{fallback}（{raw}）"
    return localized if is_chinese_learning_content(localized) else fallback


def _template_topic_title(context: ResourceContext) -> str:
    raw = str(context.node_title or "").strip()
    if raw and is_chinese_learning_content(raw, allow_name_only=True):
        return raw
    if raw:
        localized = f"当前知识点（{raw}）"
        if is_chinese_learning_content(localized):
            return localized
    return f"当前知识点（{context.node_id}）" if context.node_id else "当前知识点"


def _template_blueprint(context: ResourceContext) -> dict[str, Any]:
    if context.blueprint_snapshot:
        snapshot = dict(context.blueprint_snapshot)
        if not non_chinese_resource_fields({"learning_blueprint": snapshot}):
            return snapshot
    refs = _source_ref_ids(context)
    objective_id = f"obj:{context.node_id}:core"
    title = _template_topic_title(context)
    return {
        "version": "resource-blueprint-v1",
        "objectives": [
            {
                "id": objective_id,
                "text": f"解释{title}的定义、成立条件与边界。",
            }
        ],
        "claims": [
            {
                "id": f"claim:{context.node_id}:definition",
                "text": f"{title}必须根据课程证据中的定义和约束来解释。",
                "critical": True,
                "evidence_ids": refs[:2],
            }
        ],
        "terms": [title],
        "misconceptions": ["只记忆术语而不检查成立条件。"],
        "examples": [f"用一个小规模输入追踪{title}的状态变化。"],
        "boundaries": ["检查空输入、最小输入和违反前提的输入。"],
        "difficulty_strategy": (
            f"面向{_mastery_bucket_label(context.mastery_bucket)}阶段，先解释约束，再给出可复核例子。"
        ),
        "card_roles": {
            "concept_map": "建立定义、机制和边界",
            "code_snippet": "用独立例子验证机制",
            "interactive_exercise": "针对错误标签进行练习",
            "video_summary": "组织可信媒体或阅读顺序",
            "diagnostic_quiz": "诊断概念到迁移能力",
        },
    }


def _template_common(
    context: ResourceContext,
    *,
    evidence_fields: list[str],
    blueprint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    refs = _source_ref_ids(context)
    blueprint = blueprint if blueprint is not None else _template_blueprint(context)
    objective_ids = [
        str(value.get("id") or "")
        for value in blueprint.get("objectives", [])
        if isinstance(value, dict) and str(value.get("id") or "")
    ]
    return {
        "title": _template_topic_title(context),
        "source_ref_ids": refs,
        "objective_ids": objective_ids,
        "evidence_map": {field: refs[:2] for field in evidence_fields},
        "language": context.locale,
        "content_language": context.locale,
        "quality_profile": {
            "status": (
                "degraded"
                if context.evidence_status == "degraded"
                else "template"
            ),
            "evidence_status": context.evidence_status,
        },
    }


def _template_payload(context: ResourceContext, card_type: str) -> dict[str, Any]:
    title = _template_topic_title(context)
    if card_type == "concept_map":
        blueprint = _template_blueprint(context)
        common = _template_common(
            context,
            evidence_fields=["summary", "definition", "constraints", "mechanism"],
            blueprint=blueprint,
        )
        return {
            **common,
            "render_type": card_type,
            "summary": f"先依据课程证据识别{title}的核心约束，再选择实现方法。",
            "definition": f"{title}应从不变量、成立条件和适用边界三个方面解释。",
            "constraints": ["应用该概念前，必须先说明输入假设和成立条件。"],
            "mechanism": ["逐步跟踪维持核心不变量的状态变化。"],
            "prerequisites": [
                _template_display_name(item.get("title"), "课程前置知识")
                for item in context.prerequisite_nodes[:2]
            ] or ["上一课程节点的基础知识"],
            "learning_objectives": [f"能够解释{title}背后的约束并检查边界。"],
            "sections": [{"heading": "运行机制", "body": f"把{title}中的每一步操作与它所保持的不变量对应起来。"}],
            "bullets": ["依次检查前提、状态变化和边界情况。"],
            "common_misconceptions": ["只记住操作步骤，却不检查操作成立的前提。"],
            "counterexamples": ["违反必要前提的输入不能直接套用同一种方法。"],
            "transfer_questions": [f"哪个新问题与{title}共享相同的核心约束？"],
            "review_prompts": ["说出核心不变量，并验证一个边界输入。"],
            "mermaid_source": "graph TD\nA[前置知识] --> B[定义]\nB --> C[约束]\nC --> D[机制]\nD --> E[应用]",
            "learning_blueprint": blueprint,
        }
    if card_type == "code_snippet":
        common = _template_common(
            context,
            evidence_fields=["scenario", "explanation", "complexity_notes"],
        )
        practice_id = str(context.code_practice.get("problem_id") or "")
        return {
            **common,
            "render_type": card_type,
            "language": "python",
            "scenario": f"用一个与正式练习不同的小例子，执行并跟踪{title}。",
            "prerequisites": ["运行前先阅读输入契约并确认边界。"],
            "code": "def apply_concept(items):\n    if items is None:\n        return []\n    return list(items)",
            "boundary_tests": [
                {"name": "空输入", "input": "[]", "expected": "[]"},
            ],
            "walkthrough_steps": ["先检查输入边界，再执行数据转换。"],
            "explanation": "该预验证示例显式保留输入契约，并产生确定性输出。",
            "complexity_notes": ["复制序列需要 O(n) 时间和 O(n) 额外空间。"],
            "pitfalls": ["未检查契约就假设输入一定存在。"],
            "experiments": ["增加单元素测试，并说明执行过程中保持的不变量。"],
            "example_binding": f"example:{context.node_id}:resource-v4",
            "practice_id": practice_id,
            "verification": {
                "status": "prevalidated_template",
                "runtime": "local_template",
            },
        }
    if card_type == "interactive_exercise":
        common = _template_common(
            context,
            evidence_fields=["goal", "prompt", "solution_outline"],
        )
        return {
            **common,
            "render_type": card_type,
            "goal": f"根据约束选择{title}，而不是机械套用记忆模板。",
            "error_signature": context.error_signature,
            "prompt": f"写出{title}的不变量，再分别用一个普通输入和一个边界输入验证。",
            "steps": ["说明输入假设。", "写出核心不变量。", "跟踪普通情况。", "跟踪边界情况。"],
            "checkpoints": ["每一步操作后，核心不变量仍然成立。"],
            "hints": ["先找出必须保持的状态。", "把边界轨迹与普通轨迹并排比较。"],
            "solution_outline": "先把成立条件映射到不变量，再用状态轨迹逐步验证。",
            "expected_outcome": "形成一段简短、可复核的适用条件说明。",
            "rubric": [
                {
                    "criterion": "准确说明成立条件和不变量",
                    "points": 60,
                    "evidence": "答案明确给出前提并在轨迹中保持不变量。",
                },
                {
                    "criterion": "覆盖边界输入",
                    "points": 40,
                    "evidence": "答案单独检查至少一个边界情况。",
                },
            ],
            "structured_checkpoints": [
                {
                    "id": "检查点-条件",
                    "prompt": "当前方法成立需要哪些条件？",
                    "expected_signal": "列出输入前提和核心不变量。",
                },
                {
                    "id": "检查点-边界",
                    "prompt": "边界输入是否仍满足这些条件？",
                    "expected_signal": "明确接受、拒绝或单独处理边界。",
                },
            ],
            "hint_levels": {
                "level_1": "先写出定义中的访问或状态约束。",
                "level_2": "逐步标记每次操作前后的关键状态。",
                "level_3": "把正常输入和最小边界输入并排比较。",
            },
        }
    if card_type == "video_summary":
        trusted_video = next(
            (
                ref
                for ref in context.knowledge_refs
                if str(ref.get("video_url") or "")
                and str(ref.get("video_source_id") or ref.get("id") or "")
            ),
            None,
        )
        if trusted_video and non_chinese_resource_fields({
            "timeline": list(trusted_video.get("timeline") or []),
        }):
            trusted_video = None
        common = _template_common(
            context,
            evidence_fields=["summary", "key_points", "reading_sequence"],
        )
        return {
            **common,
            "render_type": card_type,
            "summary": f"围绕{title}的定义、状态变化和边界组织可信媒体或阅读材料。",
            "key_points": ["先识别不变量，再阅读实现细节。"],
            "timeline": (
                list(trusted_video.get("timeline") or [])
                if trusted_video
                else []
            ),
            "watch_focus": ["状态发生变化时暂停，并预测下一步。"],
            "review_questions": [f"哪个条件决定{title}是否适用？"],
            "duration_minutes": (
                int(trusted_video.get("duration_minutes") or 0)
                if trusted_video
                else 0
            ),
            "video_url": trusted_video.get("video_url") if trusted_video else None,
            "video_source_id": (
                trusted_video.get("video_source_id") or trusted_video.get("id")
                if trusted_video
                else None
            ),
            "media_status": "trusted_video" if trusted_video else "no_trusted_video",
            "reading_sequence": [
                "先阅读定义与成立条件。",
                "再跟踪机制和状态变化。",
                "最后检查边界、反例与误区。",
            ],
        }
    common = _template_common(
        context,
        evidence_fields=["questions", "after_quiz_guidance"],
    )
    blueprint = _template_blueprint(context)
    terms = [str(t).strip() for t in blueprint.get("terms", []) if str(t).strip()]
    topic_term = terms[0] if terms else title
    misconceptions = [
        str(m).strip()
        for m in blueprint.get("misconceptions", [])
        if str(m).strip()
    ]
    boundaries = [
        str(b).strip()
        for b in blueprint.get("boundaries", [])
        if str(b).strip()
    ]

    # Each distractor is a plausible but factually incorrect *technical* claim
    # about the topic — never a piece of meta-cognitive or study-skills advice.
    _DISTRACTOR_POOL: list[str] = [
        f"{topic_term}支持在任意位置插入或删除元素。",
        f"{topic_term}的操作规则与队列完全相同。",
        f"对空{topic_term}执行删除操作会静默返回0。",
        f"{topic_term}的核心不变量在所有输入下都自动成立。",
        f"{topic_term}的效率与具体实现方式无关，总是O(1)。",
        f"所有涉及{topic_term}的问题都可用同一种算法模板解决。",
        f"{topic_term}的边界情况不需要单独处理。",
        f"只要输入合法，{topic_term}就不会产生任何错误。",
    ]

    def _pick_distractors(correct_answer: str, *, offset: int = 0, count: int = 3) -> list[str]:
        picked: list[str] = []
        pool_size = len(_DISTRACTOR_POOL)
        start = offset % pool_size
        for i in range(pool_size):
            d = _DISTRACTOR_POOL[(start + i) % pool_size]
            if d != correct_answer and d not in picked:
                picked.append(d)
            if len(picked) >= count:
                break
        # If the pool is exhausted (very unlikely), fill with structural variants.
        fallback_idx = 0
        while len(picked) < count:
            fallback_idx += 1
            fb = f"将{topic_term}的核心规则错误地套用到不相关的场景（模板回退#{fallback_idx}）。"
            if fb not in picked and fb != correct_answer:
                picked.append(fb)
        return picked

    # Chinese display labels for schema-level enum values.
    _LEVEL_LABEL: dict[str, str] = {
        "concept": "概念",
        "understanding": "理解",
        "application": "应用",
        "boundary": "边界",
        "transfer": "迁移",
    }
    _LEVEL_SKILL_TAG: dict[str, str] = {
        "concept": f"{topic_term}概念",
        "understanding": f"{topic_term}机制",
        "application": f"{topic_term}应用",
        "boundary": f"{topic_term}边界",
        "transfer": f"{topic_term}迁移",
    }

    levels = [
        (
            "concept",
            "哪项描述最符合{topic}的核心定义？",
            f"准确描述{topic_term}的核心定义、成立条件与适用边界。",
        ),
        (
            "understanding",
            "在{topic}中，哪项操作能正确保持其核心不变量？",
            f"正确维持{topic_term}不变量的操作序列或状态转移。",
        ),
        (
            "application",
            "面对一个需要{topic}的典型输入，应首先做什么？",
            f"先检查{topic_term}的输入前提与适用条件，再按约束执行操作。",
        ),
        (
            "boundary",
            "在{topic}中，当前提条件不成立时应如何处理？",
            f"显式判断{topic_term}的前提是否成立，不成立则拒绝操作或采用单独的处理路径。",
        ),
        (
            "transfer",
            "以下哪个新场景与{topic}共享相同的核心约束？",
            f"准确识别出与{topic_term}共享相同结构约束或不变量的新问题场景。",
        ),
    ]

    questions_payload: list[dict[str, Any]] = []
    for q_idx, (level, prompt_template, correct_answer) in enumerate(levels):
        prompt_text = prompt_template.format(topic=topic_term)
        question_distractors = _pick_distractors(correct_answer, offset=q_idx * 3)
        label = _LEVEL_LABEL.get(level, level)
        skill = _LEVEL_SKILL_TAG.get(level, level)
        questions_payload.append({
            "id": f"{context.node_id}-{label}-v1",
            "level": level,
            "prompt": prompt_text,
            "options": [correct_answer] + question_distractors,
            "answer_index": 0,
            "explanation": f"正确选项直接关联{topic_term}的{label}维度，需根据课程证据中的定义和约束来判断。",
            "skill_tag": skill,
            "error_tags": [f"{label}误解"],
            "distractor_error_tags": {
                "1": f"{label}干扰项一",
                "2": f"{label}干扰项二",
                "3": f"{label}干扰项三",
            },
            "difficulty": (
                "easy"
                if level == "concept"
                else "hard"
                if level in {"boundary", "transfer"}
                else "medium"
            ),
        })

    return {
        **common,
        "render_type": "diagnostic_quiz",
        "questions": questions_payload,
        "pass_threshold": 0.65,
        "after_quiz_guidance": (
            f"重新作答前，请先回顾{topic_term}的概念图，并完整跟踪一个边界用例。"
        ),
    }


class ResourceGenerator:
    """One structured generator shared by synchronous compatibility and jobs."""

    def _bind_context(
        self,
        payload: dict[str, Any],
        context: ResourceContext,
        card_type: str,
        *,
        source: str,
    ) -> dict[str, Any]:
        bound = dict(payload or {})
        bound["render_type"] = card_type
        bound.setdefault("title", context.node_title)
        bound["source_ref_ids"] = _bind_source_ref_ids(bound, context)
        bound["quality_profile"] = {
            "generation_source": source,
            "status": "pending" if source == "llm" else "template",
        }
        if card_type == "code_snippet":
            bound["practice_id"] = str(
                context.code_practice.get("problem_id") or ""
            )
            bound["example_binding"] = (
                f"example:{context.node_id}:resource-v4"
            )
            bound["verification"] = {
                "status": (
                    "prevalidated_template"
                    if source == "template"
                    else "unverified"
                )
            }
        return bound

    def _result_from_payload(
        self,
        card_type: str,
        payload: dict[str, Any],
        context: ResourceContext,
        *,
        source: str,
        provider: str | None = None,
        model: str | None = None,
        fallback_reason: str | None = None,
        elapsed_ms: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> GeneratedResourcePayload:
        bound = self._bind_context(
            payload,
            context,
            card_type,
            source=source,
        )
        validation: ResourcePayloadValidation = validate_resource_payload(card_type, bound, context)
        if validation.valid and validation.payload is not None:
            markdown = render_markdown(card_type, validation.payload)
            if source == "template":
                markdown = TEMPLATE_NOTICE + markdown
            return GeneratedResourcePayload(
                card_type=card_type,
                structured_payload=validation.payload,
                body_markdown=markdown,
                source=source,
                provider=provider,
                model=model,
                fallback_reason=fallback_reason,
                elapsed_ms=elapsed_ms,
                input_tokens=max(0, int(input_tokens)),
                output_tokens=max(0, int(output_tokens)),
            )
        codes = tuple(issue.code for issue in validation.issues)
        fallback = _template_payload(context, card_type)
        fallback_validation = validate_resource_payload(card_type, fallback, context)
        # Template payloads are authored locally and kept valid. This guard
        # prevents a malformed future template from leaking an invalid card.
        if not fallback_validation.valid or fallback_validation.payload is None:
            raise RuntimeError(f"Local fallback validation failed for {card_type}: {codes}")
        return GeneratedResourcePayload(
            card_type=card_type,
            structured_payload=fallback_validation.payload,
            body_markdown=TEMPLATE_NOTICE + render_markdown(card_type, fallback_validation.payload),
            source="template",
            provider=provider,
            model=model,
            fallback_reason=fallback_reason or "local_validation_failed",
            validation_issues=codes,
            elapsed_ms=elapsed_ms,
            input_tokens=max(0, int(input_tokens)),
            output_tokens=max(0, int(output_tokens)),
        )

    def template(self, context: ResourceContext, card_type: str, reason: str = "no_eligible_provider") -> GeneratedResourcePayload:
        return self._result_from_payload(
            card_type,
            _template_payload(context, card_type),
            context,
            source="template",
            fallback_reason=reason,
        )

    @staticmethod
    def _chat_sync(
        llm: Any,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        timeout_sec: float | None,
    ) -> Any:
        call = llm.chat_sync
        kwargs: dict[str, Any] = {
            "temperature": 0.25,
            "max_tokens": max_tokens,
            "json_mode": True,
        }
        try:
            parameters = inspect.signature(call).parameters.values()
            if timeout_sec is not None and any(
                parameter.name == "timeout_sec" or parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters
            ):
                kwargs["timeout_sec"] = timeout_sec
        except (TypeError, ValueError):
            pass
        return call(messages, **kwargs)

    def generate(
        self,
        llm: Any,
        context: ResourceContext,
        card_type: str,
        *,
        max_tokens: int | None = None,
        timeout_sec: float | None = 22.0,
    ) -> GeneratedResourcePayload:
        started = time.monotonic()
        try:
            result = self._chat_sync(
                llm,
                build_card_messages(context, card_type),
                max_tokens=max_tokens or TOKEN_BUDGETS[card_type],
                timeout_sec=timeout_sec,
            )
            content = result.get("content", "") if isinstance(result, dict) else result
            input_tokens, output_tokens = _usage_tokens(result)
            payload = extract_json_object(content)
            if payload is None:
                return replace(
                    self.template(context, card_type, "invalid_json"),
                    provider=str(getattr(llm, "provider", "") or "") or None,
                    model=_model_name(llm),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            return self._result_from_payload(
                card_type,
                payload,
                context,
                source="llm",
                provider=str(getattr(llm, "provider", "") or "") or None,
                model=_model_name(llm),
                elapsed_ms=round((time.monotonic() - started) * 1000, 3),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        except Exception as exc:
            return self.template(context, card_type, f"provider_error:{type(exc).__name__}")

    def generate_bundle(
        self,
        llm: Any,
        context: ResourceContext,
        card_types: list[str],
        *,
        max_tokens: int | None = None,
        timeout_sec: float | None = 20.0,
    ) -> dict[str, GeneratedResourcePayload]:
        requested = list(dict.fromkeys(card_type for card_type in card_types if card_type != "concept_map"))
        if not requested:
            return {}

        groups = [
            [
                card_type
                for card_type in ("code_snippet", "video_summary")
                if card_type in requested
            ],
            [
                card_type
                for card_type in ("interactive_exercise", "diagnostic_quiz")
                if card_type in requested
            ],
        ]
        groups = [group for group in groups if group]
        if len(groups) > 1:
            outputs: dict[str, GeneratedResourcePayload] = {}
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=2,
                thread_name_prefix="resource-v4-supporting",
            ) as pool:
                futures = {
                    tuple(group): pool.submit(
                        self._generate_bundle_once,
                        llm,
                        context,
                        group,
                        max_tokens=(
                            TOKEN_BUDGETS["code_media_bundle"]
                            if "code_snippet" in group
                            else TOKEN_BUDGETS["practice_diagnostic_bundle"]
                        ),
                        timeout_sec=timeout_sec,
                    )
                    for group in groups
                }
                for group, future in futures.items():
                    try:
                        outputs.update(future.result())
                    except Exception:
                        for card_type in group:
                            outputs[card_type] = self.template(
                                context,
                                card_type,
                                "supporting_subpackage_failed",
                            )
            return outputs
        return self._generate_bundle_once(
            llm,
            context,
            requested,
            max_tokens=max_tokens or TOKEN_BUDGETS["supporting_bundle"],
            timeout_sec=timeout_sec,
        )

    def _generate_bundle_once(
        self,
        llm: Any,
        context: ResourceContext,
        requested: list[str],
        *,
        max_tokens: int,
        timeout_sec: float | None,
    ) -> dict[str, GeneratedResourcePayload]:
        started = time.monotonic()
        try:
            result = self._chat_sync(
                llm,
                build_supporting_bundle_messages(context, requested),
                max_tokens=max_tokens,
                timeout_sec=timeout_sec,
            )
            content = result.get("content", "") if isinstance(result, dict) else result
            input_tokens, output_tokens = _usage_tokens(result)
            raw_bundle = extract_json_object(content) or {}
        except Exception:
            raw_bundle = {}
            input_tokens = 0
            output_tokens = 0
        elapsed_ms = round((time.monotonic() - started) * 1000, 3)
        provider = str(getattr(llm, "provider", "") or "") or None
        model = _model_name(llm)
        outputs: dict[str, GeneratedResourcePayload] = {}
        card_count = max(1, len(requested))
        for index, card_type in enumerate(requested):
            allocated_input = (
                input_tokens // card_count
                + (1 if index < input_tokens % card_count else 0)
            )
            allocated_output = (
                output_tokens // card_count
                + (1 if index < output_tokens % card_count else 0)
            )
            payload = raw_bundle.get(card_type)
            if not isinstance(payload, dict):
                outputs[card_type] = replace(
                    self.template(
                        context,
                        card_type,
                        "bundle_missing_card",
                    ),
                    provider=provider,
                    model=model,
                    input_tokens=allocated_input,
                    output_tokens=allocated_output,
                )
                continue
            outputs[card_type] = self._result_from_payload(
                card_type,
                payload,
                context,
                source="llm",
                provider=provider,
                model=model,
                elapsed_ms=elapsed_ms,
                input_tokens=allocated_input,
                output_tokens=allocated_output,
            )
        return outputs
