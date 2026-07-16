"""Production policy constants and deterministic resource-v4 rollout."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass


PIPELINE_VERSION = "resource-v4"
PROMPT_VERSION = "resource-v4.1"
BLUEPRINT_VERSION = "resource-blueprint-v1"
QUALITY_VERSION = "resource-quality-v4.1"
MAX_GENERATION_CALLS = 8
MAX_INPUT_TOKENS = 45_000
MAX_OUTPUT_TOKENS = 12_000
CONCEPT_DEADLINE_SECONDS = 30
BUNDLE_DEADLINE_SECONDS = 120


def _csv_set(name: str) -> set[str]:
    return {
        item.strip()
        for item in str(os.environ.get(name) or "").split(",")
        if item.strip()
    }


def _percent(name: str) -> int:
    try:
        value = int(os.environ.get(name, "0"))
    except (TypeError, ValueError):
        value = 0
    return max(0, min(100, value))


def _bucket(user_id: str, course_id: str, node_id: str) -> int:
    digest = hashlib.sha256(
        f"{user_id}|{course_id}|{node_id}|resource-v4".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:4], "big") % 100


@dataclass(frozen=True)
class RolloutDecision:
    enabled: bool
    exposure_mode: str
    cohort: str


def resource_v4_rollout(
    user_id: str,
    course_id: str,
    node_id: str,
    *,
    requested_shadow: bool = False,
) -> RolloutDecision:
    allowlist = _csv_set("RESOURCE_QUALITY_V4_ALLOWLIST") | _csv_set(
        "EDUAGENT_RESOURCE_QUALITY_V4_ALLOWLIST"
    )
    denylist = _csv_set("RESOURCE_QUALITY_V4_DENYLIST") | _csv_set(
        "EDUAGENT_RESOURCE_QUALITY_V4_DENYLIST"
    )
    if user_id in denylist:
        return RolloutDecision(False, "normal", "v3-denylist")
    enabled = user_id in allowlist or _bucket(user_id, course_id, node_id) < max(
        _percent("RESOURCE_QUALITY_V4_ROLLOUT_PERCENT"),
        _percent("EDUAGENT_RESOURCE_QUALITY_V4_ROLLOUT_PERCENT"),
    )
    calibrated = str(
        os.environ.get("RESOURCE_V4_NLI_CALIBRATED")
        or os.environ.get("EDUAGENT_RESOURCE_V4_NLI_CALIBRATED")
        or ""
    ).strip().lower() in {"1", "true", "yes", "on"}
    digest_pinned = str(
        os.environ.get("NLI_MODEL_ARTIFACT_DIGEST") or ""
    ).startswith("sha256:")
    if requested_shadow:
        if not calibrated or not digest_pinned:
            return RolloutDecision(False, "normal", "v4-shadow-blocked-nli")
        return RolloutDecision(True, "shadow", "v4-shadow")
    if enabled and (not calibrated or not digest_pinned):
        return RolloutDecision(False, "normal", "v4-blocked-nli")
    return RolloutDecision(
        enabled,
        "normal",
        "v4-rollout" if enabled else "v3-control",
    )
