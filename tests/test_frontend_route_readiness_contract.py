from pathlib import Path


SOURCE_PATH = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "src"
    / "composables"
    / "useEduAgent.js"
)
LEARN_VIEW_PATH = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "src"
    / "views"
    / "LearnView.vue"
)


def _source_between(start: str, end: str) -> str:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    start_index = source.index(start)
    end_index = source.index(end, start_index)
    return source[start_index:end_index]


def test_non_learning_bootstrap_never_starts_resource_generation() -> None:
    bootstrap = _source_between(
        "async function bootstrap()",
        "async function handleEnrollCourse",
    )
    path_initialization = _source_between(
        "async function initPathAndEnter()",
        "async function loadAvailableCourses",
    )

    for critical_path in (bootstrap, path_initialization):
        assert "hydrateNode(" not in critical_path
        assert "scheduleRouteEnhancements(" not in critical_path
        assert "fetchCurrentNodeResources(" not in critical_path
        assert "fetchRouteNodeResources(" not in critical_path


def test_learning_route_is_ready_before_background_resource_request() -> None:
    entrypoint = _source_between(
        "function prepareLearningRoute",
        "async function runLearningRoutePreparation",
    )
    preparation = _source_between(
        "async function runLearningRoutePreparation",
        "async function recordNodeBrowse",
    )
    scheduler = _source_between(
        "function scheduleRouteEnhancements",
        "function prepareLearningRoute",
    )

    current_node = preparation.index("currentNode.value = resolvedNodeId;")
    ready_mode = preparation.index('bootMode.value = "ready";')
    schedule = preparation.index("scheduleRouteEnhancements(")
    ready_result = preparation.index('return { status: "ready"')

    assert current_node < ready_mode < schedule < ready_result
    assert "const generation = ++routePreparationGeneration;" in entrypoint
    assert "routePreparationQueue.then(() => runLearningRoutePreparation(" in entrypoint
    assert "routePreparationQueue = request.catch(() => undefined);" in entrypoint
    assert preparation.count("if (!isCurrentPreparation()) return staleResult();") >= 8
    assert "await hydrateNode(" not in preparation
    assert "await restoreLatestDiagnostic(" not in preparation
    assert "setTimeout(" in scheduler
    assert "void runRouteEnhancements(" in scheduler
    assert "fetchRouteNodeResources(" not in scheduler


def test_background_results_require_generation_course_session_and_node_match() -> None:
    guard = _source_between(
        "function isCurrentRouteEnhancement",
        "function fetchRouteNodeResources",
    )
    enhancement = _source_between(
        "async function runRouteEnhancements",
        "async function hydrateNode",
    )
    diagnostic = _source_between(
        "async function restoreLatestDiagnostic",
        "function createLearningEvent",
    )

    assert "context.generation === routeEnhancementGeneration" in guard
    assert "context.courseId === courseId.value" in guard
    assert "context.sessionId === sessionId.value" in guard
    assert "context.nodeId === currentNode.value" in guard
    assert enhancement.count("isCurrentRouteEnhancement(context)") >= 5
    assert enhancement.index("isCurrentRouteEnhancement(context)") < enhancement.index(
        "mergeNodeResources(context.nodeId"
    )
    assert "diagnostic && shouldApply()" in diagnostic


def test_explicit_node_hydration_remains_awaitable() -> None:
    hydration = _source_between(
        "async function hydrateNode",
        "function scheduleRouteEnhancements",
    )

    assert "const context = createRouteEnhancementContext(nodeId);" in hydration
    assert "return runRouteEnhancements(context, { silent });" in hydration


def test_setup_redirect_does_not_skip_first_node_resource_scheduling() -> None:
    source = LEARN_VIEW_PATH.read_text(encoding="utf-8")
    watcher_start = source.index("() => [currentNode.value, bootMode.value]")
    watcher_end = source.index("function reportEventFailure", watcher_start)
    setup_redirect_watcher = source[watcher_start:watcher_end]

    assert 'props.nodeId !== "setup"' in setup_redirect_watcher
    assert 'name: "learn"' in setup_redirect_watcher
    assert "hydratedRouteKey =" not in setup_redirect_watcher
