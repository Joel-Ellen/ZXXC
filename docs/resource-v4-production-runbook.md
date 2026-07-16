# Resource v4 production runbook

## Deployment contract

- Run `alembic upgrade head` before deploying v4 binaries. Rollback never runs a schema downgrade.
- Keep v3 readers and writers available for at least 14 days and two release cycles.
- API runs at least 3 replicas with `EDUAGENT_RESOURCE_IN_PROCESS_WORKERS=false`.
- Worker runs at least 8 replicas with 8 stage slots each and scales to 20 from queue age.
- PostgreSQL is the queue and event source of truth. Redis is only a wakeup channel.
- Production workers must not mount a Docker socket. `SANDBOX_RUNNER_URL` points to an isolated gVisor/Kata/Firecracker service.
- Production Elasticsearch hosts must use `https://`, authentication and certificate verification. The application reads only `resource-kb-v4-read`; ingestion writes through `resource-kb-v4-write`.
- Set `EDUAGENT_PROMETHEUS_PORT=9108` on API and worker pods. Prometheus must scrape both services and retain aggregate metrics for 13 months.
- Set provider-normalized input/output microunit rates and a per-bundle cost budget before enabling a production cohort.
- Set `RESOURCE_V4_NLI_CALIBRATED=true` only after the selected artifact passes the fixed evaluation dataset, and pin `NLI_MODEL_ARTIFACT_DIGEST` to its immutable digest.

## Required gates

1. Run `python scripts/run_resource_v4_eval.py`.
2. Calibrate the selected NLI artifact with `python scripts/evaluate_nli_artifact.py --predictions ... --artifact-digest sha256:...`.
3. Run contract, migration, lease, worker-kill, tenant-isolation, prompt-injection, ES, Redis, provider and sandbox fault tests.
4. Complete 50-concurrent generation load, a 4-hour soak, database failover, ES alias rollback and sandbox outage drills in staging.

## Capacity and soak

Create a secret, temporary JSON or JSONL file with at least 50 distinct staging targets. Never commit this file or upload it as an artifact:

```json
[
  {"session_id": "user-a:course-a", "node_id": "N01", "token": "redacted"},
  {"session_id": "user-b:course-a", "node_id": "N02", "token": "redacted"}
]
```

Run real generation capacity, not repeated requests for one learner:

```bash
python scripts/resource_v4_load_test.py \
  --base-url "$STAGING_BASE_URL" \
  --accounts-file "$RESOURCE_V4_STAGING_ACCOUNTS" \
  --mode generation \
  --concurrency 50 \
  --requests 200
```

Run the soak with the same isolated staging accounts:

```bash
python scripts/resource_v4_load_test.py \
  --base-url "$STAGING_BASE_URL" \
  --accounts-file "$RESOURCE_V4_STAGING_ACCOUNTS" \
  --mode generation \
  --concurrency 50 \
  --soak-hours 4
```

The driver fails unless API P95 is below 300ms, concept P95 below 30s, five-card P95 below 120s and both API acceptance and generation completion are at least 99.5%.

## Rollout and rollback

- Roll out in this order: offline evaluation, 7-day shadow, internal allowlist, 1%, 5%, 25%, 50%, 100%.
- Shadow traffic must remain below 10% of production generation capacity.
- Immediately roll back for any unsupported critical claim, cross-course evidence, tenant isolation failure, safety event or monitoring blindness.
- Roll back by setting `RESOURCE_QUALITY_V4_ROLLOUT_PERCENT=0` and restoring the previous immutable image digest.
- Switch `resource-kb-v4-read/write` aliases back to the prior index if the new knowledge index caused the regression.

## Alerts

- Page immediately for cross-course retrieval, unsupported critical claims, sandbox escape, unattributed publication or telemetry schema failure.
- Alert for oldest queue age over 60 seconds, generation failure over 1%, fallback over 5%, provider breaker open over 5 minutes or forecast cost 20% above budget.
- Treat an absent `resource_telemetry_schema_valid` metric as monitoring blindness, not as a healthy zero.

## Retention

- Run `python scripts/resource_retention.py` daily.
- Evidence excerpts are stripped after 30 days, attempt metadata after 90 days and quality evaluations after 180 days.
- Prometheus-compatible aggregate metrics are retained by the managed monitoring backend for 13 months.

## External evidence

The release owner must attach the online Alembic result, NLI calibration report and artifact digest, 50-concurrency report, 4-hour soak report, worker-kill takeover report, database failover report, ES alias rollback report and sandbox-outage report to the release record. Repository tests do not substitute for managed infrastructure drills.
