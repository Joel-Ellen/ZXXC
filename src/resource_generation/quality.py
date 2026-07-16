"""Resource-v4 weighted quality scoring and non-bypassable gates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from src.observability import incr_metric

from .context import ResourceContext
from .services import (
    DiagnosticBlindVerifierClient,
    NLIServiceClient,
    SandboxRunnerClient,
    ServiceUnavailable,
)


QUALITY_WEIGHTS = {
    "factual": 30,
    "evidence": 15,
    "pedagogy": 20,
    "personalization": 15,
    "verifiability": 10,
    "coordination": 5,
    "language": 5,
}


@dataclass(frozen=True)
class QualityEvaluation:
    score: float
    gate_status: str
    dimensions: dict[str, float]
    issue_codes: tuple[str, ...]
    hard_fail: bool
    artifact_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "gate_status": self.gate_status,
            "dimensions": self.dimensions,
            "issue_codes": list(self.issue_codes),
            "hard_fail": self.hard_fail,
            "artifact_digest": self.artifact_digest,
        }


def _evidence_text(context: ResourceContext, ids: set[str]) -> str:
    return "\n".join(
        str(ref.get("excerpt") or "")
        for ref in context.knowledge_refs
        if str(ref.get("id") or "") in ids
    )[:16_000]


def _learner_visible_text(payload: Mapping[str, Any]) -> str:
    values: list[str] = []
    for key, value in payload.items():
        if key in {
            "source_ref_ids",
            "evidence_map",
            "quality_profile",
            "answer_index",
            "verification",
        }:
            continue
        values.append(str(value))
    return "\n".join(values)


def _language_score(
    payload: Mapping[str, Any],
    locale: str,
    card_type: str,
) -> float:
    language = str(
        payload.get("content_language")
        if card_type == "code_snippet"
        else payload.get("language")
        or payload.get("content_language")
        or ""
    )
    if language != locale:
        return 0.0
    if not locale.lower().startswith("zh"):
        return 100.0
    text = _learner_visible_text(payload)
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_words = len(re.findall(r"\b[A-Za-z]{3,}\b", text))
    # API names and code are controlled exceptions; only reject a clearly
    # English-dominant learner-facing payload.
    return 100.0 if chinese >= max(8, latin_words) else 60.0


def evaluate_resource_quality(
    card_type: str,
    payload: Mapping[str, Any],
    context: ResourceContext,
    *,
    nli: Optional[NLIServiceClient] = None,
    sandbox: Optional[SandboxRunnerClient] = None,
    diagnostic_verifier: Optional[DiagnosticBlindVerifierClient] = None,
) -> QualityEvaluation:
    issues: list[str] = []
    hard_fail = False
    known_ids = {
        str(ref.get("id") or "")
        for ref in context.knowledge_refs
        if str(ref.get("id") or "")
    }
    if any(
        str(ref.get("course_id") or context.course_id) != context.course_id
        for ref in context.knowledge_refs
        if isinstance(ref, dict)
    ):
        issues.append("cross_course_evidence")
        hard_fail = True
    objective_ids = {
        str(value)
        for value in payload.get("objective_ids", [])
        if str(value).strip()
    }
    evidence_map = payload.get("evidence_map")
    evidence_map = evidence_map if isinstance(evidence_map, dict) else {}
    mapped_ids = {
        str(ref_id)
        for values in evidence_map.values()
        if isinstance(values, list)
        for ref_id in values
    }
    unknown = mapped_ids - known_ids
    if unknown:
        issues.append("unknown_evidence_reference")
        hard_fail = True
    if not objective_ids:
        issues.append("objective_ids_missing")
    if not evidence_map:
        issues.append("evidence_map_missing")

    blueprint = payload.get("learning_blueprint") or context.blueprint_snapshot
    claims = blueprint.get("claims", []) if isinstance(blueprint, dict) else []
    artifact_digest = ""
    factual_scores: list[float] = []
    nli_client = nli or NLIServiceClient()
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        evidence_ids = {
            str(value)
            for value in claim.get("evidence_ids", [])
            if str(value)
        }
        critical = bool(claim.get("critical", True))
        threshold = 0.85 if critical else 0.75
        if not evidence_ids or not evidence_ids.issubset(known_ids):
            issues.append(
                "critical_evidence_coverage_insufficient"
                if critical
                else "supporting_evidence_coverage_insufficient"
            )
            hard_fail = hard_fail or critical
            factual_scores.append(0.0)
            continue
        try:
            result = nli_client.entailment(
                _evidence_text(context, evidence_ids),
                str(claim.get("text") or ""),
                threshold=threshold,
            )
            artifact_digest = str(result.get("artifact_digest") or artifact_digest)
            factual_scores.append(float(result.get("entailment") or 0.0) * 100)
            if not result.get("passed"):
                issues.append(
                    "unsupported_critical_claim"
                    if critical
                    else "unsupported_supporting_claim"
                )
                hard_fail = hard_fail or critical
        except ServiceUnavailable:
            factual_scores.append(75.0 if critical else 60.0)
            issues.append(
                "critical_nli_unavailable"
                if critical
                else "supporting_nli_unavailable"
            )

    critical_fields = {
        "concept_map": {"definition", "constraints", "mechanism"},
        "code_snippet": {"scenario", "explanation", "complexity_notes"},
        "interactive_exercise": {"goal", "prompt", "solution_outline"},
        "video_summary": {"summary", "key_points"},
        "diagnostic_quiz": {"questions"},
    }[card_type]
    for field_name, raw_ids in evidence_map.items():
        if field_name not in payload or not isinstance(raw_ids, list):
            continue
        evidence_ids = {
            str(value)
            for value in raw_ids
            if str(value) in known_ids
        }
        critical = field_name in critical_fields
        threshold = 0.85 if critical else 0.75
        if not evidence_ids:
            issues.append(
                "critical_field_evidence_missing"
                if critical
                else "supporting_field_evidence_missing"
            )
            hard_fail = hard_fail or critical
            continue
        try:
            result = nli_client.entailment(
                _evidence_text(context, evidence_ids),
                str(payload.get(field_name) or "")[:4_000],
                threshold=threshold,
            )
            artifact_digest = str(
                result.get("artifact_digest") or artifact_digest
            )
            factual_scores.append(float(result.get("entailment") or 0.0) * 100)
            if not result.get("passed"):
                issues.append(
                    "unsupported_critical_field"
                    if critical
                    else "unsupported_supporting_field"
                )
                hard_fail = hard_fail or critical
        except ServiceUnavailable:
            factual_scores.append(75.0 if critical else 60.0)
            issues.append(
                "critical_field_nli_unavailable"
                if critical
                else "supporting_field_nli_unavailable"
            )

    if card_type == "code_snippet":
        verification = payload.get("verification")
        verification = verification if isinstance(verification, dict) else {}
        is_server_template = (
            payload.get("quality_profile", {}).get("generation_source")
            == "template"
            and verification.get("status") == "prevalidated_template"
        )
        if verification.get("status") != "verified":
            try:
                result = (sandbox or SandboxRunnerClient()).verify(
                    source_code=str(payload.get("code") or ""),
                    public_tests=[
                        dict(value)
                        for value in payload.get("boundary_tests", [])
                        if isinstance(value, dict)
                    ],
                    hidden_test_set_id=str(payload.get("example_binding") or ""),
                )
                if result.get("status") != "verified":
                    issues.append("code_verification_failed")
                    hard_fail = True
            except ServiceUnavailable:
                if is_server_template:
                    issues.append("sandbox_unavailable_prevalidated_template")
                else:
                    issues.append("sandbox_unavailable")
                    hard_fail = True

    if card_type == "video_summary":
        media_status = str(payload.get("media_status") or "")
        if media_status == "no_trusted_video":
            if payload.get("video_url") or payload.get("timeline"):
                issues.append("fabricated_video_metadata")
                hard_fail = True
        elif not payload.get("video_url") or not payload.get("video_source_id"):
            issues.append("trusted_video_attribution_missing")
            hard_fail = True

    if card_type == "diagnostic_quiz":
        questions = [
            value
            for value in payload.get("questions", [])
            if isinstance(value, dict)
        ]
        if not 5 <= len(questions) <= 7:
            issues.append("diagnostic_question_count_invalid")
        required_levels = {
            "concept",
            "understanding",
            "application",
            "boundary",
            "transfer",
        }
        if not required_levels.issubset(
            {str(item.get("level") or "") for item in questions}
        ):
            issues.append("diagnostic_coverage_incomplete")
        try:
            blind = (diagnostic_verifier or DiagnosticBlindVerifierClient()).verify(
                questions
            )
            if float(blind.get("agreement") or 0.0) < 0.98:
                issues.append("diagnostic_answer_inconsistent")
                hard_fail = True
        except ServiceUnavailable:
            is_server_template = (
                payload.get("quality_profile", {}).get("generation_source")
                == "template"
            )
            issues.append("diagnostic_blind_verifier_unavailable")
            hard_fail = hard_fail or not is_server_template

    factual = (
        sum(factual_scores) / len(factual_scores)
        if factual_scores
        else (0.0 if context.content_version.startswith("resource-v4") else 100.0)
    )
    evidence = 100.0 if evidence_map and not unknown else (50.0 if evidence_map else 0.0)
    pedagogy = 100.0
    if card_type == "interactive_exercise" and (
        not payload.get("rubric")
        or len(payload.get("hint_levels", {})) < 3
        or not payload.get("structured_checkpoints")
    ):
        pedagogy = 50.0
        issues.append("exercise_scaffolding_incomplete")
    personalization = 100.0 if context.mastery_bucket and context.learning_stage else 50.0
    verifiability = 100.0
    if any(
        code in issues
        for code in (
            "sandbox_unavailable",
            "diagnostic_blind_verifier_unavailable",
            "critical_nli_unavailable",
        )
    ):
        verifiability = 40.0
    coordination = 100.0 if objective_ids else 0.0
    language = _language_score(payload, context.locale, card_type)
    dimensions = {
        "factual": factual,
        "evidence": evidence,
        "pedagogy": pedagogy,
        "personalization": personalization,
        "verifiability": verifiability,
        "coordination": coordination,
        "language": language,
    }
    score = round(
        sum(dimensions[name] * weight for name, weight in QUALITY_WEIGHTS.items())
        / 100.0,
        2,
    )
    if hard_fail or score < 75:
        gate_status = "failed"
    elif context.evidence_status == "degraded" or any(
        code.endswith("_unavailable") for code in issues
    ):
        gate_status = "degraded"
    elif score < 85:
        gate_status = "warning"
    else:
        gate_status = "normal"
    unique_issues = tuple(dict.fromkeys(issues))
    incr_metric(
        "resource_quality_evaluation_total",
        card_type=card_type,
        gate_status=gate_status,
    )
    if any(
        code in {
            "unsupported_critical_claim",
            "unsupported_critical_field",
        }
        for code in unique_issues
    ):
        incr_metric(
            "resource_unsupported_critical_claim_total",
            card_type=card_type,
            gate_status=gate_status,
        )
    if "cross_course_evidence" in unique_issues:
        incr_metric(
            "resource_cross_course_recall_total",
            card_type=card_type,
            source="quality_gate",
        )
    return QualityEvaluation(
        score=score,
        gate_status=gate_status,
        dimensions=dimensions,
        issue_codes=unique_issues,
        hard_fail=hard_fail,
        artifact_digest=artifact_digest,
    )
