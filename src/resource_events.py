"""Best-effort Redis wakeups for durable PostgreSQL resource events."""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Iterator, Optional


class ResourceEventNotifier:
    """Redis never carries event truth; it only wakes PostgreSQL readers."""

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self.redis_url = redis_url or os.environ.get("REDIS_URL", "")
        self._client: Any = None
        self._lock = threading.Lock()

    def _get_client(self) -> Any:
        if not self.redis_url:
            return None
        with self._lock:
            if self._client is not None:
                return self._client
            try:
                import redis

                self._client = redis.Redis.from_url(
                    self.redis_url,
                    socket_connect_timeout=0.2,
                    socket_timeout=0.2,
                    decode_responses=True,
                )
            except Exception:
                self._client = None
            return self._client

    def publish(self, job_id: str, event_id: int) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            client.publish(
                f"resource-job:{job_id}",
                json.dumps({"job_id": job_id, "event_id": int(event_id)}),
            )
            return True
        except Exception:
            return False

    def listen(
        self,
        job_id: str,
        *,
        timeout_seconds: float = 2.0,
    ) -> Iterator[dict[str, Any]]:
        client = self._get_client()
        if client is None:
            return
        pubsub = None
        try:
            pubsub = client.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(f"resource-job:{job_id}")
            while True:
                message = pubsub.get_message(timeout=timeout_seconds)
                if not message:
                    return
                try:
                    payload = json.loads(message.get("data") or "{}")
                except (TypeError, ValueError):
                    continue
                if isinstance(payload, dict):
                    yield payload
        except Exception:
            return
        finally:
            if pubsub is not None:
                try:
                    pubsub.close()
                except Exception:
                    pass

    def wait(
        self,
        job_id: str,
        *,
        after_event_id: int,
        timeout_seconds: float,
    ) -> bool:
        """Wait for a newer wakeup; callers must still replay PostgreSQL."""
        for payload in self.listen(
            job_id,
            timeout_seconds=max(0.01, float(timeout_seconds)),
        ):
            try:
                event_id = int(payload.get("event_id") or 0)
            except (TypeError, ValueError):
                continue
            if event_id > int(after_event_id):
                return True
        return False


notifier = ResourceEventNotifier()
