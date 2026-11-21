"""D3 and D4: before, the only write code targets an endpoint that no longer exists, and nothing records which
agent, for whom, read what. After, the scripted agent proposes; invalid and uncited proposals are refused; the
agent cannot accept; the owner accepts, and the signed snapshot names the agent, the person and the inputs."""

import json
from datetime import timedelta
from pathlib import Path

from _common import (AGENT, ANALYST, ANALYST_ROLES, NOTES, NOTEBOOK, OWNER, OWNER_DOMAINS, OWNER_ROLES, REPO, RISK,
                     after_stack, before_stack, ok, section, show)
from agent import RiskReviewAgent, review_note_turtle
from channels import StackChannel
from lineage.trust import load_trust
from lineage.verify import verify_envelope


def frozen_write_to_jena() -> str:
    """The frozen method's source. Read as text: the frozen module imports `requests`, which the demos do not need."""
    text = (Path(__file__).resolve().parent / "before/domains/accounts/src/main/python/semantic/rdf_writer.py").read_text()
    start = text.index("    def write_to_jena(")
    return text[start:text.index("    def write_to_file(", start)]


def main() -> None:
    section("BEFORE (frozen): how an agent's output could reach storage")
    writer_src = frozen_write_to_jena()
    show("write code (frozen)", "RdfWriter.write_to_jena, POST to .../update" if "/update" in writer_src else "?")
    fuseki = (REPO / "domains/risk-compliance/config/fuseki-config.ttl").read_text()
    show("Fuseki /update today", "not served (locked-down config)" if "No update endpoint" in fuseki else "served")
    callers = [p for p in (REPO / "domains").rglob("*.py") if "write_to_jena(" in p.read_text()
               and "def write_to_jena" not in p.read_text()]
    show("runtime callers", len(callers))
    with before_stack() as before:
        paths = {getattr(route, "path", "") for route in before.app.routes}
    show("write routes on boundary", sorted(p for p in paths if "proposal" in p or "rollback" in p) or "none")
    assert "/update" in writer_src and not callers and not any("proposal" in p for p in paths)
    print("  No agent write path existed. The only write code targets an endpoint that is gone.")

    section("AFTER: the scripted agent proposes; the owner decides")
    with after_stack() as stack:
        stack.grants.create(subject=ANALYST, workload_spiffe_id=AGENT, product_id=RISK,
                            columns=["customer_iri", "risk_band", "scored_at"], purpose="risk-review",
                            expires_at=stack.now + timedelta(hours=1))
        stack.grants.create(subject=ANALYST, workload_spiffe_id=AGENT, product_id=NOTES, columns=[],
                            purpose="propose", expires_at=stack.now + timedelta(hours=2))
        client = stack.boundary()
        channel = StackChannel(stack, ANALYST, ANALYST_ROLES, [AGENT])
        run = RiskReviewAgent(channel, now=lambda: stack.now).run()
        show("snapshot the agent read", run.snapshot_sha256[:16] + "...")
        show("high-risk, stale scores", len(run.high_risk_stale))
        for proposal in run.proposals:
            show(f"proposal {proposal['id']}", proposal["status"])
        assert len(run.proposals) == 2 and not run.refusals, run.refusals
        first = run.proposals[0]
        digest = run.snapshot_sha256

        def propose(payload: str, derived=(digest,)):
            return channel.post(f"/products/{NOTES}/proposals",
                                json={"payload": payload, "derived_from": list(derived)})

        note = review_note_turtle("RN-DEMO-EMAIL", run.high_risk_stale[0], "high", "2026-01-15", stack.now)
        deprecated = propose(note.replace("fintech:reviewedNote", 'fintech:email "a@example.test" ;\n  fintech:reviewedNote'))
        show("deprecated term", deprecated.status_code)
        unminted = propose(note.replace(run.high_risk_stale[0], "https://chakracommerce.com/customer#3abeb7cf"))
        show("unminted customer id", unminted.status_code)
        unread = propose(note.replace("RN-DEMO-EMAIL", "RN-DEMO-UNREAD"), derived=("0" * 64,))
        show("cites a snapshot never read", unread.status_code)
        self_accept = client.post(f"/products/{NOTES}/proposals/{first['id']}/accept",
                                  headers=stack.delegated_headers(OWNER, OWNER_ROLES, [AGENT]))
        show("agent accepts its own", self_accept.status_code)
        assert (deprecated.status_code, unminted.status_code, unread.status_code, self_accept.status_code) == (
            422, 422, 403, 403)

        owner = stack.headers(stack.token(OWNER, OWNER_ROLES, owns=OWNER_DOMAINS), workload=NOTEBOOK)
        accepted = client.post(f"/products/{NOTES}/proposals/{first['id']}/accept", headers=owner)
        show("owner accepts", accepted.status_code)
        assert accepted.status_code == 200

        envelope = json.loads((stack.paths["lineage"] / f"{NOTES}.dsse.json").read_text())
        predicate = verify_envelope(envelope, load_trust(stack.paths["trust"])[NOTES].public_key)["predicate"]
        print("  signed snapshot (verified with the trust configuration):")
        show("  action", predicate["action"])
        show("  on_behalf_of", predicate["on_behalf_of"])
        show("  actor_chain", predicate["actor_chain"])
        show("  derived_from", [d["sha256"][:16] + "..." for d in predicate["derived_from"]])
        show("  accepted_by", predicate["accepted_by"])
        assert predicate["on_behalf_of"] == ANALYST and predicate["actor_chain"] == [AGENT]
        assert predicate["accepted_by"] == OWNER
        ok("invalid, uncited and self-accepted proposals changed nothing")
        ok("the signed snapshot names the agent, the person, the inputs and the acceptance")


if __name__ == "__main__":
    main()
