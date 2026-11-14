"""G7: "federated" was one central file. Now a domain writes its own policy, and the platform guardrails
still hold when that domain policy tries to loosen them.

Before: one platform abac.rego decides for every product. A product's domain has no file of its own, and the
        decision sees only a classification string, not which product or which owner it belongs to.
After:  the accounts domain's policy is replaced, for this demo only, by one that tries to (a) allow reads
        with no verified person and (b) show every PII column in the clear. Both fail: the guardrails
        (platform) deny the first and keep PII masked on the second.
"""

import asyncio
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _loader import before_policy_dir, line, section  # noqa: E402
from boundary.policy import decide  # noqa: E402
from shared.testing.harness import DOMAIN_POLICY_DIRS, PLATFORM_POLICY_DIR, WORKLOADS, open_stack  # noqa: E402

PRODUCT = "accounts.account-master"
LOOSENED = """package data_mesh.domain["accounts"]["account-master"]

import rego.v1

# A domain policy that tries to allow everything, unmasked, to anyone.
allow := true

requires_approval := false

column_strategy := {"account_id": "no_mask", "customer_name": "no_mask", "balance": "no_mask"}
"""


def before() -> None:
    before_rego = (before_policy_dir() / "abac.rego").read_text()
    print(f"frozen policy files for every product: {sorted(p.name for p in before_policy_dir().glob('*.rego'))}")
    print(f"the frozen rules see product classification only (no product id, no owner): "
          f"{'input.product' in before_rego}")
    print("so the accounts team has no file of its own: any product rule has to be written into the one platform file.")


def after() -> None:
    with tempfile.TemporaryDirectory(prefix="trust-loosened-") as tmp:
        domain_dir = Path(tmp) / "accounts"
        domain_dir.mkdir()
        (domain_dir / "account-master.rego").write_text(LOOSENED)
        policy_dirs = [PLATFORM_POLICY_DIR, domain_dir,
                       *[d for d in DOMAIN_POLICY_DIRS if d.parent.name != "accounts"]]

        with open_stack(policy_dirs=policy_dirs) as stack:
            decide_input = {
                "action": "read",
                "principal": {"subject": "", "roles": ["risk_analyst"]},
                "workload": {"spiffe_id": WORKLOADS["notebook"]},
                "product": {"id": PRODUCT, "domain": "accounts", "name": "account-master",
                            "classification": "pii", "approval_required": True, "owner": "accounts-domain"},
            }
            decision = asyncio.run(decide(decide_input))
            print(f"domain says allow=true; read with NO verified person -> allow={decision.allow}  (platform guardrail)")

            analyst = stack.headers(stack.token("analyst@chakra.fintech", roles=["analyst"]))
            stack.grants.create(subject="analyst@chakra.fintech", workload_spiffe_id=WORKLOADS["notebook"],
                                product_id=PRODUCT, columns=["account_id", "customer_name", "balance"],
                                purpose="balance-review",
                                expires_at=stack.now + timedelta(hours=1))
            r = stack.boundary().get(
                f"/products/{PRODUCT}/rows?columns=account_id,customer_name,balance&purpose=balance-review",
                headers=analyst)
            print(f"domain says no_mask for every PII column; verified analyst with a grant -> HTTP {r.status_code}")
            for row in r.json()["rows"][:1]:
                print(f"   account_id={row['account_id']}  (not shown in the clear: the guardrail's PII floor wins)")
            print(f"   strategies in the audit: {stack.audit_records[-1]['strategies']}")


if __name__ == "__main__":
    line("G7 federated means layered")
    section("BEFORE (frozen f949583)")
    before()
    section("AFTER (live code, with a loosening domain policy)")
    after()
