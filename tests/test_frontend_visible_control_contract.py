from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"


def _source(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text(encoding="utf-8")


def test_settings_only_exposes_preferences_with_real_workspace_effects() -> None:
    settings = _source("views/SettingsView.vue")
    account = _source("components/UserSettingsView.vue")

    assert "setTheme(" not in settings
    assert "useTheme" not in settings
    assert 'id="account-theme"' not in account
    assert 'v-model="settingsDraft.preferences.theme"' not in account

    for preference in ("highContrast", "reduceMotion", "fontSize"):
        assert f"preferences.{preference}" in settings
    assert "window.localStorage.setItem(PREFERENCES_KEY" in settings
    assert 'role="noticeIsError ? \'alert\' : \'status\'"' in settings
    assert settings.count("min-h-11") >= 4


def test_tutor_context_buttons_expose_selection_and_send_real_context() -> None:
    chat = _source("components/ChatArea.vue")

    assert ':aria-pressed="String(selectedContext === ctx.value)"' in chat
    assert "contextType: selectedContext.value" in chat
    assert 'codeSnippet: selectedContext.value === "code_debug"' in chat
    assert 'errorMessage: selectedContext.value === "code_debug"' in chat


def test_learning_resource_controls_have_verifiable_handlers() -> None:
    canvas = _source("components/ResourceCanvas.vue")
    card = _source("components/ResourceCard.vue")

    assert ':show-pin="false"' in canvas
    assert ':show-minimize="false"' in canvas
    assert "draggable=" not in canvas
    assert '@bookmark="toggleBookmark(card)"' in canvas
    assert 'learningAssets.write("bookmarks"' in canvas
    assert '@save-note="saveNoteAnnotation(card, $event)"' in canvas
    assert '@save-highlight="saveHighlightAnnotation(card, $event)"' in canvas
    assert '@remove="removeAnnotation"' in canvas
    assert 'cardType: slot.type' in canvas
    assert ':aria-label="isBookmarked ? \'取消收藏资源\' : \'收藏资源\'"' in card


def test_browse_courses_control_targets_the_course_center_route() -> None:
    switcher = _source("components/workspace/CourseSwitcher.vue")
    workspace = _source("components/PremiumWorkspace.vue")
    learn_view = _source("views/LearnView.vue")

    assert '@click="browseCourses"' in switcher
    assert 'emit("browse-courses")' in switcher
    assert '@browse-courses="handleBrowseCourses"' in workspace
    assert '@browse-courses="router.push({ name: \'courses\' })"' in learn_view


def test_review_page_only_renders_empty_state_after_server_confirmation() -> None:
    review = _source("views/ReviewView.vue")

    for state in ("not_loaded", "loading", "missing_session", "error", "ready"):
        assert f'viewState === \'{state}\'' in review
    assert 'const dashboard = ref(null)' in review
    assert 'viewState.value = "missing_session"' in review
    assert 'viewState.value = "ready"' in review
    assert "服务端已确认当前没有到期复习任务" in review
    assert '@click="loadDashboard({ announce: true })"' in review


def test_progress_audit_refresh_never_silently_ignores_missing_identity() -> None:
    progress = _source("views/ProgressView.vue")

    assert 'const auditPrerequisiteError = computed(() =>' in progress
    assert 'if (!userId.value)' in progress
    assert ':disabled="auditLoading || Boolean(auditPrerequisiteError)"' in progress
    assert 'role="alert">{{ auditPrerequisiteError }}' in progress
    assert "auditError.value = auditPrerequisiteError.value" in progress


def test_login_redirect_is_resolved_and_rejects_auth_or_fallback_routes() -> None:
    login = _source("views/LoginView.vue")

    assert "router.resolve(candidate)" in login
    for route_name in ("login", "password-forgot", "password-reset", "email-verify"):
        assert f'"{route_name}"' in login
    assert "matchedAuthRoute" in login
    assert "matchedFallbackRoute" in login
    assert "resolved.fullPath" in login
    assert "candidate.startsWith(\"//\")" in login


def test_recent_learning_only_exposes_still_enrolled_courses() -> None:
    lifecycle = _source("stores/courseLifecycle.js")
    management = _source("components/CourseManagementView.vue")

    assert ".filter((item) => enrolledByCourse.value.has(item.course_id))" in lifecycle
    assert "const availableRecentLearning = computed" in management
    assert "enrolledCourseIds.value.has(item.course_id)" in management
    assert 'v-for="(item, index) in availableRecentLearning.slice(0, 8)"' in management
