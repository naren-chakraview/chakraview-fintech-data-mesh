"""Undo. Before, a bad write could be removed only by hand, and the removal was recorded nowhere. After, the
owner rolls the product back to its previous snapshot; the rollback is audited and signed like any change."""

from datetime import timedelta

from _common import (AGENT, ANALYST, ANALYST_ROLES, NOTES, NOTEBOOK, OWNER, OWNER_DOMAINS, OWNER_ROLES, RISK,
                     after_stack, before_stack, ok, section, show)
from agent import RiskReviewAgent
from channels import StackChannel
from lineage.trust import load_trust
from lineage.verify import verify_envelope


def main() -> None:
    section("BEFORE (frozen): undoing a bad change")
    with before_stack() as before:
        paths = {getattr(route, "path", "") for route in before.app.routes}
    show("rollback route on boundary", "rollback" in " ".join(paths))
    show("history of the product", "none: no versions are kept")
    print("  A bad change is removed by hand from storage, and that removal is recorded nowhere.")
    assert not any("rollback" in p for p in paths)

    section("AFTER: the owner rolls back, and the rollback is signed")
    with after_stack() as stack:
        stack.grants.create(subject=ANALYST, workload_spiffe_id=AGENT, product_id=RISK,
                            columns=["customer_iri", "risk_band", "scored_at"], purpose="risk-review",
                            expires_at=stack.now + timedelta(hours=1))
        stack.grants.create(subject=ANALYST, workload_spiffe_id=AGENT, product_id=NOTES, columns=[],
                            purpose="propose", expires_at=stack.now + timedelta(hours=2))
        client = stack.boundary()
        run = RiskReviewAgent(StackChannel(stack, ANALYST, ANALYST_ROLES, [AGENT]), now=lambda: stack.now).run()
        owner = stack.headers(stack.token(OWNER, OWNER_ROLES, owns=OWNER_DOMAINS), workload=NOTEBOOK)
        accepted = client.post(f"/products/{NOTES}/proposals/{run.proposals[0]['id']}/accept", headers=owner)
        assert accepted.status_code == 200
        show("accepted note", run.proposals[0]["id"])
        show("versions before undo", len(stack.writer.versions()))

        agent_try = client.post(f"/products/{NOTES}/rollback", json={"reason": "undo"},
                                headers=stack.delegated_headers(OWNER, OWNER_ROLES, [AGENT]))
        show("agent tries to roll back", agent_try.status_code)
        assert agent_try.status_code == 403

        rolled = client.post(f"/products/{NOTES}/rollback",
                             json={"reason": "wrong customer on the accepted note"}, headers=owner)
        show("owner rolls back", rolled.status_code)
        assert rolled.status_code == 200
        show("versions after undo", len(rolled.json()["versions"]))
        show("product rows now", len(stack.writer._versions[-1]["rows"]))
        assert stack.writer._versions[-1]["rows"] == []

        envelope = __import__("json").loads((stack.paths["lineage"] / f"{NOTES}.dsse.json").read_text())
        predicate = verify_envelope(envelope, load_trust(stack.paths["trust"])[NOTES].public_key)["predicate"]
        show("signed action", predicate["action"])
        show("rolled back from", predicate["rolled_back_from"][:16] + "...")
        show("reason", predicate["reason"])
        rollback_audit = [r for r in stack.audit_records if r.get("action") == "rollback"]
        show("audited", bool(rollback_audit) and rollback_audit[-1]["decided_by"] == OWNER)
        assert predicate["action"] == "rollback" and rollback_audit
        ok("the owner undid the accepted change; the agent could not")
        ok("the rollback is signed and audited, like the change it reverses")


if __name__ == "__main__":
    main()
