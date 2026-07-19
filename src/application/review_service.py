# -*- coding: utf-8 -*-
"""Durable, evidence-backed review and remediation workflow.

Review items are derived only from question outcomes produced by the server's
diagnostic verifier.  They are intentionally stored in ``AgentState`` so the
same session persistence mechanism restores the queue on another device.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from threading import Lock, RLock
from typing import Any, Iterable

from src.state.agent_state import AgentState

from ._common import MASTERY_ADVANCE_THRESHOLD, get_node_title, get_session, persist_session


REVIEW_ITEMS_KEY = "review_items"
MAX_REVIEW_ITEMS = 500
MAX_TREND_POINTS = 120
MASTERY_REINFORCEMENT_ENABLED = False

_REVIEW_LOCKS_GUARD = Lock()
_REVIEW_LOCKS: dict[tuple[str, str], RLock] = {}

_RESOURCE_LABELS = {
    "concept_map": "讲解材料",
    "code_snippet": "示例代码",
    "interactive_exercise": "相似题练习",
    "video_summary": "视频回顾",
    "diagnostic_quiz": "复测",
}
_RECOMMENDED_RESOURCE_TYPES = (
    "concept_map",
    "interactive_exercise",
    "code_snippet",
)


def _review_lock(user_id: str, course_id: str) -> RLock:
    key = (str(user_id), str(course_id))
    with _REVIEW_LOCKS_GUARD:
        lock = _REVIEW_LOCKS.get(key)
        if lock is None:
            lock = RLock()
            _REVIEW_LOCKS[key] = lock
        return lock


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _as_text(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value.strip() or default
    if value is None:
        return default
    return str(value).strip() or default


def _safe_int(value: object, default: int = -1) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_timestamp(value: object) -> datetime | None:
    raw = _as_text(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _review_items(state: AgentState) -> list[dict[str, Any]]:
    """Return the durable review ledger, repairing legacy state safely."""
    raw_items = state.internal_state.setdefault(REVIEW_ITEMS_KEY, [])
    if not isinstance(raw_items, list):
        raw_items = []
        state.internal_state[REVIEW_ITEMS_KEY] = raw_items

    items: list[dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, dict) and _as_text(item.get("review_item_id")):
            items.append(item)
    if len(items) != len(raw_items):
        state.internal_state[REVIEW_ITEMS_KEY] = items
        return items
    return raw_items


def _review_item_id(node_id: str, question_id: str) -> str:
    digest = sha256(f"{node_id}:{question_id}".encode("utf-8")).hexdigest()[:16]
    return f"review_{digest}"


_CODE_SUBMISSION_VERDICTS = frozenset({
    "wrong_answer",
    "syntax_error",
    "runtime_error",
    "time_limit",
    "internal_error",
})
_CODE_SUCCESS_ANSWER = "\u901a\u8fc7\u5168\u90e8\u670d\u52a1\u7aef\u6d4b\u8bd5"


def _code_review_item_id(
    node_id: str,
    resource_id: str,
    problem_id: str,
    problem_version: str,
) -> str:
    digest = sha256(
        f"code:{node_id}:{resource_id}:{problem_id}:{problem_version}".encode("utf-8")
    ).hexdigest()[:16]
    return f"review_{digest}"


def _code_submission_summary(evidence: dict[str, Any]) -> dict[str, int]:
    raw_summary = evidence.get("summary")
    summary = raw_summary if isinstance(raw_summary, dict) else {}
    return {
        key: max(0, _safe_int(summary.get(key), 0))
        for key in ("public_passed", "public_total", "hidden_passed", "hidden_total")
    }


def _code_verdict(evidence: dict[str, Any]) -> str:
    verdict = _as_text(evidence.get("verdict")).lower()
    return verdict if verdict in _CODE_SUBMISSION_VERDICTS | {"accepted"} else "submission_failed"


def _code_failure_reason(verdict: str, summary: dict[str, int]) -> str:
    """Return a safe learner-facing reason without disclosing hidden tests."""
    if verdict == "syntax_error":
        return "\u4ee3\u7801\u5b58\u5728\u8bed\u6cd5\u9519\u8bef\u3002\u4fee\u6b63\u540e\u91cd\u65b0\u63d0\u4ea4\u3002"
    if verdict == "runtime_error":
        return "\u4ee3\u7801\u8fd0\u884c\u65f6\u53d1\u751f\u9519\u8bef\u3002\u68c0\u67e5\u8fb9\u754c\u60c5\u51b5\u540e\u91cd\u65b0\u63d0\u4ea4\u3002"
    if verdict == "time_limit":
        return "\u4ee3\u7801\u8d85\u8fc7\u4e86\u6267\u884c\u65f6\u95f4\u9650\u5236\u3002\u8bf7\u4f18\u5316\u7b97\u6cd5\u540e\u91cd\u65b0\u63d0\u4ea4\u3002"
    if verdict == "wrong_answer":
        if summary["public_total"] > summary["public_passed"]:
            return "\u516c\u5f00\u6d4b\u8bd5\u672a\u901a\u8fc7\u3002\u8bf7\u67e5\u770b\u53ef\u89c1\u5931\u8d25\u7528\u4f8b\u540e\u4fee\u6b63\u4ee3\u7801\u3002"
        if summary["hidden_total"] > summary["hidden_passed"]:
            return "\u516c\u5f00\u6d4b\u8bd5\u5df2\u901a\u8fc7\uff0c\u4f46\u9690\u85cf\u6d4b\u8bd5\u672a\u901a\u8fc7\u3002\u8bf7\u68c0\u67e5\u8fb9\u754c\u6761\u4ef6\u540e\u91cd\u65b0\u63d0\u4ea4\u3002"
        return "\u4ee3\u7801\u672a\u901a\u8fc7\u5168\u90e8\u670d\u52a1\u7aef\u6d4b\u8bd5\u3002\u8bf7\u4fee\u6b63\u540e\u91cd\u65b0\u63d0\u4ea4\u3002"
    return "\u672c\u6b21\u4ee3\u7801\u63d0\u4ea4\u672a\u80fd\u901a\u8fc7\u3002\u8bf7\u68c0\u67e5\u4ee3\u7801\u540e\u91cd\u65b0\u63d0\u4ea4\u3002"


def _code_result_snapshot(
    evidence: dict[str, Any],
    *,
    accepted: bool,
    now: datetime,
) -> dict[str, Any]:
    """Keep only server-issued, learner-safe code submission metadata."""
    snapshot: dict[str, Any] = {
        "accepted": accepted,
        "submission_id": _as_text(evidence.get("submission_id")),
        "verdict": _code_verdict(evidence),
        "summary": _code_submission_summary(evidence),
        "recorded_at": _iso(now),
    }
    for key in ("runtime_ms", "memory_kb"):
        value = evidence.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            snapshot[key] = value
    return snapshot


def _code_practice_material(
    state: AgentState,
    node_id: str,
    resource_id: str,
) -> dict[str, str]:
    for card in state.generated_resources.get(node_id, []):
        if _as_text(getattr(card, "resource_id", "")) != resource_id:
            continue
        card_type = _as_text(getattr(card, "card_type", ""), "code_snippet")
        return {
            "resource_id": resource_id,
            "resource_type": card_type,
            "label": _RESOURCE_LABELS.get(card_type, "代码练习"),
        }
    return {
        "resource_id": resource_id,
        "resource_type": "code_snippet",
        "label": "代码练习",
    }


def _code_recommended_materials(
    state: AgentState,
    node_id: str,
    resource_id: str,
) -> list[dict[str, str]]:
    source = _code_practice_material(state, node_id, resource_id)
    materials = _recommended_materials(state, node_id)
    if all(material.get("resource_id") != resource_id for material in materials):
        return [source, *materials]
    return materials


def _error_type(question_result: dict[str, Any]) -> str:
    skill_tag = _as_text(question_result.get("skill_tag")).lower()
    if "boundary" in skill_tag or "边界" in skill_tag:
        return "boundary_condition"
    if "scenario" in skill_tag or "场景" in skill_tag or "application" in skill_tag:
        return "application_context"
    return "concept_understanding"


def _resource_cards_by_type(state: AgentState, node_id: str) -> dict[str, Any]:
    cards: dict[str, Any] = {}
    for card in state.generated_resources.get(node_id, []):
        card_type = _as_text(getattr(card, "card_type", ""))
        if card_type:
            cards[card_type] = card
    return cards


def _recommended_materials(state: AgentState, node_id: str) -> list[dict[str, str]]:
    cards = _resource_cards_by_type(state, node_id)
    materials: list[dict[str, str]] = []
    for card_type in _RECOMMENDED_RESOURCE_TYPES:
        card = cards.get(card_type)
        if card is None:
            continue
        materials.append({
            "resource_id": _as_text(getattr(card, "resource_id", "")),
            "resource_type": card_type,
            "label": _RESOURCE_LABELS[card_type],
        })
    return materials


def _find_item(items: Iterable[dict[str, Any]], review_item_id: str) -> dict[str, Any] | None:
    return next((item for item in items if item.get("review_item_id") == review_item_id), None)


def _serialize_item(item: dict[str, Any]) -> dict[str, Any]:
    """Return an API-safe copy of one learner-owned review record."""
    allowed = {
        "review_item_id",
        "source_event_id",
        "source_resource_id",
        "source_submission_id",
        "review_kind",
        "node_id",
        "node_title",
        "question_id",
        "question_prompt",
        "practice_problem_id",
        "practice_problem_version",
        "code_verdict",
        "error_type",
        "error_detail",
        "original_answer",
        "original_answer_index",
        "correct_answer",
        "correct_answer_index",
        "explanation",
        "related_node",
        "next_review_at",
        "status",
        "phase",
        "attempt_count",
        "retest_attempt_count",
        "recommended_materials",
        "targeted_practice",
        "retest_resource_id",
        "created_at",
        "updated_at",
        "started_at",
        "practice_required_after",
        "practice_event_id",
        "practice_completed_at",
        "completed_at",
        "last_retest_event_id",
        "last_submission_event_id",
        "resolution_submission_id",
        "last_result",
    }
    return {key: item.get(key) for key in allowed if key in item}


def _targeted_practice(materials: list[dict[str, str]]) -> dict[str, str] | None:
    return next(
        (material for material in materials if material.get("resource_type") == "interactive_exercise"),
        None,
    )


def _next_review_time(item: dict[str, Any], now: datetime) -> str:
    """Use a short, deterministic retry cadence without inventing mastery."""
    retries = max(0, _safe_int(item.get("retest_attempt_count"), 0))
    delay_hours = min(24 * 7, 24 * (2 ** min(retries, 3)))
    return _iso(now + timedelta(hours=delay_hours))


def _require_new_practice(item: dict[str, Any], now: datetime) -> None:
    """Invalidate prior practice evidence when another remediation cycle begins."""
    item["practice_required_after"] = _iso(now)
    item.pop("practice_event_id", None)
    item.pop("practice_completed_at", None)
    item.pop("retest_resource_id", None)


def _retarget_active_review_item(
    item: dict[str, Any],
    question_result: dict[str, Any],
    *,
    event_id: str,
    now: datetime,
) -> None:
    """Close or reschedule an in-progress item using a verified retest answer."""
    item["last_retest_event_id"] = event_id
    item["retest_attempt_count"] = max(0, _safe_int(item.get("retest_attempt_count"), 0)) + 1
    item["last_result"] = {
        "correct": bool(question_result.get("correct")),
        "selected_answer": _as_text(question_result.get("selected_answer")),
        "correct_answer": _as_text(question_result.get("correct_answer")),
        "recorded_at": _iso(now),
    }
    if question_result.get("correct"):
        item["status"] = "completed"
        item["phase"] = "completed"
        item["completed_at"] = _iso(now)
        item["next_review_at"] = None
    else:
        item["status"] = "due"
        item["phase"] = "material_review"
        item["next_review_at"] = _next_review_time(item, now)
        item["original_answer"] = _as_text(question_result.get("selected_answer"))
        item["original_answer_index"] = _safe_int(question_result.get("selected_index"))
        _require_new_practice(item, now)
    item["updated_at"] = _iso(now)


def _retarget_reinforcement_item(
    item: dict[str, Any],
    *,
    event_id: str,
    correctness: float,
    mastery_after: float,
    now: datetime,
) -> None:
    """Resolve an evidence-gap task only when a fresh verified retest reaches mastery."""
    item["last_retest_event_id"] = event_id
    item["retest_attempt_count"] = max(0, _safe_int(item.get("retest_attempt_count"), 0)) + 1
    item["last_result"] = {
        "correctness": round(float(correctness), 6),
        "mastery_after": round(float(mastery_after), 6),
        "recorded_at": _iso(now),
    }
    if mastery_after >= MASTERY_ADVANCE_THRESHOLD:
        item["status"] = "completed"
        item["phase"] = "completed"
        item["completed_at"] = _iso(now)
        item["next_review_at"] = None
    else:
        item["status"] = "due"
        item["phase"] = "material_review"
        item["next_review_at"] = _next_review_time(item, now)
        _require_new_practice(item, now)
    item["updated_at"] = _iso(now)


def record_verified_diagnostic(
    state: AgentState,
    *,
    event_id: str,
    node_id: str,
    resource_id: str,
    evidence: dict[str, Any],
    correctness: float,
    mastery_after: float,
) -> dict[str, Any]:
    """Create/update review items from server-owned diagnostic outcomes.

    ``evidence`` comes from ``_verify_quiz_completion``.  This function never
    accepts a browser-provided correctness value, correct answer, or error
    classification.
    """
    now = _utcnow()
    items = _review_items(state)
    results = evidence.get("question_results") if isinstance(evidence, dict) else []
    if not isinstance(results, list):
        results = []
    question_results = [result for result in results if isinstance(result, dict)]
    by_question = {
        _as_text(result.get("question_id")): result
        for result in question_results
        if _as_text(result.get("question_id"))
    }
    report_lines = [
        f"## {get_node_title(node_id, node_id)} 诊断",
        "",
        f"- 事件：`{event_id}`",
        f"- 服务端验证正确率：{round(float(correctness) * 100)}%",
        f"- 诊断后掌握度：{round(float(mastery_after) * 100)}%",
        "",
        "### 逐题结果",
    ]
    for result in question_results:
        outcome = "正确" if result.get("correct") else "需复习"
        report_lines.extend([
            "",
            f"- {outcome}：{_as_text(result.get('prompt'), _as_text(result.get('question_id')))}",
            f"  - 作答：{_as_text(result.get('selected_answer'), '未作答')}",
            f"  - 依据：{_as_text(result.get('explanation'), '以服务端答案键为准')}",
        ])
    state.internal_state["latest_verified_diagnostic_report"] = {
        "event_id": event_id,
        "node_id": node_id,
        "resource_id": resource_id,
        "correctness": round(float(correctness), 6),
        "mastery_after": round(float(mastery_after), 6),
        "question_results": [dict(result) for result in question_results],
        "markdown": "\n".join(report_lines),
        "recorded_at": _iso(now),
    }

    # A started review item can only close after a fresh, server-verified
    # diagnostic resource answers its original question correctly.
    retested_items: list[dict[str, Any]] = []
    for item in items:
        if item.get("status") != "in_progress" or item.get("retest_resource_id") != resource_id:
            continue
        if item.get("review_kind") == "mastery_reinforcement":
            _retarget_reinforcement_item(
                item,
                event_id=event_id,
                correctness=correctness,
                mastery_after=mastery_after,
                now=now,
            )
            retested_items.append(item)
            continue
        result = by_question.get(_as_text(item.get("question_id")))
        if result is None:
            continue
        _retarget_active_review_item(item, result, event_id=event_id, now=now)
        retested_items.append(item)

    created_or_updated: list[dict[str, Any]] = []
    for result in question_results:
        if result.get("correct"):
            continue
        question_id = _as_text(result.get("question_id"))
        if not question_id:
            continue
        review_id = _review_item_id(node_id, question_id)
        item = _find_item(items, review_id)
        materials = _recommended_materials(state, node_id)
        if item is None:
            item = {
                "review_item_id": review_id,
                "source_event_id": event_id,
                "source_resource_id": resource_id,
                "review_kind": "diagnostic_quiz",
                "node_id": node_id,
                "node_title": get_node_title(node_id, node_id),
                "related_node": node_id,
                "question_id": question_id,
                "question_prompt": _as_text(result.get("prompt")),
                "error_type": _error_type(result),
                "error_detail": _as_text(result.get("skill_tag"), "concept"),
                "original_answer": _as_text(result.get("selected_answer")),
                "original_answer_index": _safe_int(result.get("selected_index")),
                "correct_answer": _as_text(result.get("correct_answer")),
                "correct_answer_index": _safe_int(result.get("correct_index")),
                "explanation": _as_text(result.get("explanation")),
                "recommended_materials": materials,
                "targeted_practice": _targeted_practice(materials),
                "next_review_at": _iso(now),
                "status": "due",
                "phase": "material_review",
                "attempt_count": 1,
                "retest_attempt_count": 0,
                "created_at": _iso(now),
                "updated_at": _iso(now),
            }
            items.append(item)
        else:
            item.update({
                "source_event_id": event_id,
                "source_resource_id": resource_id,
                "review_kind": "diagnostic_quiz",
                "node_title": get_node_title(node_id, node_id),
                "question_prompt": _as_text(result.get("prompt")),
                "error_type": _error_type(result),
                "error_detail": _as_text(result.get("skill_tag"), "concept"),
                "original_answer": _as_text(result.get("selected_answer")),
                "original_answer_index": _safe_int(result.get("selected_index")),
                "correct_answer": _as_text(result.get("correct_answer")),
                "correct_answer_index": _safe_int(result.get("correct_index")),
                "explanation": _as_text(result.get("explanation")),
                "recommended_materials": materials,
                "targeted_practice": _targeted_practice(materials),
                "status": "due",
                "phase": "material_review",
                "next_review_at": _iso(now),
                "attempt_count": max(0, _safe_int(item.get("attempt_count"), 0)) + 1,
                "updated_at": _iso(now),
            })
            # A prior completed record becomes due again only after a newly
            # verified incorrect answer, never after a client-side action.
            item.pop("completed_at", None)
            _require_new_practice(item, now)
        created_or_updated.append(item)

    outstanding = [
        item for item in items
        if item.get("node_id") == node_id and item.get("status") in {"due", "in_progress"}
    ]
    if MASTERY_REINFORCEMENT_ENABLED and mastery_after < MASTERY_ADVANCE_THRESHOLD and not outstanding:
        reinforcement_id = _review_item_id(node_id, "__mastery_evidence_gap__")
        reinforcement = _find_item(items, reinforcement_id)
        materials = _recommended_materials(state, node_id)
        question_count = max(0, _safe_int(evidence.get("question_count"), len(question_results)))
        correct_count = max(0, _safe_int(evidence.get("correct_count"), 0))
        snapshot = (
            f"本次诊断 {correct_count}/{question_count}，"
            f"当前掌握度 {round(float(mastery_after) * 100)}%"
        )
        reinforcement_values = {
            "source_event_id": event_id,
            "source_resource_id": resource_id,
            "review_kind": "mastery_reinforcement",
            "node_id": node_id,
            "node_title": get_node_title(node_id, node_id),
            "related_node": node_id,
            "question_id": "__mastery_evidence_gap__",
            "question_prompt": "本次诊断已通过，但节点掌握证据仍未达到推进阈值",
            "error_type": "insufficient_evidence",
            "error_detail": "mastery_below_threshold",
            "original_answer": snapshot,
            "original_answer_index": -1,
            "correct_answer": (
                "完成定向练习，并通过新的服务端复测达到 "
                f"{round(MASTERY_ADVANCE_THRESHOLD * 100)}% 掌握阈值"
            ),
            "correct_answer_index": -1,
            "explanation": (
                "本次题目答案已由服务端验证，不会计入错题本；"
                "但当前累积证据不足以推进节点，因此需要一次定向练习和新的复测。"
            ),
            "recommended_materials": materials,
            "targeted_practice": _targeted_practice(materials),
            "next_review_at": _iso(now),
            "status": "due",
            "phase": "material_review",
            "updated_at": _iso(now),
        }
        if reinforcement is None:
            reinforcement = {
                "review_item_id": reinforcement_id,
                "attempt_count": 1,
                "retest_attempt_count": 0,
                "created_at": _iso(now),
                **reinforcement_values,
            }
            items.append(reinforcement)
        else:
            reinforcement.update({
                **reinforcement_values,
                "attempt_count": max(0, _safe_int(reinforcement.get("attempt_count"), 0)) + 1,
            })
            reinforcement.pop("completed_at", None)
            _require_new_practice(reinforcement, now)
        created_or_updated.append(reinforcement)

    if len(items) > MAX_REVIEW_ITEMS:
        items.sort(key=lambda item: _as_text(item.get("updated_at")), reverse=True)
        del items[MAX_REVIEW_ITEMS:]

    outstanding = [
        item for item in items
        if item.get("node_id") == node_id and item.get("status") in {"due", "in_progress"}
    ]
    # An open item remains an explicit task even when the latest aggregate
    # score is high. A learner must close it through a mapped fresh retest.
    requires_remediation = bool(outstanding)
    remediation = None
    if requires_remediation:
        reinforcement_only = all(
            item.get("review_kind") == "mastery_reinforcement"
            for item in outstanding
        )
        remediation = {
            "node_id": node_id,
            "title": "完成掌握度补强后再复测" if reinforcement_only else "完成这组补救任务后再复测",
            "steps": [
                {
                    "kind": "review_material",
                    "label": "回看本节点讲解" if reinforcement_only else "复盘错题解析",
                    "detail": (
                        "先回顾关键条件、示例和边界。"
                        if reinforcement_only
                        else "先核对原答案、正确答案和解析。"
                    ),
                },
                {"kind": "targeted_practice", "label": "完成相似题练习", "detail": "使用系统为当前薄弱点准备的练习材料。"},
                {"kind": "retest", "label": "进行服务端复测", "detail": "复测结果会决定错题是否完成，并据真实结果更新掌握度。"},
            ],
            "review_item_ids": [item["review_item_id"] for item in outstanding],
        }

    return {
        "requires_remediation": requires_remediation,
        "created_or_updated_items": [_serialize_item(item) for item in created_or_updated],
        "retested_items": [_serialize_item(item) for item in retested_items],
        "remediation": remediation,
    }


def record_verified_code_submission(
    state: AgentState,
    *,
    event_id: str,
    node_id: str,
    resource_id: str,
    evidence: dict[str, Any],
    receipt_accepted: bool,
) -> dict[str, Any]:
    """Create or resolve a code review item from a verified submission receipt.

    The caller must pass the evidence returned by
    ``code_practice_service.verify_submission_receipt``.  This function only
    persists learner-safe receipt metadata; source code, hidden inputs,
    expected values, and reference implementations never enter the review
    ledger.
    """
    trusted_evidence = evidence if isinstance(evidence, dict) else {}
    normalized_node_id = _as_text(node_id)
    normalized_resource_id = _as_text(resource_id)
    submission_id = _as_text(trusted_evidence.get("submission_id"))
    problem_id = _as_text(trusted_evidence.get("problem_id"))
    problem_version = _as_text(trusted_evidence.get("problem_version"), "unknown")
    if not all((normalized_node_id, normalized_resource_id, submission_id, problem_id)):
        return {
            "requires_remediation": False,
            "created_or_updated_items": [],
            "retested_items": [],
            "remediation": None,
        }

    now = _utcnow()
    items = _review_items(state)
    review_id = _code_review_item_id(
        normalized_node_id,
        normalized_resource_id,
        problem_id,
        problem_version,
    )
    item = _find_item(items, review_id)
    created_or_updated: list[dict[str, Any]] = []
    retested_items: list[dict[str, Any]] = []

    if receipt_accepted:
        # A code review closes only after this exact server-owned receipt says
        # accepted.  A client-side success flag cannot reach this branch.
        if item is not None and item.get("status") != "completed":
            item["status"] = "completed"
            item["phase"] = "completed"
            item["completed_at"] = _iso(now)
            item["next_review_at"] = None
            item["last_submission_event_id"] = event_id
            item["resolution_submission_id"] = submission_id
            item["last_result"] = _code_result_snapshot(
                trusted_evidence,
                accepted=True,
                now=now,
            )
            item["retest_attempt_count"] = max(
                0,
                _safe_int(item.get("retest_attempt_count"), 0),
            ) + 1
            item["updated_at"] = _iso(now)
            retested_items.append(item)
    else:
        verdict = _code_verdict(trusted_evidence)
        if verdict == "internal_error":
            outstanding = [
                candidate
                for candidate in items
                if candidate.get("node_id") == normalized_node_id
                and candidate.get("status") in {"due", "in_progress"}
            ]
            return {
                "requires_remediation": bool(outstanding),
                "created_or_updated_items": [],
                "retested_items": [],
                "remediation": None,
                "transient_failure": {
                    "reason": "code_execution_internal_error",
                    "retryable": True,
                },
            }
        summary = _code_submission_summary(trusted_evidence)
        failure_reason = _code_failure_reason(verdict, summary)
        submitted_source = trusted_evidence.get("source_code")
        original_answer = (
            submitted_source
            if isinstance(submitted_source, str) and submitted_source.strip()
            else "本次提交的源代码未保存。"
        )
        materials = _code_recommended_materials(
            state,
            normalized_node_id,
            normalized_resource_id,
        )
        targeted_practice = _code_practice_material(
            state,
            normalized_node_id,
            normalized_resource_id,
        )
        if item is None:
            item = {
                "review_item_id": review_id,
                "review_kind": "code_practice",
                "source_event_id": event_id,
                "source_resource_id": normalized_resource_id,
                "source_submission_id": submission_id,
                "node_id": normalized_node_id,
                "node_title": get_node_title(normalized_node_id, normalized_node_id),
                "related_node": normalized_node_id,
                "question_id": f"code:{problem_id}:v{problem_version}",
                "question_prompt": f"代码练习：{problem_id}",
                "practice_problem_id": problem_id,
                "practice_problem_version": problem_version,
                "code_verdict": verdict,
                "error_type": verdict,
                "error_detail": failure_reason,
                "original_answer": original_answer,
                "correct_answer": _CODE_SUCCESS_ANSWER,
                "explanation": failure_reason,
                "recommended_materials": materials,
                "targeted_practice": targeted_practice,
                "next_review_at": _iso(now),
                "status": "due",
                "phase": "code_resubmission",
                "attempt_count": 1,
                "retest_attempt_count": 0,
                "last_submission_event_id": event_id,
                "last_result": _code_result_snapshot(
                    trusted_evidence,
                    accepted=False,
                    now=now,
                ),
                "created_at": _iso(now),
                "updated_at": _iso(now),
            }
            items.append(item)
        else:
            item.update({
                "source_event_id": event_id,
                "source_resource_id": normalized_resource_id,
                "source_submission_id": submission_id,
                "node_title": get_node_title(normalized_node_id, normalized_node_id),
                "code_verdict": verdict,
                "error_type": verdict,
                "error_detail": failure_reason,
                "original_answer": original_answer,
                "correct_answer": _CODE_SUCCESS_ANSWER,
                "explanation": failure_reason,
                "recommended_materials": materials,
                "targeted_practice": targeted_practice,
                "next_review_at": _iso(now),
                "status": "due",
                "phase": "code_resubmission",
                "attempt_count": max(0, _safe_int(item.get("attempt_count"), 0)) + 1,
                "last_submission_event_id": event_id,
                "last_result": _code_result_snapshot(
                    trusted_evidence,
                    accepted=False,
                    now=now,
                ),
                "updated_at": _iso(now),
            })
            item.pop("completed_at", None)
            item.pop("resolution_submission_id", None)
        created_or_updated.append(item)

    if len(items) > MAX_REVIEW_ITEMS:
        items.sort(key=lambda candidate: _as_text(candidate.get("updated_at")), reverse=True)
        del items[MAX_REVIEW_ITEMS:]

    outstanding = [
        candidate
        for candidate in items
        if candidate.get("node_id") == normalized_node_id
        and candidate.get("status") in {"due", "in_progress"}
    ]
    remediation = None
    if outstanding:
        remediation = {
            "node_id": normalized_node_id,
            "title": "\u8bf7\u5b8c\u6210\u4ee3\u7801\u8865\u6551\u540e\u518d\u6b21\u63d0\u4ea4",
            "steps": [
                {
                    "kind": "review_material",
                    "label": "\u590d\u76d8\u5931\u8d25\u539f\u56e0",
                    "detail": "\u67e5\u770b\u672c\u6b21\u670d\u52a1\u7aef\u5224\u5b9a\u7684\u9519\u8bef\u539f\u56e0\u548c\u53ef\u89c1\u6d4b\u8bd5\u7ed3\u679c\u3002",
                },
                {
                    "kind": "targeted_practice",
                    "label": "\u4fee\u6539\u5e76\u8fd0\u884c\u4ee3\u7801",
                    "detail": "\u9488\u5bf9\u5f53\u524d\u5931\u8d25\u539f\u56e0\u4fee\u6b63\u5b9e\u73b0\uff0c\u5148\u8fd0\u884c\u516c\u5f00\u6d4b\u8bd5\u786e\u8ba4\u3002",
                },
                {
                    "kind": "retest",
                    "label": "\u91cd\u65b0\u63d0\u4ea4\u670d\u52a1\u7aef\u6d4b\u8bd5",
                    "detail": "\u53ea\u6709\u670d\u52a1\u7aef\u5224\u5b9a\u901a\u8fc7\u540e\uff0c\u8865\u6551\u4efb\u52a1\u624d\u4f1a\u5b8c\u6210\u5e76\u66f4\u65b0\u638c\u63e1\u5ea6\u3002",
                },
            ],
            "review_item_ids": [candidate["review_item_id"] for candidate in outstanding],
        }
    return {
        "requires_remediation": bool(outstanding),
        "created_or_updated_items": [_serialize_item(candidate) for candidate in created_or_updated],
        "retested_items": [_serialize_item(candidate) for candidate in retested_items],
        "remediation": remediation,
    }


def _is_due_today(item: dict[str, Any], now: datetime) -> bool:
    if item.get("status") not in {"due", "in_progress"}:
        return False
    raw = _as_text(item.get("next_review_at"))
    if not raw:
        return item.get("status") == "in_progress"
    try:
        scheduled = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return True
    return scheduled.astimezone(timezone.utc) <= now


def _mastery_trend(state: AgentState) -> list[dict[str, Any]]:
    raw = state.internal_state.get("mastery_attributions", [])
    if not isinstance(raw, list):
        return []
    trend: list[dict[str, Any]] = []
    for attribution in raw[-MAX_TREND_POINTS:]:
        if not isinstance(attribution, dict):
            continue
        before = attribution.get("mastery_before")
        after = attribution.get("mastery_after")
        if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
            continue
        evidence = attribution.get("evidence")
        evidence_summary = ""
        if isinstance(evidence, dict):
            question_count = _safe_int(evidence.get("question_count"), 0)
            correct_count = _safe_int(evidence.get("correct_count"), 0)
            if question_count > 0:
                evidence_summary = f"服务端诊断 {correct_count}/{question_count}"
            else:
                code_summary = evidence.get("summary")
                if isinstance(code_summary, dict):
                    public_passed = _safe_int(code_summary.get("public_passed"), 0)
                    public_total = _safe_int(code_summary.get("public_total"), 0)
                    hidden_passed = _safe_int(code_summary.get("hidden_passed"), 0)
                    hidden_total = _safe_int(code_summary.get("hidden_total"), 0)
                    evidence_summary = (
                        f"代码测试：公开 {public_passed}/{public_total}，"
                        f"隐藏 {hidden_passed}/{hidden_total}"
                    )
        trend.append({
            "event_id": _as_text(attribution.get("event_id")),
            "event_type": _as_text(attribution.get("event_type")),
            "node_id": _as_text(attribution.get("node_id")),
            "node_title": get_node_title(_as_text(attribution.get("node_id")), _as_text(attribution.get("node_id"))),
            "resource_id": _as_text(attribution.get("resource_id")),
            "recorded_at": _as_text(attribution.get("recorded_at")),
            "mastery_before": float(before),
            "mastery_after": float(after),
            "mastery_delta": round(float(after) - float(before), 6),
            "reason": _as_text(attribution.get("reason")),
            "evidence_summary": evidence_summary,
        })
    return trend


def _weak_nodes(state: AgentState, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    outstanding_by_node: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        if item.get("status") not in {"due", "in_progress"}:
            continue
        node_id = _as_text(item.get("node_id"))
        if node_id:
            outstanding_by_node.setdefault(node_id, []).append(item)

    evidence_node_ids: set[str] = set(outstanding_by_node)
    for collection_name in ("mastery_attributions", "verified_completion_events"):
        records = state.internal_state.get(collection_name, [])
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            node_id = _as_text(record.get("node_id"))
            if node_id:
                evidence_node_ids.add(node_id)

    entries: list[dict[str, Any]] = []
    for node_id in evidence_node_ids:
        mastery = float(state.dynamic_profile.knowledge_mastery.get(node_id, 0.0) or 0.0)
        mistakes = outstanding_by_node.get(node_id, [])
        if mastery >= MASTERY_ADVANCE_THRESHOLD and not mistakes:
            continue
        error_types = sorted({_as_text(item.get("error_type")) for item in mistakes if _as_text(item.get("error_type"))})
        entries.append({
            "node_id": node_id,
            "node_title": get_node_title(node_id, node_id),
            "mastery": mastery,
            "outstanding_count": len(mistakes),
            "error_types": error_types,
            "next_review_at": min((_as_text(item.get("next_review_at")) for item in mistakes), default=""),
            "weakness_score": round((1.0 - mastery) + min(0.8, len(mistakes) * 0.5), 4),
        })
    return sorted(entries, key=lambda item: (-item["weakness_score"], item["node_id"]))


def _latest_diagnostic(state: AgentState) -> dict[str, Any] | None:
    snapshot = state.internal_state.get("latest_verified_diagnostic_report")
    if isinstance(snapshot, dict) and _as_text(snapshot.get("event_id")):
        node_id = _as_text(snapshot.get("node_id"))
        question_results = snapshot.get("question_results")
        normalized_results = question_results if isinstance(question_results, list) else []
        return {
            "event_id": _as_text(snapshot.get("event_id")),
            "node_id": node_id,
            "node_title": get_node_title(node_id, node_id),
            "resource_id": _as_text(snapshot.get("resource_id")),
            "correctness": snapshot.get("correctness"),
            "mastery_after": snapshot.get("mastery_after"),
            "question_count": len(normalized_results),
            "correct_count": sum(
                1 for result in normalized_results
                if isinstance(result, dict) and result.get("correct")
            ),
            "question_results": normalized_results,
            "recorded_at": _as_text(snapshot.get("recorded_at")),
        }
    raw = state.internal_state.get("verified_completion_events", [])
    if not isinstance(raw, list):
        return None
    for record in reversed(raw):
        if not isinstance(record, dict):
            continue
        return {
            "event_id": _as_text(record.get("event_id")),
            "node_id": _as_text(record.get("node_id")),
            "node_title": get_node_title(_as_text(record.get("node_id")), _as_text(record.get("node_id"))),
            "resource_id": _as_text(record.get("resource_id")),
            "correctness": record.get("correctness"),
            "question_count": record.get("question_count"),
            "correct_count": record.get("correct_count"),
            "question_results": record.get("question_results", []),
        }
    return None


def get_review_dashboard(user_id: str, course_id: str = "data_structures") -> dict[str, Any]:
    """Return the learner's review queue and its evidence-backed context."""
    session = get_session(user_id, course_id)
    state = session.agent_state
    now = _utcnow()
    items = _review_items(state)
    legacy_items = [item for item in items if item.get("review_kind") == "mastery_reinforcement"]
    if legacy_items:
        items[:] = [item for item in items if item.get("review_kind") != "mastery_reinforcement"]
        persist_session(session)
    active_items = [item for item in items if item.get("status") in {"due", "in_progress"}]
    today = [item for item in active_items if _is_due_today(item, now)]
    diagnostic_snapshot = state.internal_state.get("latest_verified_diagnostic_report")
    diagnostic_markdown = (
        _as_text(diagnostic_snapshot.get("markdown"))
        if isinstance(diagnostic_snapshot, dict)
        else ""
    )
    return {
        "status": "ok",
        "user_id": user_id,
        "course_id": course_id,
        "generated_at": _iso(now),
        "mistakes": [
            _serialize_item(item)
            for item in sorted(items, key=lambda item: _as_text(item.get("updated_at")), reverse=True)
            if item.get("review_kind") != "mastery_reinforcement"
        ],
        "reinforcement_tasks": [
            _serialize_item(item)
            for item in sorted(items, key=lambda item: _as_text(item.get("updated_at")), reverse=True)
            if item.get("review_kind") == "mastery_reinforcement"
        ],
        "today_queue": [_serialize_item(item) for item in sorted(today, key=lambda item: (_as_text(item.get("next_review_at")), _as_text(item.get("review_item_id"))))],
        "weak_nodes": _weak_nodes(state, items),
        "mastery_trend": _mastery_trend(state),
        "diagnostic_report": {
            "markdown": diagnostic_markdown,
            "latest": _latest_diagnostic(state),
        },
    }


def start_review_item(user_id: str, course_id: str, review_item_id: str) -> dict[str, Any]:
    with _review_lock(user_id, course_id):
        return _start_review_item_unlocked(user_id, course_id, review_item_id)


def delete_review_item(user_id: str, course_id: str, review_item_id: str) -> dict[str, Any]:
    """Permanently remove one learner-owned review record."""
    normalized_id = _as_text(review_item_id)
    if not normalized_id:
        return {"status": "invalid_review_item_id", "status_code": 422}

    with _review_lock(user_id, course_id):
        session = get_session(user_id, course_id)
        items = _review_items(session.agent_state)
        item = _find_item(items, normalized_id)
        if item is None:
            return {"status": "review_item_not_found", "status_code": 404}
        items[:] = [candidate for candidate in items if candidate is not item]
        persist_session(session)
        return {"status": "deleted", "review_item_id": normalized_id}


def _start_review_item_unlocked(
    user_id: str,
    course_id: str,
    review_item_id: str,
) -> dict[str, Any]:
    """Start the material-review phase for one due item.

    Starting an item is a real learner action but cannot change mastery.  The
    later retest must still be submitted to the normal evidence verifier.
    """
    normalized_id = _as_text(review_item_id)
    if not normalized_id:
        return {"status": "invalid_review_item_id", "status_code": 422}
    session = get_session(user_id, course_id)
    item = _find_item(_review_items(session.agent_state), normalized_id)
    if item is None:
        return {"status": "review_item_not_found", "status_code": 404}
    if item.get("status") == "completed":
        return {"status": "review_item_completed", "status_code": 409, "review_item": _serialize_item(item)}

    if item.get("status") == "in_progress" and item.get("phase") == "retest":
        node_id = _as_text(item.get("node_id"))
        retest_resource_id = _as_text(item.get("retest_resource_id"))
        retest_exists = any(
            _as_text(getattr(card, "resource_id", "")) == retest_resource_id
            and _as_text(getattr(card, "card_type", "")) == "diagnostic_quiz"
            for card in session.agent_state.generated_resources.get(node_id, [])
        )
        if retest_resource_id and retest_exists:
            return {
                "status": "ok",
                "review_item": _serialize_item(item),
                "learning_task": {
                    "node_id": node_id,
                    "focus_resource_type": "diagnostic_quiz",
                    "review_kind": _as_text(item.get("review_kind"), "diagnostic_quiz"),
                    "phase": "retest",
                    "retest_resource_id": retest_resource_id,
                },
            }
        now = _utcnow()
        item["status"] = "due"
        item["phase"] = "material_review"
        _require_new_practice(item, now)
        item["updated_at"] = _iso(now)
        persist_session(session)

    was_due = item.get("status") == "due"
    now = _utcnow()
    review_kind = _as_text(item.get("review_kind"), "diagnostic_quiz")
    is_code_review = review_kind == "code_practice"
    node_id = _as_text(item.get("node_id"))
    if not node_id:
        return {"status": "review_item_invalid_node", "status_code": 422}

    if is_code_review:
        source_resource_id = _as_text(item.get("source_resource_id"))
        materials = _code_recommended_materials(
            session.agent_state,
            node_id,
            source_resource_id,
        )
        targeted_practice = _code_practice_material(
            session.agent_state,
            node_id,
            source_resource_id,
        )
    else:
        materials = _recommended_materials(session.agent_state, node_id)
        targeted_practice = _targeted_practice(materials)
        if targeted_practice is None:
            from . import resource_service

            generated = resource_service.generate_current_node_resources(
                user_id,
                course_id,
                node_id,
                force=False,
                card_type="interactive_exercise",
            )
            if generated.get("status") not in {
                "generated",
                "already_exists",
                "repaired_fallback",
            }:
                return {
                    "status": "targeted_practice_unavailable",
                    "status_code": int(generated.get("status_code") or 503),
                    "detail": generated.get("error") or "暂时无法准备定向练习，请稍后重试。",
                }
            session = get_session(user_id, course_id)
            item = _find_item(_review_items(session.agent_state), normalized_id)
            if item is None:
                return {"status": "review_item_not_found", "status_code": 404}
            materials = _recommended_materials(session.agent_state, node_id)
            targeted_practice = _targeted_practice(materials)
        if targeted_practice is None:
            return {
                "status": "targeted_practice_unavailable",
                "status_code": 503,
                "detail": "定向练习资源缺少可验证的题目，请稍后重试。",
            }

    item["status"] = "in_progress"
    item["phase"] = "code_resubmission" if is_code_review else "material_review"
    if was_due:
        item["started_at"] = _iso(now)
        if not is_code_review:
            _require_new_practice(item, now)
    else:
        item["started_at"] = item.get("started_at") or _iso(now)
    item["updated_at"] = _iso(now)
    item["recommended_materials"] = materials
    item["targeted_practice"] = targeted_practice
    persist_session(session)
    return {
        "status": "ok",
        "review_item": _serialize_item(item),
        "learning_task": {
            "node_id": node_id,
            "resource_id": _as_text(item.get("source_resource_id")) if is_code_review else "",
            "focus_resource_type": "code_snippet" if is_code_review else "interactive_exercise",
            "review_kind": review_kind,
            "phase": item["phase"],
        },
    }


def start_direct_review_retest(user_id: str, course_id: str, review_item_id: str) -> dict[str, Any]:
    """Issue a fresh diagnostic quiz for the explicit quick-retest action."""
    with _review_lock(user_id, course_id):
        return _start_direct_review_retest_unlocked(user_id, course_id, review_item_id)


def _start_direct_review_retest_unlocked(
    user_id: str,
    course_id: str,
    review_item_id: str,
) -> dict[str, Any]:
    normalized_id = _as_text(review_item_id)
    if not normalized_id:
        return {"status": "invalid_review_item_id", "status_code": 422}

    session = get_session(user_id, course_id)
    item = _find_item(_review_items(session.agent_state), normalized_id)
    if item is None:
        return {"status": "review_item_not_found", "status_code": 404}
    if item.get("status") == "completed":
        return {"status": "review_item_completed", "status_code": 409, "review_item": _serialize_item(item)}
    if item.get("review_kind") == "code_practice":
        return {
            "status": "code_review_requires_submission",
            "status_code": 409,
            "detail": "代码错题需要进入代码练习后重新提交。",
        }

    node_id = _as_text(item.get("node_id"))
    if not node_id:
        return {"status": "review_item_invalid_node", "status_code": 422}

    if item.get("status") == "in_progress" and item.get("phase") == "retest":
        retest_resource_id = _as_text(item.get("retest_resource_id"))
        retest_exists = any(
            _as_text(getattr(card, "resource_id", "")) == retest_resource_id
            and _as_text(getattr(card, "card_type", "")) == "diagnostic_quiz"
            for card in session.agent_state.generated_resources.get(node_id, [])
        )
        if retest_resource_id and retest_exists:
            return {
                "status": "ok",
                "idempotent": True,
                "review_item": _serialize_item(item),
                "learning_task": {
                    "node_id": node_id,
                    "focus_resource_type": "diagnostic_quiz",
                    "phase": "retest",
                    "retest_resource_id": retest_resource_id,
                },
            }

    quiz_card = _resource_cards_by_type(session.agent_state, node_id).get("diagnostic_quiz")
    if quiz_card is None:
        from . import resource_service

        generated = resource_service.generate_current_node_resources(
            user_id,
            course_id,
            node_id,
            force=False,
            card_type="diagnostic_quiz",
        )
        if generated.get("status") not in {"generated", "already_exists", "repaired_fallback"}:
            return {
                "status": "review_retest_generation_failed",
                "status_code": int(generated.get("status_code") or 500),
                "detail": generated.get("error") or "暂时无法准备复测题，请稍后重试。",
            }
        refreshed_session = get_session(user_id, course_id)
        quiz_card = _resource_cards_by_type(refreshed_session.agent_state, node_id).get("diagnostic_quiz")
    else:
        refreshed_session = session
    if quiz_card is None:
        return {"status": "review_retest_generation_failed", "status_code": 500, "detail": "新的复测题暂未准备好。"}

    item = _find_item(_review_items(refreshed_session.agent_state), normalized_id)
    if item is None:
        return {"status": "review_item_not_found", "status_code": 404}
    now = _utcnow()
    item["status"] = "in_progress"
    item["phase"] = "retest"
    item["retest_resource_id"] = _as_text(getattr(quiz_card, "resource_id", ""))
    item["started_at"] = item.get("started_at") or _iso(now)
    item["updated_at"] = _iso(now)
    persist_session(refreshed_session)
    return {
        "status": "ok",
        "review_item": _serialize_item(item),
        "learning_task": {
            "node_id": node_id,
            "focus_resource_type": "diagnostic_quiz",
            "phase": "retest",
            "retest_resource_id": item["retest_resource_id"],
        },
    }


def _validated_practice_event(
    state: AgentState,
    item: dict[str, Any],
    practice_event_id: str,
) -> tuple[dict[str, Any] | None, str]:
    history = state.internal_state.get("learning_events", [])
    if not isinstance(history, list):
        return None, "targeted_practice_event_not_found"
    event = next(
        (
            candidate
            for candidate in reversed(history)
            if isinstance(candidate, dict)
            and _as_text(candidate.get("event_id")) == practice_event_id
        ),
        None,
    )
    if event is None:
        return None, "targeted_practice_event_not_found"
    if event.get("event_type") != "answer_submitted":
        return None, "targeted_practice_answer_required"

    verification = event.get("practice_verification")
    if not isinstance(verification, dict) or not verification.get("verified"):
        return None, "targeted_practice_not_verified"
    if not verification.get("correct"):
        return None, "targeted_practice_answer_incorrect"
    if _as_text(verification.get("review_item_id")) != _as_text(item.get("review_item_id")):
        return None, "targeted_practice_review_item_mismatch"
    if _as_text(event.get("node_id")) != _as_text(item.get("node_id")):
        return None, "targeted_practice_node_mismatch"

    targeted_practice = item.get("targeted_practice")
    expected_resource_id = (
        _as_text(targeted_practice.get("resource_id"))
        if isinstance(targeted_practice, dict)
        else ""
    )
    if not expected_resource_id or _as_text(event.get("resource_id")) != expected_resource_id:
        return None, "targeted_practice_resource_mismatch"

    required_after = _parse_timestamp(
        item.get("practice_required_after") or item.get("started_at")
    )
    received_at = _parse_timestamp(event.get("received_at"))
    if received_at is None or (required_after is not None and received_at < required_after):
        return None, "targeted_practice_event_too_old"

    for candidate in _review_items(state):
        if _as_text(candidate.get("practice_event_id")) != practice_event_id:
            continue
        return None, "targeted_practice_event_already_consumed"
    return event, "verified_targeted_practice_correct"


def prepare_review_retest(
    user_id: str,
    course_id: str,
    review_item_id: str,
    practice_event_id: str = "",
) -> dict[str, Any]:
    with _review_lock(user_id, course_id):
        return _prepare_review_retest_unlocked(
            user_id,
            course_id,
            review_item_id,
            practice_event_id,
        )


def _prepare_review_retest_unlocked(
    user_id: str,
    course_id: str,
    review_item_id: str,
    practice_event_id: str = "",
) -> dict[str, Any]:
    """Consume verified directed-practice evidence and issue a fresh quiz."""
    normalized_id = _as_text(review_item_id)
    if not normalized_id:
        return {"status": "invalid_review_item_id", "status_code": 422}
    session = get_session(user_id, course_id)
    state = session.agent_state
    item = _find_item(_review_items(state), normalized_id)
    if item is None:
        return {"status": "review_item_not_found", "status_code": 404}
    if item.get("status") == "completed":
        return {"status": "review_item_completed", "status_code": 409, "review_item": _serialize_item(item)}

    if item.get("review_kind") == "code_practice":
        return {
            "status": "code_review_requires_submission",
            "status_code": 409,
            "review_item": _serialize_item(item),
            "learning_task": {
                "node_id": _as_text(item.get("node_id")),
                "resource_id": _as_text(item.get("source_resource_id")),
                "focus_resource_type": "code_snippet",
                "review_kind": "code_practice",
                "phase": "code_resubmission",
            },
        }

    normalized_practice_event_id = _as_text(practice_event_id)
    if item.get("status") == "in_progress" and item.get("phase") == "retest":
        stored_practice_event_id = _as_text(item.get("practice_event_id"))
        if not normalized_practice_event_id:
            return {
                "status": "targeted_practice_evidence_required",
                "status_code": 409,
                "review_item": _serialize_item(item),
            }
        if stored_practice_event_id != normalized_practice_event_id:
            return {
                "status": "targeted_practice_event_mismatch",
                "status_code": 409,
                "review_item": _serialize_item(item),
            }
        node_id = _as_text(item.get("node_id"))
        retest_resource_id = _as_text(item.get("retest_resource_id"))
        retest_exists = any(
            _as_text(getattr(card, "resource_id", "")) == retest_resource_id
            and _as_text(getattr(card, "card_type", "")) == "diagnostic_quiz"
            for card in state.generated_resources.get(node_id, [])
        )
        if not retest_resource_id or not retest_exists:
            return {
                "status": "review_retest_resource_unavailable",
                "status_code": 409,
                "review_item": _serialize_item(item),
            }
        return {
            "status": "ok",
            "idempotent": True,
            "review_item": _serialize_item(item),
            "learning_task": {
                "node_id": node_id,
                "focus_resource_type": "diagnostic_quiz",
                "phase": "retest",
                "retest_resource_id": retest_resource_id,
            },
        }

    if (
        item.get("status") != "in_progress"
        or item.get("phase") != "material_review"
    ):
        return {
            "status": "review_material_phase_required",
            "status_code": 409,
            "review_item": _serialize_item(item),
        }

    node_id = _as_text(item.get("node_id"))
    if not node_id:
        return {"status": "review_item_invalid_node", "status_code": 422}

    if not normalized_practice_event_id:
        return {
            "status": "targeted_practice_evidence_required",
            "status_code": 409,
            "review_item": _serialize_item(item),
        }
    practice_event, practice_reason = _validated_practice_event(
        state,
        item,
        normalized_practice_event_id,
    )
    if practice_event is None:
        return {
            "status": practice_reason,
            "status_code": 409,
            "review_item": _serialize_item(item),
        }

    # Only one diagnostic quiz resource is retained for a node. Replacing it
    # while a different item is awaiting its retest would make that item
    # impossible to resolve against the resource it was issued for.
    blocking_item = next(
        (
            candidate
            for candidate in _review_items(state)
            if candidate.get("review_item_id") != normalized_id
            and candidate.get("node_id") == node_id
            and candidate.get("status") in {"due", "in_progress"}
            and candidate.get("phase") == "retest"
        ),
        None,
    )
    if blocking_item is not None:
        return {
            "status": "review_retest_already_in_progress",
            "status_code": 409,
            "review_item": _serialize_item(item),
            "blocking_review_item_id": _as_text(blocking_item.get("review_item_id")),
        }

    # Generate a versioned resource through the established resource service.
    # It keeps answer keys server-only and replaces the consumed quiz card.
    from . import resource_service

    generated = resource_service.generate_current_node_resources(
        user_id,
        course_id,
        node_id,
        force=True,
        card_type="diagnostic_quiz",
    )
    if generated.get("status") not in {"generated", "already_exists"}:
        return {
            "status": "review_retest_generation_failed",
            "status_code": int(generated.get("status_code") or 500),
            "detail": generated.get("error") or "暂时无法准备新的复测，请稍后重试。",
        }

    refreshed_session = get_session(user_id, course_id)
    fresh_cards = _resource_cards_by_type(refreshed_session.agent_state, node_id)
    quiz_card = fresh_cards.get("diagnostic_quiz")
    if quiz_card is None:
        return {"status": "review_retest_generation_failed", "status_code": 500}

    now = _utcnow()
    item = _find_item(_review_items(refreshed_session.agent_state), normalized_id)
    if item is None:
        return {"status": "review_item_not_found", "status_code": 404}
    item["status"] = "in_progress"
    item["phase"] = "retest"
    item["practice_event_id"] = normalized_practice_event_id
    item["practice_completed_at"] = _as_text(practice_event.get("received_at"), _iso(now))
    item["retest_resource_id"] = _as_text(getattr(quiz_card, "resource_id", ""))
    item["updated_at"] = _iso(now)
    persist_session(refreshed_session)

    return {
        "status": "ok",
        "review_item": _serialize_item(item),
        "learning_task": {
            "node_id": node_id,
            "focus_resource_type": "diagnostic_quiz",
            "phase": "retest",
            "retest_resource_id": item["retest_resource_id"],
        },
    }
