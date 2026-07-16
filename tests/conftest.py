"""Suite-wide guards against cross-test pollution.

Resource generation runs on module-level ThreadPoolExecutors with
threading.Timer retries, and a completing concept job auto-enqueues its
supporting bundle. Work submitted during one test can therefore still be
running when the next test begins — calling that test's monkeypatched
functions and competing for its executor workers. Draining at each test
boundary keeps every test's background state to itself.
"""

from __future__ import annotations

import pytest

from src.application import resource_service


@pytest.fixture(autouse=True)
def _resource_generation_worker_isolation():
    # A previous test's teardown already drained; this guards against
    # anything scheduled outside the fixture window (e.g. module setup).
    resource_service.drain_generation_workers(timeout_seconds=15.0)
    yield
    drained = resource_service.drain_generation_workers(timeout_seconds=15.0)
    assert drained, "resource generation background work leaked past the test deadline"
