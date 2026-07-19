from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SERVER = ROOT / "frontend" / "server.py"

LEGACY_FRONTEND_MARKERS = (
    "compatInternal",
    "/api/state",
    "/api/pipeline/step",
    "/api/tutor/ask",
    "/api/tutor/ask-stream",
    "/tutor-stream",
    "/api/resources/generate-node",
    '"/state"',
    '"/pipeline/step"',
    '"/tutor/ask"',
    '"/tutor-stream"',
    '"/resources/generate-node"',
)

RETIRED_SERVER_MARKERS = (
    'Route("/api/state"',
    'Route("/api/cold-start/probe"',
    'Route("/api/cold-start/answer"',
    'Route("/api/init-path"',
    'Route("/api/pipeline/step"',
    'Route("/api/pipeline/stream"',
    'Route("/api/tutor/ask"',
    'Route("/api/tutor/ask-stream"',
    'Route("/api/resources/generate-node"',
    'Route("/api/sessions/{session_id}/tutor-stream"',
    "api_compat_",
    "COMPAT_INTERNAL_HEADERS",
    "_compat_request_allowed",
)


def test_frontend_main_flow_does_not_call_legacy_learning_api():
    offenders = []
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in {".js", ".vue"}:
            continue
        text = path.read_text(encoding="utf-8")
        found = [marker for marker in LEGACY_FRONTEND_MARKERS if marker in text]
        if found:
            offenders.append((path.relative_to(ROOT).as_posix(), found))

    assert offenders == []


def test_legacy_learning_routes_are_fully_retired():
    text = SERVER.read_text(encoding="utf-8")
    for marker in RETIRED_SERVER_MARKERS:
        assert marker not in text, f"retired compat marker resurfaced: {marker}"


def test_canonical_tutor_endpoint_is_the_only_tutor_surface():
    text = SERVER.read_text(encoding="utf-8")
    assert 'Route("/api/sessions/{session_id}/tutor", api_session_tutor' in text


def test_unknown_api_paths_return_deterministic_json_404():
    text = SERVER.read_text(encoding="utf-8")
    assert 'Route("/api/{rest:path}", api_not_found' in text
