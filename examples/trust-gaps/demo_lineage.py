"""G6: nothing recorded what produced a data product. Now a signed statement names the producer and the bytes.

Before: platform/lineage/ was one line. A read says nothing about where its data came from.
After:  each producer signs an in-toto statement (DSSE, Ed25519) over the snapshot's SHA-256. A trust configuration
        names the expected producer and its key per product, separately from the attestations. The boundary reports
        lineage_verified with every read. A product whose contract sets require_provenance is refused when its
        snapshot does not verify; risk-scores only reports it.
"""

import json
import subprocess
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _loader import line, section  # noqa: E402
from boundary.reader import FixtureReader  # noqa: E402
from lineage.attest import generate_signing_key, publish_attestation  # noqa: E402
from shared.testing.harness import REPO, WORKLOADS, open_stack  # noqa: E402

RISK = "risk-compliance.risk-scores"
ACCOUNTS = "accounts.account-master"
PURPOSE = "fraud-review"


def before() -> None:
    try:
        text = subprocess.run(["git", "show", "f949583:platform/lineage/__init__.py"], cwd=REPO,
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        text = "(git history unavailable)"
    print(f"platform/lineage/__init__.py at f949583: {text!r}")
    print("a read at f949583 returns rows and no provenance field.")


def _publish(product, producer, key_name, attestations, private_pem):
    """Sign the product's live snapshot as `producer`."""
    snapshot = (REPO / "platform/boundary/fixtures" / f"{product}.json").read_bytes()
    publish_attestation(product, snapshot, private_key_pem=private_pem, keyid=key_name,
                        producer_spiffe_id=producer, code_commit="demo", input_snapshots=[],
                        out_dir=attestations)


def after() -> None:
    with tempfile.TemporaryDirectory(prefix="trust-lineage-") as tmp:
        tmp = Path(tmp)
        attestations = tmp / "attestations"
        trust = tmp / "trust-config"
        attestations.mkdir()
        trust.mkdir()
        products = {}
        for product, key_name, producer in [
            (RISK, "risk-producer", WORKLOADS["risk-producer"]),
            (ACCOUNTS, "nightly-batch", WORKLOADS["nightly-batch"]),
        ]:
            private_pem, public_pem = generate_signing_key()
            (trust / f"{key_name}.pub").write_bytes(public_pem)
            products[product] = {"producer": producer, "public_key": f"{key_name}.pub"}
            _publish(product, producer, key_name, attestations, private_pem)
        (trust / "producers.json").write_text(json.dumps({"products": products}))
        print("each producer signed its product; the trust config names the expected producers")

        with open_stack(lineage_dir=attestations, lineage_trust_dir=trust) as stack:
            analyst = stack.headers(stack.token("risk.analyst@chakra.fintech", roles=["risk_analyst"]))
            stack.grants.create(subject="risk.analyst@chakra.fintech", workload_spiffe_id=WORKLOADS["notebook"],
                                product_id=RISK, columns=["fraud_score"], purpose=PURPOSE,
                                expires_at=stack.now + timedelta(hours=1))
            stack.grants.create(subject="risk.analyst@chakra.fintech", workload_spiffe_id=WORKLOADS["notebook"],
                                product_id=ACCOUNTS, columns=["account_id"], purpose="balance-review",
                                expires_at=stack.now + timedelta(hours=1))
            client = stack.boundary()
            risk_url = f"/products/{RISK}/rows?columns=fraud_score&purpose={PURPOSE}"
            accounts_url = "/products/accounts.account-master/rows?columns=account_id&purpose=balance-review"

            r = client.get(risk_url, headers=analyst)
            print(f"risk-scores, verified snapshot              -> {r.status_code} lineage_verified={r.json()['lineage_verified']}")
            r = client.get(accounts_url, headers=analyst)
            print(f"account-master, verified snapshot           -> {r.status_code} lineage_verified={r.json()['lineage_verified']}")

            # One byte of the snapshot changes.
            tampered = tmp / "fixtures"
            tampered.mkdir()
            (tampered / f"{RISK}.json").write_bytes(
                (REPO / "platform/boundary/fixtures" / f"{RISK}.json").read_bytes().replace(b"0.82", b"0.19"))
            (tampered / f"{ACCOUNTS}.json").write_bytes(
                (REPO / "platform/boundary/fixtures" / f"{ACCOUNTS}.json").read_bytes().replace(b"ACC-1001", b"ACC-9999"))
            stack.boundary_app.state.services.reader = FixtureReader(tampered)

            r = client.get(risk_url, headers=analyst)
            print(f"risk-scores, one byte changed               -> {r.status_code} lineage_verified={r.json()['lineage_verified']}")
            r = client.get(accounts_url, headers=analyst)
            print(f"account-master, one byte changed            -> {r.status_code} {r.json()['detail']}")

            # The attacker can write the attestation directory. They re-sign the tampered bytes with their own key
            # and claim the expected producer. The trust config still names the producer's real key.
            attacker_private, _ = generate_signing_key()
            forged_bytes = (tampered / f"{ACCOUNTS}.json").read_bytes()
            publish_attestation(ACCOUNTS, forged_bytes, private_key_pem=attacker_private, keyid="nightly-batch",
                                producer_spiffe_id=WORKLOADS["nightly-batch"], code_commit="forged",
                                input_snapshots=[], out_dir=attestations)
            r = client.get(accounts_url, headers=analyst)
            print(f"forged attestation for the tampered bytes -> {r.status_code} {r.json()['detail']}")


if __name__ == "__main__":
    line("G6 no lineage")
    section("BEFORE (frozen f949583)")
    before()
    section("AFTER (live code)")
    after()
