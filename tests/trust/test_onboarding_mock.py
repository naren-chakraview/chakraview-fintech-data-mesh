"""The deterministic onboarding mock on the customer-intake path, in-process: the same script gives the same outcomes
every time, on a fresh stack, and each step is the outcome the addendum requires."""

import sys
from datetime import timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "examples" / "agent-gaps"))

from shared.testing.harness import open_proposal_stack  # noqa: E402
import onboarding_mock  # noqa: E402
from channels import StackChannel  # noqa: E402


def run_once(root):
    with open_proposal_stack(root) as stack:
        stack.grants.create(subject=onboarding_mock.CUSTOMER, workload_spiffe_id=onboarding_mock.ONBOARD,
                            product_id=onboarding_mock.INTAKE, columns=["customer_iri", "legal_name", "ssn", "address"],
                            purpose="write", expires_at=stack.now + timedelta(hours=1))
        channel = StackChannel(stack, onboarding_mock.CUSTOMER, ["customer"], [onboarding_mock.ONBOARD],
                               attributes={"kyc_id": onboarding_mock.KYC})
        return onboarding_mock.run(channel)


def test_the_script_produces_the_required_outcomes(tmp_path):
    results = run_once(tmp_path)

    onboarding_mock.check(results)
    statuses = [status for _, status, _ in results]
    assert statuses[0] in {201, 409}, "the own record is new (201) or already held (409)"
    assert statuses[1] in {201, 409}, "the same record again is new or already held"
    assert statuses[2] == 403, "another customer's record is always refused, whatever the database holds"


def test_the_script_is_deterministic(tmp_path):
    first = run_once(tmp_path / "a")
    second = run_once(tmp_path / "b")

    assert first == second


def test_a_failed_step_is_reported_by_name(tmp_path):
    results = run_once(tmp_path)
    results[0] = ("own record", 403, "refused")

    with pytest.raises(AssertionError, match="own record: got 403"):
        onboarding_mock.check(results)
