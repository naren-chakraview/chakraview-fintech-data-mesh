"""Delegated reads: the boundary accepts an agent acting for a person only from the gateway, with a token the
gateway signed, and gives the agent no more than the person, the agent's capability and the product allow."""

from datetime import timedelta

from shared.testing.harness import AGENT_SPIFFE_ID, WORKLOADS, TrustStack

RISK = "risk-compliance.risk-scores"
ACCOUNTS = "accounts.account-master"
PURPOSE = "risk-review"
SUBJECT = "risk.analyst@chakra.fintech"
ROLES = ["risk_analyst"]


def agent_grant(stack: TrustStack, *, columns, workload=AGENT_SPIFFE_ID, purpose=PURPOSE, product=RISK):
    return stack.grants.create(
        subject=SUBJECT, workload_spiffe_id=workload, product_id=product,
        columns=list(columns), purpose=purpose, expires_at=stack.now + timedelta(hours=1),
    )


def delegated_read(stack: TrustStack, columns: str, *, purpose=PURPOSE, product=RISK, chain=(AGENT_SPIFFE_ID,)):
    headers = stack.delegated_headers(SUBJECT, ROLES, list(chain))
    return stack.boundary().get(f"/products/{product}/rows?columns={columns}&purpose={purpose}", headers=headers)


def test_agent_read_names_the_person_and_the_agent_in_the_audit(stack):
    grant = agent_grant(stack, columns=["customer_iri", "risk_band"])

    r = delegated_read(stack, "customer_iri,risk_band")

    assert r.status_code == 200, r.text
    assert r.json()["grant_id"] == grant.id
    assert len(r.json()["snapshot_sha256"]) == 64
    record = stack.audit_records[-1]
    assert record["action"] == "read" and record["decision"] == "allow"
    assert record["subject"] == SUBJECT
    assert record["workload_spiffe_id"] == AGENT_SPIFFE_ID
    assert record["on_behalf_of"] == SUBJECT
    assert record["actor_chain"] == [AGENT_SPIFFE_ID]


def test_agent_cannot_read_a_column_only_the_person_can(stack):
    agent_grant(stack, columns=["fraud_score"])

    r = delegated_read(stack, "fraud_score")

    assert r.status_code == 403
    assert "rows" not in r.json()


def test_grant_for_the_notebook_does_not_extend_to_the_agent(stack):
    agent_grant(stack, columns=["customer_iri"], workload=WORKLOADS["notebook"])

    r = delegated_read(stack, "customer_iri")

    assert r.status_code == 403
    assert r.json()["detail"] == "approval required: no valid grant"


def test_person_keeps_full_access_without_delegation(stack):
    stack.grants.create(subject=SUBJECT, workload_spiffe_id=WORKLOADS["notebook"], product_id=RISK,
                        columns=["fraud_score", "kyc_verdict"], purpose=PURPOSE,
                        expires_at=stack.now + timedelta(hours=1))
    headers = stack.headers(stack.token(SUBJECT, roles=ROLES))

    r = stack.boundary().get(f"/products/{RISK}/rows?columns=kyc_verdict&purpose={PURPOSE}", headers=headers)

    assert r.status_code == 200
    assert "delegation" not in stack.audit_records[-1] and "on_behalf_of" not in stack.audit_records[-1]


def test_agent_for_a_product_that_does_not_name_it_is_refused(stack):
    agent_grant(stack, columns=["customer_iri"], product=ACCOUNTS, purpose=PURPOSE)

    r = delegated_read(stack, "account_id", product=ACCOUNTS)

    assert r.status_code == 403


def test_forwarded_headers_on_the_mtls_listener_are_ignored(stack):
    """An agent (or any client) cannot make a call look delegated by sending the gateway's headers over mTLS. The
    mTLS listener never reads them, so the call needs an identity token, and it has none."""
    headers = stack.delegated_headers(SUBJECT, ROLES, [AGENT_SPIFFE_ID])
    headers["X-Client-Cert"] = stack._certs[WORKLOADS["risk-review-agent"]]

    r = stack.boundary_mtls().get(f"/products/{RISK}/rows?columns=customer_iri&purpose={PURPOSE}", headers=headers)

    assert r.status_code == 401


def test_self_asserted_actor_in_a_token_the_gateway_did_not_sign_is_refused(stack):
    """A claimed act is not evidence. The agent signs its own token and names the chain it likes."""
    from shared.identity.devtools import generate_rsa_keypair
    from delegation import mint_delegated_token
    from shared.testing.harness import GATEWAY_ISSUER, AUDIENCE

    agent_key, _ = generate_rsa_keypair()
    forged = mint_delegated_token(agent_key, stack.gateway_kid, issuer=GATEWAY_ISSUER, audience=AUDIENCE,
                                  user=SUBJECT, roles=ROLES, chain=[AGENT_SPIFFE_ID], now=stack.now)
    headers = {"Authorization": f"Bearer {forged}", "X-Client-Cert": stack._certs[WORKLOADS["zt-gateway"]]}

    r = stack.boundary().get(f"/products/{RISK}/rows?columns=customer_iri&purpose={PURPOSE}", headers=headers)

    assert r.status_code == 401


def test_chain_deeper_than_the_cap_is_refused(stack):
    deep = [AGENT_SPIFFE_ID, "spiffe://chakracommerce.com/ns/agents/sa/relay", "spiffe://chakracommerce.com/ns/agents/sa/tool"]
    agent_grant(stack, columns=["customer_iri"])

    r = delegated_read(stack, "customer_iri", chain=deep)

    assert r.status_code == 401


def test_expired_delegation_is_refused(stack):
    headers = stack.delegated_headers(SUBJECT, ROLES, [AGENT_SPIFFE_ID], ttl_seconds=60,
                                      issued_at=stack.now - timedelta(hours=2))
    agent_grant(stack, columns=["customer_iri"])

    r = stack.boundary().get(f"/products/{RISK}/rows?columns=customer_iri&purpose={PURPOSE}", headers=headers)

    assert r.status_code == 401


def test_delegated_token_for_another_audience_is_refused(stack):
    from delegation import mint_delegated_token
    from shared.testing.harness import GATEWAY_ISSUER

    token = mint_delegated_token(stack._gateway_key, stack.gateway_kid, issuer=GATEWAY_ISSUER,
                                 audience="some-other-service", user=SUBJECT, roles=ROLES,
                                 chain=[AGENT_SPIFFE_ID], now=stack.now)
    headers = {"Authorization": f"Bearer {token}", "X-Client-Cert": stack._certs[WORKLOADS["zt-gateway"]]}

    r = stack.boundary().get(f"/products/{RISK}/rows?columns=customer_iri&purpose={PURPOSE}", headers=headers)

    assert r.status_code == 401


def test_agent_read_records_the_masking_applied_per_column(stack):
    agent_grant(stack, columns=["customer_iri"])

    r = delegated_read(stack, "customer_iri")

    assert r.status_code == 200
    strategies = stack.audit_records[-1]["strategies"]
    assert strategies["customer_iri"] == "no_mask"



# --- the forwarded-call contract (the boundary's sidecar on the loopback listener) ---

def _loopback_get(stack, headers, columns="customer_iri"):
    return stack.boundary().get(f"/products/{RISK}/rows?columns={columns}&purpose={PURPOSE}", headers=headers)


def test_forwarded_user_header_that_disagrees_with_the_token_is_refused(stack):
    agent_grant(stack, columns=["customer_iri"])
    headers = stack.delegated_headers(SUBJECT, ROLES, [AGENT_SPIFFE_ID])
    headers["X-ZT-Verified-User"] = "ceo@chakra.fintech"

    assert _loopback_get(stack, headers).status_code == 401


def test_forwarded_caller_header_that_disagrees_with_the_token_is_refused(stack):
    agent_grant(stack, columns=["customer_iri"])
    headers = stack.delegated_headers(SUBJECT, ROLES, [AGENT_SPIFFE_ID])
    headers["X-ZT-Verified-Caller"] = "spiffe://chakracommerce.com/ns/analytics/sa/notebook"

    assert _loopback_get(stack, headers).status_code == 401


def test_forwarded_chain_header_that_disagrees_with_the_token_is_refused(stack):
    agent_grant(stack, columns=["customer_iri"])
    headers = stack.delegated_headers(SUBJECT, ROLES, [AGENT_SPIFFE_ID])
    headers["X-ZT-Verified-Chain"] = f"{AGENT_SPIFFE_ID},spiffe://chakracommerce.com/ns/agents/sa/extra"

    assert _loopback_get(stack, headers).status_code == 401


def test_a_forwarded_token_is_single_use(stack):
    """The sidecar's jti cache is the first check; the boundary keeps its own, so a replay is refused here too."""
    agent_grant(stack, columns=["customer_iri"])
    headers = stack.delegated_headers(SUBJECT, ROLES, [AGENT_SPIFFE_ID])

    assert _loopback_get(stack, headers).status_code == 200
    assert _loopback_get(stack, headers).status_code == 401


def test_a_loopback_call_with_no_forwarded_token_is_refused(stack):
    headers = stack.headers(stack.token(SUBJECT, roles=ROLES))

    from fastapi.testclient import TestClient
    from shared.testing.harness import LOOPBACK_PORT
    loopback = TestClient(stack.boundary_app, base_url=f"http://127.0.0.1:{LOOPBACK_PORT}",
                          raise_server_exceptions=False)
    assert loopback.get(f"/products/{RISK}/rows?columns=customer_iri&purpose={PURPOSE}",
                        headers=headers).status_code == 401, "only forwarded calls reach the loopback listener"


def test_a_delegated_read_without_roles_in_the_token_is_denied_by_policy(stack):
    agent_grant(stack, columns=["customer_iri"])

    r = _loopback_get(stack, stack.delegated_headers(SUBJECT, [], [AGENT_SPIFFE_ID]))

    assert r.status_code == 403, "the person's roles come from the token; none means no access"


# --- aggregates: counts per group, through the forwarded-call path ---

def _aggregate(stack, group_by, headers):
    return stack.boundary().get(f"/products/{RISK}/aggregates?group_by={group_by}&purpose={PURPOSE}", headers=headers)


def test_agent_gets_counts_per_group_with_small_groups_suppressed(stack):
    agent_grant(stack, columns=["risk_band"])

    r = _aggregate(stack, "risk_band", stack.delegated_headers(SUBJECT, ROLES, [AGENT_SPIFFE_ID]))

    assert r.status_code == 200, r.text
    body = r.json()
    # The fixture has three "high" rows; "low" and "medium" have one each, below the minimum of 3.
    assert body["groups"] == [{"value": "high", "count": 3}]
    assert body["suppressed_groups"] == 2
    assert body["min_group_size"] == 3
    assert "rows" not in body, "a count never carries a row"
    record = stack.audit_records[-1]
    assert record["action"] == "aggregate" and record["on_behalf_of"] == SUBJECT
    assert record["suppressed_groups"] == 2


def test_agent_may_not_aggregate_by_a_column_it_may_not_read_as_rows(stack):
    agent_grant(stack, columns=["fraud_score"])

    r = _aggregate(stack, "fraud_score", stack.delegated_headers(SUBJECT, ROLES, [AGENT_SPIFFE_ID]))

    assert r.status_code == 403


def test_a_non_public_column_is_never_a_group_even_for_a_person(stack):
    stack.grants.create(subject=SUBJECT, workload_spiffe_id=WORKLOADS["notebook"], product_id=RISK,
                        columns=["fraud_score"], purpose=PURPOSE, expires_at=stack.now + timedelta(hours=1))

    r = stack.boundary().get(f"/products/{RISK}/aggregates?group_by=fraud_score&purpose={PURPOSE}",
                             headers=stack.headers(stack.token(SUBJECT, roles=ROLES)))

    assert r.status_code == 403, "a group key reveals the value, so only public columns group"


def test_a_grouping_the_agent_was_never_granted_is_refused_by_the_grant(stack):
    agent_grant(stack, columns=["customer_iri"])  # a grant, but not for the band

    r = _aggregate(stack, "risk_band", stack.delegated_headers(SUBJECT, ROLES, [AGENT_SPIFFE_ID]))

    assert r.status_code == 403
