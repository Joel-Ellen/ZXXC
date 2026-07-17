from src.release_controls import operational_switch, rollout_decision
from src.observability import incr_metric, launch_metrics_snapshot, reset_metrics


def setup_function() -> None:
    reset_metrics()


def teardown_function() -> None:
    reset_metrics()


def test_rollout_assignment_is_stable_and_respects_boundaries() -> None:
    disabled = rollout_decision(
        "code_practice",
        "learner-1",
        environment={"EDUAGENT_CODE_PRACTICE_ROLLOUT_PERCENT": "0"},
    )
    enabled = rollout_decision(
        "code_practice",
        "learner-1",
        environment={"EDUAGENT_CODE_PRACTICE_ROLLOUT_PERCENT": "100"},
    )
    repeated = rollout_decision("code_practice", "learner-1", environment={})

    assert disabled.enabled is False
    assert disabled.cohort == "holdback"
    assert enabled.enabled is True
    assert enabled.cohort == "rollout"
    assert repeated.bucket == enabled.bucket


def test_rollout_lists_override_percentage_without_exposing_identity() -> None:
    environment = {
        "EDUAGENT_CODE_PRACTICE_ROLLOUT_PERCENT": "0",
        "EDUAGENT_CODE_PRACTICE_ROLLOUT_ALLOWLIST": "early-user",
        "EDUAGENT_CODE_PRACTICE_ROLLOUT_DENYLIST": "blocked-user",
    }

    assert rollout_decision("code_practice", "early-user", environment=environment).cohort == "allowlist"
    assert rollout_decision("code_practice", "blocked-user", environment=environment).cohort == "denylist"
    assert rollout_decision("code_practice", "", environment=environment).enabled is False


def test_operational_switch_parses_known_values_and_fails_to_default() -> None:
    assert operational_switch("compat_api", environment={"EDUAGENT_ENABLE_COMPAT_API": "yes"}) is True
    assert operational_switch("compat_api", default=True, environment={"EDUAGENT_ENABLE_COMPAT_API": "off"}) is False
    assert operational_switch("compat_api", environment={"EDUAGENT_ENABLE_COMPAT_API": "unexpected"}) is False
    assert operational_switch("compat_api", default=True, environment={}) is True


def test_launch_metrics_expose_rates_without_identity_labels() -> None:
    incr_metric("auth.login_total", outcome="success", reason="authenticated")
    incr_metric("auth.login_total", outcome="failure", reason="invalid_credentials")
    incr_metric("resource.generate_total", outcome="success", card_type="all")
    incr_metric("code.execution_total", outcome="accepted", mode="run", verdict="accepted")
    incr_metric("code.execution_total", outcome="test_failed", mode="run", verdict="wrong_answer")
    incr_metric("frontend.exception_total", surface="learn", kind="vue")
    incr_metric("frontend.session_total", surface="app")
    incr_metric("frontend.next_task_ready_total", outcome="within_5s", surface="app")
    incr_metric("learning.node_completion_attempt_total", event_type="lesson_completed", outcome="accepted")
    incr_metric("learning.node_completion_total", event_type="lesson_completed", advanced="false")
    incr_metric("frontend.refresh_recovery_total", outcome="success", surface="learn")
    incr_metric("learning_event.mastery_mutation_total", outcome="attributed")

    launch = launch_metrics_snapshot()

    assert launch["login_failure"] == {
        "failed": 1,
        "infrastructure_failed": 0,
        "total": 2,
        "rate": 0.5,
        "infrastructure_rate": 0.0,
    }
    assert launch["resource_failure"] == {"failed": 0, "total": 1, "rate": 0.0}
    assert launch["code_execution_failure"]["rate"] == 0.5
    assert launch["frontend_exceptions"] == {"total": 1, "sessions": 1, "rate": 1.0}
    assert launch["next_task_ready"]["rate"] == 1.0
    assert launch["node_completions"]["rate"] == 1.0
    assert launch["node_completions"]["advanced_rate"] == 0.0
    assert launch["refresh_recovery"]["rate"] == 1.0
    assert launch["mastery_attribution_integrity"] == {
        "attributed": 1,
        "unattributed": 0,
        "total": 1,
        "rate": 1.0,
    }
