from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Mapping, Optional


_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", "disabled"})


@dataclass(frozen=True)
class RolloutDecision:
    feature: str
    enabled: bool
    cohort: str
    bucket: float
    percent: float


def _feature_key(feature: str) -> str:
    normalized = "_".join(str(feature or "").strip().upper().replace("-", "_").split())
    if not normalized or not all(char.isalnum() or char == "_" for char in normalized):
        raise ValueError("feature must contain only letters, digits, spaces, hyphens, or underscores")
    return normalized


def _csv_values(value: object) -> set[str]:
    return {
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    }


def _rollout_percent(value: object, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float(default)
    return max(0.0, min(100.0, parsed))


def rollout_decision(
    feature: str,
    subject: str,
    *,
    default_percent: float = 100.0,
    environment: Optional[Mapping[str, str]] = None,
) -> RolloutDecision:
    """Return a stable rollout assignment without retaining learner identity."""
    source = os.environ if environment is None else environment
    key = _feature_key(feature)
    normalized_subject = str(subject or "").strip()
    percent = _rollout_percent(
        source.get(f"EDUAGENT_{key}_ROLLOUT_PERCENT"),
        default_percent,
    )
    allowlist = _csv_values(source.get(f"EDUAGENT_{key}_ROLLOUT_ALLOWLIST"))
    denylist = _csv_values(source.get(f"EDUAGENT_{key}_ROLLOUT_DENYLIST"))

    if normalized_subject in denylist:
        return RolloutDecision(feature=feature, enabled=False, cohort="denylist", bucket=100.0, percent=percent)
    if normalized_subject in allowlist:
        return RolloutDecision(feature=feature, enabled=True, cohort="allowlist", bucket=0.0, percent=percent)

    digest = hashlib.sha256(f"eduagent:{key}:{normalized_subject}".encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") / float(2**64) * 100.0
    enabled = bool(normalized_subject) and bucket < percent
    return RolloutDecision(
        feature=feature,
        enabled=enabled,
        cohort="rollout" if enabled else "holdback",
        bucket=round(bucket, 6),
        percent=percent,
    )


def operational_switch(
    name: str,
    *,
    default: bool = False,
    environment: Optional[Mapping[str, str]] = None,
) -> bool:
    """Read a strict boolean operations switch with a fail-closed fallback."""
    source = os.environ if environment is None else environment
    key = _feature_key(name)
    raw = source.get(f"EDUAGENT_ENABLE_{key}")
    if raw is None or not str(raw).strip():
        return bool(default)
    normalized = str(raw).strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return bool(default)
