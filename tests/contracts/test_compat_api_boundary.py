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


def test_frontend_main_flow_does_not_call_compat_learning_api():
    offenders = []
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in {".js", ".vue"}:
            continue
        text = path.read_text(encoding="utf-8")
        found = [marker for marker in LEGACY_FRONTEND_MARKERS if marker in text]
        if found:
            offenders.append((path.relative_to(ROOT).as_posix(), found))

    assert offenders == []


def test_legacy_learning_routes_are_explicit_compat_bridges():
    text = SERVER.read_text(encoding="utf-8")
    assert "COMPAT_INTERNAL_HEADERS" in text
    assert 'Route("/api/state", api_compat_get_state' in text
    assert 'Route("/api/pipeline/step", api_compat_run_pipeline_step' in text
    assert 'Route("/api/pipeline/stream", api_compat_stream_pipeline' in text
    assert 'Route("/api/tutor/ask", api_compat_ask_tutor' in text
    assert 'Route("/api/tutor/ask-stream", api_compat_ask_tutor_stream' in text
    assert 'Route("/api/resources/generate-node", api_compat_generate_node_resources' in text


def test_session_tutor_stream_alias_is_short_term_deprecated():
    text = SERVER.read_text(encoding="utf-8")
    assert "SESSION_TUTOR_ALIAS_HEADERS" in text
    assert 'Route("/api/sessions/{session_id}/tutor", api_session_tutor' in text
    assert 'Route("/api/sessions/{session_id}/tutor-stream", api_session_tutor_stream' in text
    assert '"X-EduAgent-Canonical-Api": "/api/sessions/{session_id}/tutor"' in text
