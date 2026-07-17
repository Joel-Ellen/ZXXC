"""Hardened clients for resource-v4 model sidecars."""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional

import httpx

from src.observability import get_request_context, set_metric

try:
    from opentelemetry.propagate import inject as inject_trace_headers
except ImportError:  # pragma: no cover - optional in minimal local installs
    inject_trace_headers = None


class ServiceUnavailable(RuntimeError):
    pass


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    open_seconds: float = 30.0

    def __post_init__(self) -> None:
        self._failures = 0
        self._open_until = 0.0
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            return time.monotonic() >= self._open_until

    @property
    def is_open(self) -> bool:
        with self._lock:
            return time.monotonic() < self._open_until

    def success(self) -> None:
        with self._lock:
            self._failures = 0
            self._open_until = 0.0

    def failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._open_until = time.monotonic() + self.open_seconds
                self._failures = 0


class _JsonServiceClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float,
        token: str = "",
    ) -> None:
        self.base_url = str(base_url or "").rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.token = token
        self.breaker = CircuitBreaker()

    @property
    def available(self) -> bool:
        return bool(self.base_url) and self.breaker.allow()

    def post(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        deadline_seconds: Optional[float] = None,
    ) -> dict[str, Any]:
        if not self.available:
            if self.base_url and self.breaker.is_open:
                set_metric(
                    "resource_provider_circuit_open",
                    1.0,
                    provider=type(self).__name__,
                )
            raise ServiceUnavailable(f"{type(self).__name__} is unavailable")
        context = get_request_context()
        deadline_at = str(context.get("deadline_at") or "").strip()
        remaining_seconds: Optional[float] = None
        if deadline_at:
            try:
                deadline = datetime.fromisoformat(
                    deadline_at.replace("Z", "+00:00")
                )
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                remaining_seconds = (
                    deadline.astimezone(timezone.utc)
                    - datetime.now(timezone.utc)
                ).total_seconds()
            except ValueError:
                deadline_at = ""
        if remaining_seconds is not None and remaining_seconds <= 0:
            raise ServiceUnavailable("deadline_exceeded")
        timeout = min(
            self.timeout_seconds,
            deadline_seconds if deadline_seconds is not None else self.timeout_seconds,
            remaining_seconds if remaining_seconds is not None else self.timeout_seconds,
        )
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        trace_id = str(
            context.get("trace_id")
            or context.get("request_id")
            or ""
        ).strip()
        if trace_id:
            headers["X-Trace-ID"] = trace_id
        if deadline_at:
            headers["X-Deadline-At"] = deadline_at
        headers["X-Request-Timeout-Ms"] = str(
            max(100, int(max(0.1, timeout) * 1000))
        )
        if inject_trace_headers is not None:
            inject_trace_headers(headers)
        try:
            response = httpx.post(
                f"{self.base_url}/{path.lstrip('/')}",
                json=dict(payload),
                headers=headers,
                timeout=max(0.1, timeout),
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("service returned a non-object JSON payload")
            self.breaker.success()
            set_metric(
                "resource_provider_circuit_open",
                0.0,
                provider=type(self).__name__,
            )
            return result
        except Exception as exc:
            self.breaker.failure()
            set_metric(
                "resource_provider_circuit_open",
                1.0 if self.breaker.is_open else 0.0,
                provider=type(self).__name__,
            )
            raise ServiceUnavailable(type(exc).__name__) from exc


class NLIServiceClient(_JsonServiceClient):
    def __init__(self) -> None:
        super().__init__(
            os.environ.get("NLI_SERVICE_URL", ""),
            timeout_seconds=2.0,
            token=os.environ.get("NLI_SERVICE_TOKEN", ""),
        )
        self.artifact_digest = os.environ.get("NLI_MODEL_ARTIFACT_DIGEST", "")

    @property
    def rollout_ready(self) -> bool:
        return self.available and self.artifact_digest.startswith("sha256:")

    def entailment(
        self,
        evidence: str,
        hypothesis: str,
        *,
        threshold: float,
    ) -> dict[str, Any]:
        result = self.post(
            "/v1/entailment",
            {
                "premise": evidence,
                "hypothesis": hypothesis,
                "artifact_digest": self.artifact_digest,
            },
        )
        score = float(result.get("entailment") or 0.0)
        contradiction = float(result.get("contradiction") or 0.0)
        return {
            "passed": score >= threshold and contradiction < 0.5,
            "entailment": score,
            "contradiction": contradiction,
            "artifact_digest": str(
                result.get("artifact_digest") or self.artifact_digest
            ),
        }


class EmbeddingServiceClient(_JsonServiceClient):
    def __init__(self) -> None:
        super().__init__(
            os.environ.get("EMBEDDING_SERVICE_URL", ""),
            timeout_seconds=2.0,
            token=os.environ.get("EMBEDDING_SERVICE_TOKEN", ""),
        )

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        result = self.post("/v1/embeddings", {"texts": list(texts)})
        vectors = result.get("embeddings")
        if not isinstance(vectors, list):
            raise ServiceUnavailable("embedding response is missing vectors")
        return vectors


class SandboxRunnerClient(_JsonServiceClient):
    def __init__(self) -> None:
        super().__init__(
            os.environ.get("SANDBOX_RUNNER_URL", ""),
            timeout_seconds=3.0,
            token=os.environ.get("SANDBOX_RUNNER_TOKEN", ""),
        )

    def verify(
        self,
        *,
        source_code: str,
        public_tests: list[dict[str, Any]],
        hidden_test_set_id: str,
    ) -> dict[str, Any]:
        return self.post(
            "/v1/verify",
            {
                "language": "python",
                "source_code": source_code,
                "public_tests": public_tests,
                "hidden_test_set_id": hidden_test_set_id,
                "limits": {
                    "cpu": 1,
                    "memory_mb": 128,
                    "timeout_ms": 2_000,
                    "output_bytes": 65_536,
                    "network": "none",
                    "root_filesystem": "read_only",
                    "run_as_non_root": True,
                },
            },
            deadline_seconds=3.0,
        )


class DiagnosticBlindVerifierClient(_JsonServiceClient):
    def __init__(self) -> None:
        super().__init__(
            os.environ.get("DIAGNOSTIC_VERIFIER_URL", ""),
            timeout_seconds=5.0,
            token=os.environ.get("DIAGNOSTIC_VERIFIER_TOKEN", ""),
        )

    def verify(self, questions: list[dict[str, Any]]) -> dict[str, Any]:
        return self.post(
            "/v1/blind-answer",
            {
                "questions": [
                    {
                        "id": item.get("id"),
                        "prompt": item.get("prompt"),
                        "options": item.get("options"),
                    }
                    for item in questions
                ]
            },
        )


_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all instructions",
    "system prompt",
    "developer message",
    "you are chatgpt",
    "请忽略之前",
    "忽略以上指令",
    "系统提示词",
)


def sanitize_untrusted_evidence(value: str) -> tuple[str, bool]:
    text = str(value or "").replace("\x00", " ")
    lowered = text.casefold()
    detected = any(marker in lowered for marker in _INJECTION_MARKERS)
    if detected:
        for marker in _INJECTION_MARKERS:
            text = re.sub(
                re.escape(marker),
                "[removed-untrusted-instruction]",
                text,
                flags=re.IGNORECASE,
            )
    return text[:8_000], detected


def content_hash(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()
