from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_compose_defaults_to_fail_closed_production_release() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "APP_ENV=production" in compose
    assert "JWT_SECRET_KEY=${JWT_SECRET_KEY:?" in compose
    assert "EDUAGENT_OPS_TOKEN=${EDUAGENT_OPS_TOKEN:?" in compose
    assert "POSTGRES_PASSWORD=${POSTGRES_PASSWORD:?" in compose
    assert "EDUAGENT_CODE_PRACTICE_ROLLOUT_PERCENT=${EDUAGENT_CODE_PRACTICE_ROLLOUT_PERCENT:-0}" in compose
    assert "EDUAGENT_ENABLE_COMPAT_API=false" in compose
    assert "EDUAGENT_ENABLE_PUBLIC_METRICS=false" in compose
    assert "postgres:16-alpine" in compose
    assert "redis:7-alpine" in compose


def test_container_healthcheck_uses_public_health_endpoint() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "http://localhost:8800/api/health" in dockerfile
    assert "http://localhost:8800/api/state" not in dockerfile
