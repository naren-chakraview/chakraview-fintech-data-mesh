"""G6: nothing recorded what produced a data product. Now a signed statement names the producer and the bytes.

Before: platform/lineage/ was one line. A read says nothing about where its data came from.
After:  the producer signs an in-toto statement (DSSE, Ed25519) over the snapshot's SHA-256. The boundary
        reports lineage_verified with every read. A tampered snapshot does not verify.
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

PRODUCT = "risk-compliance.risk-scores"
PURPOSE = "fraud-review"


def before() -> None:
    try:
        text = subprocess.run(["git", "show", "f949583:platform/lineage/__init__.py"], cwd=REPO,
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        text = "(git history unavailable)"
    print(f"platform/lineage/__init__.py at f949583: {text!r}")
    print("a read at f949583 returns rows and no provenance field.")


def after() -> None:
    with tempfile.TemporaryDirectory(prefix="trust-lineage-") as tmp:
        tmp = Path(tmp)
        lineage_dir = tmp / "attestations"
        trust_dir = tmp / "trust"
        lineage_dir.mkdir()
        trust_dir.mkdir()
        private_pem, public_pem = generate_signing_key()
        (trust_dir / "risk-producer.pub").write_bytes(public_pem)
        (trust_dir / "producers.json").write_text(json.dumps({"products": {PRODUCT: {
            "producer": WORKLOADS["risk-producer"], "public_key": "risk-producer.pub"}}}))
        snapshot = (REPO / "platform/boundary/fixtures" / f"{PRODUCT}.json").read_bytes()
        publish_attestation(
            PRODUCT, snapshot, private_key_pem=private_pem, keyid="risk-producer",
            producer_spiffe_id=WORKLOADS["risk-producer"], code_commit="demo",
            input_snapshots=[], out_dir=lineage_dir,
        )
        print(f"producer {WORKLOADS['risk-producer']} signed the snapshot of {PRODUCT}")

        with open_stack(lineage_dir=lineage_dir, lineage_trust_dir=trust_dir) as stack:
            grant = dict(subject="risk.analyst@chakra.fintech", workload_spiffe_id=WORKLOADS["notebook"],
                         product_id=PRODUCT, columns=["fraud_score"], purpose=PURPOSE,
                         expires_at=stack.now + timedelta(hours=1))
            stack.grants.create(**grant)
            headers = stack.headers(stack.token("risk.analyst@chakra.fintech", roles=["risk_analyst"]))
            url = f"/products/{PRODUCT}/rows?columns=fraud_score&purpose={PURPOSE}"

            r = stack.boundary().get(url, headers=headers)
            print(f"read of the published snapshot       -> {r.status_code} lineage_verified={r.json()['lineage_verified']}")

            tampered_dir = tmp / "fixtures"
            tampered_dir.mkdir()
            (tampered_dir / f"{PRODUCT}.json").write_bytes(snapshot.replace(b"0.82", b"0.19"))
            stack.boundary_app.state.services.reader = FixtureReader(tampered_dir)
            r = stack.boundary().get(url, headers=headers)
            print(f"read after one byte of the snapshot changed -> {r.status_code} lineage_verified={r.json()['lineage_verified']}")

            # An attacker who can write the attestation directory re-signs the tampered snapshot with their own key
            # and claims the expected producer. The trust configuration still names the producer's real key.
            stack.boundary_app.state.services.reader = FixtureReader(tampered_dir)
            attacker_private, _ = generate_signing_key()
            publish_attestation(PRODUCT, tampered_dir.joinpath(f"{PRODUCT}.json").read_bytes(),
                                private_key_pem=attacker_private, keyid="risk-producer",
                                producer_spiffe_id=WORKLOADS["risk-producer"], code_commit="forged",
                                input_snapshots=[], out_dir=lineage_dir)
            r = stack.boundary().get(url, headers=headers)
            print(f"forged attestation for the tampered bytes -> {r.status_code} lineage_verified={r.json()['lineage_verified']}")


if __name__ == "__main__":
    line("G6 no lineage")
    section("BEFORE (frozen f949583)")
    before()
    section("AFTER (live code)")
    after()
