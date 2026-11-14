"""Trust tests run a real OPA process. They skip with a clear reason when the opa binary is missing."""

import shutil

import pytest

from shared.testing.harness import open_stack


@pytest.fixture(scope="module")
def stack():
    if shutil.which("opa") is None:
        pytest.skip("the opa binary is not on PATH; install OPA 1.0.0 to run the trust tests")
    with open_stack() as s:
        yield s


@pytest.fixture(autouse=True)
def fresh_state(stack):
    """Each test starts with no grants, no audit records, and the clock at the stack's start time."""
    from shared.governance.grants import MemoryGrantStore
    from datetime import datetime, timezone

    services = stack.boundary_app.state.services
    store = MemoryGrantStore()
    services.grants = store
    stack.grants = store
    stack.discovery.grants = store
    stack.audit_records.clear()
    stack.now = datetime.now(timezone.utc)
    yield
