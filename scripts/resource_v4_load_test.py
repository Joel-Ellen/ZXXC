"""Production capacity and soak driver for resource-v4 generation."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class Target:
    session_id: str
    node_id: str
    token: str


@dataclass(frozen=True)
class Result:
    api_ms: float
    status_code: int
    concept_ms: float | None = None
    complete_ms: float | None = None
    terminal_status: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--accounts-file")
    parser.add_argument("--session-id")
    parser.add_argument("--node-id", default="N01")
    parser.add_argument("--token")
    parser.add_argument(
        "--mode",
        choices=("api", "generation"),
        default="generation",
    )
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--soak-hours", type=float, default=0.0)
    parser.add_argument("--stream-timeout-seconds", type=float, default=135.0)
    args = parser.parse_args()
    if not args.accounts_file and not (args.session_id and args.token):
        parser.error(
            "provide --accounts-file or both --session-id and --token"
        )
    return args


def _target_from_mapping(value: dict[str, Any]) -> Target:
    target = Target(
        session_id=str(value.get("session_id") or "").strip(),
        node_id=str(value.get("node_id") or "N01").strip(),
        token=str(value.get("token") or "").strip(),
    )
    if not target.session_id or not target.node_id or not target.token:
        raise ValueError(
            "each account requires session_id, node_id and token"
        )
    return target


def load_targets(args: argparse.Namespace) -> list[Target]:
    if not args.accounts_file:
        targets = [
            Target(
                session_id=str(args.session_id),
                node_id=str(args.node_id),
                token=str(args.token),
            )
        ]
    else:
        path = Path(args.accounts_file)
        raw = path.read_text(encoding="utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = [
                json.loads(line)
                for line in raw.splitlines()
                if line.strip()
            ]
        if isinstance(payload, dict):
            payload = payload.get("accounts", [])
        if not isinstance(payload, list):
            raise ValueError("accounts file must be a JSON array or JSONL")
        targets = [
            _target_from_mapping(value)
            for value in payload
            if isinstance(value, dict)
        ]
    if args.mode == "generation" and len(targets) < args.concurrency:
        raise ValueError(
            "generation mode requires at least one distinct target per "
            "concurrent request so admission limits do not collapse the load"
        )
    return targets


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(
        len(ordered) - 1,
        max(0, int((len(ordered) - 1) * percentile)),
    )
    return ordered[index]


async def _track_job(
    client: httpx.AsyncClient,
    args: argparse.Namespace,
    target: Target,
    job_id: str,
    request_started: float,
) -> tuple[float | None, float | None, str]:
    concept_ms: float | None = None
    event_type = ""
    data_lines: list[str] = []
    url = (
        f"{args.base_url.rstrip('/')}/api/resource-generation-jobs/"
        f"{job_id}/events"
    )

    async def consume_event() -> tuple[bool, str]:
        nonlocal concept_ms, event_type, data_lines
        if not event_type and not data_lines:
            return False, ""
        try:
            payload = json.loads("\n".join(data_lines) or "{}")
        except json.JSONDecodeError:
            payload = {}
        elapsed_ms = (time.perf_counter() - request_started) * 1000
        if (
            event_type == "card_ready"
            and payload.get("card_type") == "concept_map"
            and concept_ms is None
        ):
            concept_ms = elapsed_ms
        terminal = ""
        if event_type in {"completed", "failed", "cancelled"}:
            terminal = str(payload.get("status") or event_type)
        event_type = ""
        data_lines = []
        return bool(terminal), terminal

    timeout = httpx.Timeout(
        connect=10.0,
        read=max(10.0, float(args.stream_timeout_seconds)),
        write=10.0,
        pool=10.0,
    )
    try:
        async with client.stream(
            "GET",
            url,
            headers={
                "Authorization": f"Bearer {target.token}",
                "Accept": "text/event-stream",
            },
            timeout=timeout,
        ) as response:
            if response.status_code != 200:
                return concept_ms, None, f"http_{response.status_code}"
            async for line in response.aiter_lines():
                if line == "":
                    done, terminal = await consume_event()
                    if done:
                        complete_ms = (
                            time.perf_counter() - request_started
                        ) * 1000
                        return concept_ms, complete_ms, terminal
                    continue
                if line.startswith("event:"):
                    event_type = line.partition(":")[2].strip()
                elif line.startswith("data:"):
                    data_lines.append(line.partition(":")[2].lstrip())
            done, terminal = await consume_event()
            if done:
                complete_ms = (
                    time.perf_counter() - request_started
                ) * 1000
                return concept_ms, complete_ms, terminal
    except (httpx.HTTPError, asyncio.TimeoutError):
        return concept_ms, None, "stream_error"
    return concept_ms, None, "stream_closed"


async def one_request(
    client: httpx.AsyncClient,
    args: argparse.Namespace,
    target: Target,
) -> Result:
    started = time.perf_counter()
    try:
        response = await client.post(
            (
                f"{args.base_url.rstrip('/')}/api/sessions/"
                f"{target.session_id}/resources/{target.node_id}/generation"
            ),
            headers={"Authorization": f"Bearer {target.token}"},
            json={
                "card_types": [
                    "concept_map",
                    "code_snippet",
                    "interactive_exercise",
                    "video_summary",
                    "diagnostic_quiz",
                ],
                "force": True,
                "priority": "normal",
            },
        )
    except httpx.HTTPError:
        return Result(
            api_ms=(time.perf_counter() - started) * 1000,
            status_code=599,
            terminal_status="request_error",
        )
    api_ms = (time.perf_counter() - started) * 1000
    if args.mode == "api" or response.status_code >= 300:
        return Result(api_ms=api_ms, status_code=response.status_code)
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    job_id = str(payload.get("job_id") or "")
    if not job_id:
        return Result(
            api_ms=api_ms,
            status_code=response.status_code,
            terminal_status="missing_job_id",
        )
    concept_ms, complete_ms, terminal = await _track_job(
        client,
        args,
        target,
        job_id,
        started,
    )
    return Result(
        api_ms=api_ms,
        status_code=response.status_code,
        concept_ms=concept_ms,
        complete_ms=complete_ms,
        terminal_status=terminal,
    )


async def run(args: argparse.Namespace) -> int:
    targets = load_targets(args)
    limits = httpx.Limits(
        max_connections=max(100, args.concurrency * 2),
        max_keepalive_connections=max(50, args.concurrency),
    )
    request_timeout = httpx.Timeout(15.0)
    results: list[Result] = []
    deadline = (
        time.monotonic() + args.soak_hours * 3600
        if args.soak_hours > 0
        else None
    )
    total = 0
    async with httpx.AsyncClient(
        timeout=request_timeout,
        limits=limits,
    ) as client:
        while total < args.requests or (
            deadline is not None and time.monotonic() < deadline
        ):
            batch_size = args.concurrency
            if deadline is None:
                batch_size = min(
                    batch_size,
                    max(0, args.requests - total),
                )
            if batch_size <= 0:
                break
            batch_targets = [
                targets[(total + offset) % len(targets)]
                for offset in range(batch_size)
            ]
            batch = await asyncio.gather(*[
                one_request(client, args, target)
                for target in batch_targets
            ])
            results.extend(batch)
            total += len(batch)
            if deadline is not None:
                await asyncio.sleep(1.0)

    api_values = [result.api_ms for result in results]
    concept_values = [
        result.concept_ms
        for result in results
        if result.concept_ms is not None
    ]
    complete_values = [
        result.complete_ms
        for result in results
        if result.complete_ms is not None
    ]
    accepted = sum(200 <= result.status_code < 300 for result in results)
    completed = sum(
        result.terminal_status == "completed"
        for result in results
    )
    summary = {
        "mode": args.mode,
        "requests": len(results),
        "targets": len(targets),
        "accepted": accepted,
        "api_success_rate": accepted / max(1, len(results)),
        "api_p50_ms": statistics.median(api_values) if api_values else None,
        "api_p95_ms": _percentile(api_values, 0.95),
        "concept_samples": len(concept_values),
        "concept_p95_ms": _percentile(concept_values, 0.95),
        "complete_samples": len(complete_values),
        "complete_p95_ms": _percentile(complete_values, 0.95),
        "generation_success_rate": (
            completed / max(1, len(results))
            if args.mode == "generation"
            else None
        ),
        "terminal_status_counts": {
            status: sum(
                result.terminal_status == status
                for result in results
            )
            for status in sorted({
                result.terminal_status
                for result in results
                if result.terminal_status
            })
        },
    }
    print(json.dumps(summary, sort_keys=True))

    api_p95 = summary["api_p95_ms"]
    if api_p95 is None or api_p95 >= 300:
        return 2
    if summary["api_success_rate"] < 0.995:
        return 3
    if args.mode == "generation":
        concept_p95 = summary["concept_p95_ms"]
        complete_p95 = summary["complete_p95_ms"]
        if concept_p95 is None or concept_p95 >= 30_000:
            return 4
        if complete_p95 is None or complete_p95 >= 120_000:
            return 5
        if summary["generation_success_rate"] < 0.995:
            return 6
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
