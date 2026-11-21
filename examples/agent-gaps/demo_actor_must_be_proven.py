"""D1: an actor that is only claimed is not evidence.

Before, the boundary has no delegation, so nothing is refused and nothing is attributed. After, a delegated call is
accepted only when it arrives on the boundary's sidecar listener with a token the agent's sidecar signed, and the
headers and the token agree. Each attempt below is refused, and only the sidecar's own forwarded call is served.
"""

from datetime import timedelta

from _common import AGENT, ANALYST, ANALYST_ROLES, NOTEBOOK, RISK, after_stack, before_stack, ok, section, show
from delegation import mint_delegated_token
from shared.identity.devtools import generate_rsa_keypair
from shared.testing.harness import AUDIENCE, BOUNDARY_SPIFFE_ID, GATEWAY_ISSUER, WORKLOADS

PATH = f"/products/{RISK}/rows?columns=customer_iri&purpose=risk-review"


def main() -> None:
    section("BEFORE (frozen): claimed identity headers")
    with before_stack() as before:
        before.grants.create(subject=ANALYST, workload_spiffe_id=NOTEBOOK, product_id=RISK,
                             columns=["account_ref"], purpose="risk-review",
                             expires_at=before.now + timedelta(hours=1))
        headers = before.headers(before.token(ANALYST, ANALYST_ROLES), workload=NOTEBOOK)
        headers.update({"X-ZT-Verified-User": "owner@risk-compliance.chakra.fintech",
                        "X-ZT-Verified-Chain": AGENT,
                        "X-SPIFFE-OBO-Token": "claimed-by-the-caller"})
        r = before.client().get(f"/products/{RISK}/rows?columns=account_ref&purpose=risk-review", headers=headers)
        record = before.audit_records[-1]
        show("status with forged headers", r.status_code)
        show("audit subject", record["subject"])
        print("  The forged headers are ignored, because nothing reads them. The read is served as the caller's")
        print("  own identity. Nothing says it was for anyone else, and nothing refuses the claim either.")
        assert r.status_code == 200 and record["subject"] == ANALYST

    section("AFTER: the same attempts against the governed boundary")
    with after_stack() as after:
        after.grants.create(subject=ANALYST, workload_spiffe_id=AGENT, product_id=RISK,
                            columns=["customer_iri"], purpose="risk-review",
                            expires_at=after.now + timedelta(hours=1))
        client = after.boundary()

        # (a) The forwarded call names a different caller than the token's current actor.
        forged_caller = after.delegated_headers(ANALYST, ANALYST_ROLES, [AGENT])
        forged_caller["X-ZT-Verified-Caller"] = WORKLOADS["notebook"]
        r = client.get(PATH, headers=forged_caller)
        show("(a) caller header not the actor", r.status_code)
        assert r.status_code == 401

        # (b) A forwarded token, presented a second time.
        once = after.delegated_headers(ANALYST, ANALYST_ROLES, [AGENT])
        first = client.get(PATH, headers=once)
        again = client.get(PATH, headers=once)
        show("(b) first use / replay", f"{first.status_code} / {again.status_code}")
        assert (first.status_code, again.status_code) == (200, 401)

        # (c) The gateway's headers sent over mTLS, with the analyst's own token: the headers are never read there.
        mtls = after.boundary_mtls()
        claimed = after.delegated_headers(ANALYST, ANALYST_ROLES, [AGENT])
        claimed["Authorization"] = f"Bearer {after.token(ANALYST, ANALYST_ROLES)}"
        claimed["X-Client-Cert"] = after._certs[WORKLOADS["notebook"]]
        r = mtls.get(PATH, headers=claimed)
        show("(c) forwarded headers on mTLS", r.status_code)
        assert r.status_code == 403, "the person is treated as the person: no grant on this path, so refused"

        # (d) Only the claim, with no token at all.
        r = mtls.get(PATH, headers={"X-ZT-Verified-Token": "not-a-token", "X-ZT-Verified-User": ANALYST,
                                    "X-ZT-Verified-Caller": AGENT, "X-ZT-Verified-Chain": AGENT,
                                    "X-Client-Cert": after._certs[WORKLOADS["notebook"]]})
        show("(d) claimed only, no identity", r.status_code)
        assert r.status_code == 401

        # (e) A token signed by a key the boundary does not trust, under the sidecar's issuer name.
        rogue_key, _ = generate_rsa_keypair()
        forged = mint_delegated_token(rogue_key, after.gateway_kid, issuer=GATEWAY_ISSUER, audience=BOUNDARY_SPIFFE_ID,
                                      user=ANALYST, roles=ANALYST_ROLES, chain=[AGENT], now=after.now)
        r = client.get(PATH, headers={"X-ZT-Verified-Token": forged, "X-ZT-Verified-User": ANALYST,
                                      "X-ZT-Verified-Caller": AGENT, "X-ZT-Verified-Chain": AGENT})
        show("(e) self-signed act", r.status_code)
        assert r.status_code == 401

        # (f) The sidecar's own forwarded call: served, and attributed to the person and the agent.
        r = client.get(PATH, headers=after.delegated_headers(ANALYST, ANALYST_ROLES, [AGENT]))
        show("(f) forwarded by the sidecar", r.status_code)
        assert r.status_code == 200

        ok("a claimed caller, actor or chain that disagrees with the token is refused (a)")
        ok("a forwarded token is single use (b)")
        ok("the gateway's headers mean nothing on the mTLS listener (c, d)")
        ok("a token the boundary does not trust is refused, even with a valid shape (e)")


if __name__ == "__main__":
    main()
