from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _compose_service(compose: str, service: str, next_service: str) -> str:
    start_match = re.search(rf"^  {re.escape(service)}:\s*$", compose, flags=re.MULTILINE)
    end_match = re.search(rf"^  {re.escape(next_service)}:\s*$", compose, flags=re.MULTILINE)
    assert start_match is not None
    assert end_match is not None
    start = start_match.start()
    end = end_match.start()
    assert start < end
    return compose[start:end]


def _nginx_tutor_location(config: str) -> str:
    marker = "location ~ ^/api/sessions/[^/]+/tutor(?:-stream)?$ {"
    start = config.index(marker)
    end = config.index("\n    }", start)
    return config[start:end]


def test_compose_defaults_to_fail_closed_production_release() -> None:
    compose = _read("docker-compose.yml")

    assert "APP_ENV=production" in compose
    assert "JWT_SECRET_KEY=${JWT_SECRET_KEY:?" in compose
    assert "EDUAGENT_OPS_TOKEN=${EDUAGENT_OPS_TOKEN:?" in compose
    assert "POSTGRES_PASSWORD=${POSTGRES_PASSWORD:?" in compose
    assert "REDIS_PASSWORD=${REDIS_PASSWORD:?" in compose
    assert "NEO4J_PASSWORD=${NEO4J_PASSWORD:?" in compose
    assert "MINIO_ROOT_USER=${MINIO_ACCESS_KEY:?" in compose
    assert "MINIO_ROOT_PASSWORD=${MINIO_SECRET_KEY:?" in compose
    assert "EDUAGENT_CODE_PRACTICE_ROLLOUT_PERCENT=${EDUAGENT_CODE_PRACTICE_ROLLOUT_PERCENT:-0}" in compose
    assert "EDUAGENT_APP_ACCESS_ROLLOUT_PERCENT=${EDUAGENT_APP_ACCESS_ROLLOUT_PERCENT:-0}" in compose
    assert "EDUAGENT_APP_ACCESS_ROLLOUT_ALLOWLIST=${EDUAGENT_APP_ACCESS_ROLLOUT_ALLOWLIST:-}" in compose
    assert "EDUAGENT_APP_ACCESS_ROLLOUT_DENYLIST=${EDUAGENT_APP_ACCESS_ROLLOUT_DENYLIST:-}" in compose
    assert "EDUAGENT_RATE_LIMIT_BACKEND=redis" in compose
    assert "EDUAGENT_TRUST_PROXY_HEADERS=true" in compose
    assert "EDUAGENT_ENABLE_COMPAT_API=false" in compose
    assert "EDUAGENT_ENABLE_PUBLIC_METRICS=false" in compose
    assert "EduAgent2024!" not in compose
    assert "minioadmin" not in compose


def test_compose_hardens_app_runtime_and_limits_writes_to_named_storage() -> None:
    compose = _read("docker-compose.yml")
    app = _compose_service(compose, "app", "postgres")

    for contract in (
        'user: "10001:10001"',
        "read_only: true",
        "no-new-privileges:true",
        "cap_drop:\n      - ALL",
        "/tmp:rw,nosuid,nodev,noexec,size=256m,mode=1777",
        "app-data:/app/data",
        "app-cache:/app/cache",
        "app-backups:/app/backups",
        "app-logs:/app/logs",
    ):
        assert contract in app

    assert "./backups:/app/backups" not in app
    assert "./logs:/app/logs" not in app
    for volume in ("app-data", "app-cache", "app-backups", "app-logs"):
        assert f"  {volume}:\n" in compose


def test_compose_uses_authenticated_redis_for_shared_rate_limits() -> None:
    compose = _read("docker-compose.yml")
    app = _compose_service(compose, "app", "postgres")
    redis = _compose_service(compose, "redis", "neo4j")

    assert "REDIS_URL=redis://:${REDIS_PASSWORD:?REDIS_PASSWORD is required}@redis:6379/0" in app
    assert "EDUAGENT_RATE_LIMIT_BACKEND=redis" in app
    assert "REDIS_PASSWORD=${REDIS_PASSWORD:?REDIS_PASSWORD is required}" in redis
    assert "--requirepass" in redis
    assert "redis-cli --no-auth-warning" in redis
    assert "$$REDIS_PASSWORD" in redis
    assert "grep -q PONG" in redis


def test_compose_uses_the_elasticsearch_environment_name_consumed_by_app() -> None:
    compose = _read("docker-compose.yml")
    app = _compose_service(compose, "app", "postgres")

    assert "ES_HOSTS=http://elasticsearch:9200" in app
    assert re.search(r"^\s*- ES_HOST=", app, flags=re.MULTILINE) is None


def test_example_environment_does_not_publish_production_credentials() -> None:
    example = _read(".env.example")

    for name in (
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "NEO4J_PASSWORD",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "JWT_SECRET_KEY",
        "EDUAGENT_OPS_TOKEN",
    ):
        assert re.search(rf"^{name}=$", example, flags=re.MULTILINE)

    assert "EDUAGENT_APP_ACCESS_ROLLOUT_PERCENT=0" in example
    assert "EDUAGENT_RATE_LIMIT_BACKEND=redis" in example
    assert "EduAgent2024!" not in example
    assert "minioadmin" not in example


def test_runtime_image_is_non_root_and_excludes_development_sources() -> None:
    dockerfile = _read("Dockerfile")
    dockerignore = _read(".dockerignore")
    runtime = dockerfile.split("FROM python:3.11-slim AS runtime", maxsplit=1)[1]
    users = re.findall(r"^USER\s+(.+)$", runtime, flags=re.MULTILINE)

    assert users == ["10001:10001"]
    assert "COPY --chown=10001:10001 src/ ./src/" in runtime
    assert "COPY tests/" not in dockerfile
    assert "COPY scripts/" not in dockerfile
    assert "gcc" not in runtime
    assert "libc6-dev" not in runtime
    for runtime_state in (
        "src/auth/_users.json",
        "frontend/_account_state.json",
        "frontend/_user_profiles.json",
        "frontend/_enrollments.json",
    ):
        assert runtime_state in dockerignore
    assert "*.tar.gz" in dockerignore


def test_image_build_defaults_to_official_package_registries() -> None:
    dockerfile = _read("Dockerfile")
    compose = _read("docker-compose.yml")

    assert "ARG NPM_REGISTRY=https://registry.npmjs.org" in dockerfile
    assert "ARG PIP_INDEX_URL=https://pypi.org/simple" in dockerfile
    assert "registry.npmmirror.com" not in dockerfile
    assert "pypi.tuna.tsinghua.edu.cn" not in dockerfile
    assert "NPM_REGISTRY: ${NPM_REGISTRY:-https://registry.npmjs.org}" in compose
    assert "PIP_INDEX_URL: ${PIP_INDEX_URL:-https://pypi.org/simple}" in compose


def test_container_healthcheck_uses_readiness_and_liveness_is_retained() -> None:
    dockerfile = _read("Dockerfile")
    health_routes = _read("src/routes/new_api_routes.py")
    app_server = _read("frontend/server.py")

    assert "http://localhost:8800/api/ready" in dockerfile
    assert "http://localhost:8800/api/health" not in dockerfile
    assert "http://localhost:8800/api/state" not in dockerfile
    assert 'Route("/api/health", api_health, methods=["GET"])' in health_routes
    assert 'return {"status": "ok"}' in health_routes
    assert 'Route("/api/ready", api_readiness, methods=["GET"])' in app_server
    assert '{"status": "not_ready"}' in app_server


def test_nginx_streams_the_canonical_tutor_endpoint_without_buffering() -> None:
    for relative_path in (
        "nginx/edu-agent.conf",
        "nginx/edu-agent-standalone.conf",
    ):
        config = _read(relative_path)
        tutor = _nginx_tutor_location(config)

        assert "proxy_http_version 1.1;" in tutor
        assert 'proxy_set_header Connection "";' in tutor
        assert "proxy_set_header X-Forwarded-Proto $scheme;" in tutor
        assert "proxy_set_header X-Forwarded-For $remote_addr;" in tutor
        assert "proxy_buffering off;" in tutor
        assert "proxy_cache off;" in tutor
        assert "proxy_read_timeout 300s;" in tutor
        assert "proxy_send_timeout 300s;" in tutor
        assert 'add_header X-Accel-Buffering "no" always;' in tutor
        assert "location /api/pipeline/stream" not in config
        assert "client_max_body_size 1m;" in config
        assert "$proxy_add_x_forwarded_for" not in config
        assert config.count("{") == config.count("}")


def test_standalone_nginx_listener_cannot_proxy_to_itself() -> None:
    config = _read("nginx/edu-agent-standalone.conf")

    assert re.search(r"^\s*listen\s+8080;", config, flags=re.MULTILINE)
    assert re.search(r"^\s*server\s+127\.0\.0\.1:8800;", config, flags=re.MULTILINE)
    assert re.search(r"^\s*listen\s+8800;", config, flags=re.MULTILINE) is None
    assert "proxy_pass http://127.0.0.1:8080" not in config
    assert "server_name 121.41.224.93" not in config


def test_legacy_source_and_remote_host_deploy_helpers_are_removed() -> None:
    for relative_path in (
        "auto_deploy.py",
        "deploy_light.py",
        "fix_docker.py",
        "fix_captcha.sh",
        "install_deps.sh",
        "pg_setup.sh",
        "server_setup.sh",
        "test_full.py",
    ):
        assert not (ROOT / relative_path).exists()


def test_release_deploy_requires_an_immutable_image_and_readiness() -> None:
    compose = _read("docker-compose.yml")
    example = _read(".env.example")

    deploy = _read("deploy.sh")
    assert "image: ${EDUAGENT_IMAGE:-eduagent-local:dev}" in compose
    assert "EDUAGENT_IMAGE=eduagent-local:dev" in example
    assert "EDUAGENT_COSIGN_IDENTITY=https://github.com/Joel-Ellen/ZXXC/.github/workflows/release-image.yml@refs/heads/main" in example
    assert "EDUAGENT_COSIGN_OIDC_ISSUER=https://token.actions.githubusercontent.com" in example
    assert "@sha256:" in deploy
    assert "command -v cosign" in deploy
    assert "cosign verify" in deploy
    assert '--certificate-identity "$cosign_identity"' in deploy
    assert '--certificate-oidc-issuer "$cosign_issuer"' in deploy
    assert "docker pull \"$resolved_image\"" in deploy
    assert "docker compose up -d --no-build" in deploy
    assert "docker compose up -d --build" not in deploy
    assert "/api/ready" in deploy
    assert "/api/state" not in deploy
    assert "服务在 5 分钟内未就绪" in deploy


def test_release_image_is_manual_digest_scanned_and_keyless_signed() -> None:
    workflow = _read(".github/workflows/release-image.yml")
    trigger_start = workflow.index("on:\n")
    trigger_end = workflow.index("\npermissions:", trigger_start)
    triggers = workflow[trigger_start:trigger_end]

    assert "workflow_dispatch:" in triggers
    assert "push:" not in triggers
    assert "pull_request:" not in triggers
    assert "confirm_release:" in triggers
    assert "expected_sha:" in triggers
    assert '[[ "$CONFIRM_RELEASE" != "PUBLISH" ]]' in workflow
    assert '[[ "$EXPECTED_SHA" != "$GITHUB_SHA" ]]' in workflow
    assert 'refs/heads/${DEFAULT_BRANCH}' in workflow

    assert 'image_name="ghcr.io/${GITHUB_REPOSITORY,,}"' in workflow
    assert 'image_tag="sha-${GITHUB_SHA}"' in workflow
    assert ":latest" not in workflow
    assert "docker/setup-buildx-action@" in workflow
    assert "docker/build-push-action@" in workflow
    assert "push: true" in workflow
    assert "sbom: true" in workflow
    assert "provenance: mode=max" in workflow
    assert 'image_ref="${IMAGE_NAME}@${DIGEST}"' in workflow
    assert "docker buildx imagetools inspect \"$IMAGE_REF\" --format '{{ json .SBOM.SPDX }}'" in workflow
    assert "docker buildx imagetools inspect \"$IMAGE_REF\" --format '{{ json .Provenance.SLSA }}'" in workflow

    trivy = workflow.index("uses: aquasecurity/trivy-action@")
    signing = workflow.index("cosign sign --yes --bundle")
    assert trivy < signing
    assert "image-ref: ${{ steps.immutable.outputs.image_ref }}" in workflow
    assert "severity: HIGH,CRITICAL" in workflow
    assert 'exit-code: "1"' in workflow
    assert "needs: build_and_scan" in workflow
    assert "needs.build_and_scan.result == 'success'" in workflow
    assert workflow.count("id-token: write") == 1
    assert "--certificate-identity \"$CERTIFICATE_IDENTITY\"" in workflow
    assert '--certificate-oidc-issuer "https://token.actions.githubusercontent.com"' in workflow

    uses = re.findall(r"^\s*uses:\s+[^@\s]+@([^\s#]+)", workflow, flags=re.MULTILINE)
    assert uses
    assert all(re.fullmatch(r"[0-9a-f]{40}", revision) for revision in uses)
    assert workflow.count("path: release-evidence/") == 2
    assert workflow.count("if: always()") >= 4
    assert "printenv" not in workflow
    assert ".docker/config.json" not in workflow


def test_generated_release_archives_are_not_source_controlled() -> None:
    gitignore = _read(".gitignore")
    dockerignore = _read(".dockerignore")

    assert "*.tar.gz" in gitignore
    assert "*.tar.gz" in dockerignore
