from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"


def _source(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    start_index = source.index(start)
    return source[start_index : source.index(end, start_index)]


def test_manual_course_and_node_changes_drop_review_route_context() -> None:
    learn = _source("views/LearnView.vue")
    select_node = _between(learn, "async function selectNode", "async function switchCourse")
    switch_course = _between(learn, "async function switchCourse", "async function submitCurrentQuiz")
    query_helper = _between(learn, "function routeQueryWithoutReviewContext", "</script>")

    assert "routeQueryWithoutReviewContext()" in select_node
    assert "routeQueryWithoutReviewContext()" in switch_course
    assert "delete query.reviewItem" in query_helper
    assert "delete query.reviewPhase" in query_helper


def test_terminal_diagnostic_waits_for_server_receipt_and_rolls_back_on_failure() -> None:
    canvas = _source("components/ResourceCanvas.vue")
    learn = _source("views/LearnView.vue")
    composable = _source("composables/useEduAgent.js")

    terminal_submit = _between(canvas, "function submitQuizAnswers", "function forwardWheelToContent")
    assert "quizSubmitting.value = true" in terminal_submit
    assert 'eventId: learningEventId(isReview ? "review" : "lesson"' in terminal_submit
    assert "onRecorded: () => settleSubmission(true)" in terminal_submit
    assert "onFailure: (error) => settleSubmission(false, error)" in terminal_submit
    assert terminal_submit.count("quizSubmitted.value = true") >= 2
    assert "acknowledged-but-lost response" in terminal_submit
    assert terminal_submit.index("quizSubmitted.value = true") < terminal_submit.index(
        'emit("submit-quiz"'
    )

    learn_submit = _between(learn, "async function submitCurrentQuiz", "function openReview")
    assert "submission?.onRecorded?.(response)" in learn_submit
    assert "submission?.onFailure?.(error)" in learn_submit

    submit_quiz = _between(composable, "async function submitQuiz", "async function refreshNodeResources")
    assert "throw error" in submit_quiz
    assert "return lastDiagnostic.value" in submit_quiz
    assert "eventId: submission?.eventId" in submit_quiz
    assert "The learning event already has an authoritative server receipt" in submit_quiz

    event_factory = _between(composable, "function createLearningEvent", "function recordLearningEvent")
    assert "details.eventId ?? details.event_id" in event_factory
    assert "event_id: eventId || createEventId()" in event_factory


def test_tutor_draft_is_cleared_only_after_success_and_failure_is_retryable() -> None:
    chat = _source("components/ChatArea.vue")
    learn = _source("views/LearnView.vue")
    composable = _source("composables/useEduAgent.js")

    dispatch = _between(chat, "function dispatchSend", "function retrySend")
    assert "onSuccess: () => settle(true)" in dispatch
    assert "onFailure: (error) => settle(false, error)" in dispatch
    assert dispatch.index("if (!success)") < dispatch.index("clearDraft(submission.draftKey)")
    assert 'v-if="sendError"' in chat
    assert '@click="retrySend"' in chat

    send_tutor = _between(learn, "async function sendTutor", "async function replaceWithCurrentNode")
    assert "payload.onSuccess?.()" in send_tutor
    assert "payload?.onFailure?.(error)" in send_tutor

    tutor_request = _between(composable, "async function sendTutorMessage", "function getCardLabel")
    assert "let streamFailure = null" in tutor_request
    assert "throw streamFailure" in tutor_request


def test_failed_code_event_can_be_replayed_with_original_attribution() -> None:
    learn = _source("views/LearnView.vue")
    handler = _between(learn, "async function handleCodeSubmission", "function handlePageHide")

    assert "courseId: props.courseId" in handler
    assert "nodeId: props.nodeId" in handler
    assert "eventId: codeSubmissionEventId(payload)" in handler
    assert "pendingCodeSubmission.value = event" in handler
    assert "async function retryCodeSubmissionEvent" in handler
    assert 'codeEventError.value = `${event.nodeId' in handler
    assert '@click="retryCodeSubmissionEvent"' in learn


def test_learning_header_is_task_focused_and_has_no_dead_drawer_contracts() -> None:
    header = _source("components/workspace/SessionHeader.vue")
    workspace = _source("components/PremiumWorkspace.vue")
    drawer = _source("components/SidebarDrawer.vue")

    for route_key in ("home", "courses", "progress", "review", "account", "settings"):
        assert f'key: "{route_key}"' not in header
    assert "<nav" not in header
    assert 'aria-controls="workspace-coach-panel"' in header
    assert "@click=\"$emit('toggle-tutor')\"" in header
    assert "navigate('learn')" in header
    assert '@navigate="(key) => $emit(\'navigate\', key)"' in workspace

    for stale_contract in (
        "activePanel",
        "radarValues",
        "switch-panel",
        "toggle-contrast",
        "toggle-motion",
        "set-font-size",
    ):
        assert stale_contract not in drawer
