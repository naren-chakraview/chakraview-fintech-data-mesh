# Agents as governed participants: before and after

Article 4 of the data mesh series makes one claim: **an autonomous agent is a participant the platform has to govern,
not a notebook with a different name.** This page is the evidence. Before this change, an agent acting for an analyst
was indistinguishable from the analyst, and the platform had no write path that an agent's output could safely take.
The fix makes delegation verifiable, caps what an agent can do below what its person can do, and turns every agent
write into a proposal that a domain owner must accept. Each gap below has a frozen "before", a live "after", a demo
and a test.

## The gaps

| Gap | Before (`agents-before`, frozen) | After (live code) | How it is caught now |
|---|---|---|---|
| **D1** An agent has no identity of its own | The agent can only present the analyst's token and its own certificate. The boundary has no notion of delegation, so a forged claim of who the agent acts for is ignored, not refused. | A delegated call reaches the boundary only on its **loopback listener**, which only the boundary's own sidecar can reach, carrying a token the agent's sidecar issued and the boundary's sidecar verified (`X-ZT-Verified-Token`). The boundary checks the token's signature, issuer, audience, expiry and single use, and checks that the forwarded headers agree with the token. The mTLS listener never reads these headers. A claimed actor with no gateway signature is 401. | `tests/trust/test_delegation.py`, demo `demo_actor_must_be_proven.py` |
| **D2** An agent gets the person's whole view | Policy input describes one principal and one workload. An agent using the analyst's token reads everything the analyst can read. | Effective access is the **intersection**: the person's grant (the grant names the agent's workload, so a notebook grant does not reach the agent), the agent's capability (the domain names the agent and the columns it may ask for), and the product's policy. Refusals name the column; nothing is silently dropped. A delegated read of personal data is never shown in the clear. Chains are capped at two workloads. | `platform/governance/opa-policies/delegation_test.rego`, `tests/trust/test_delegation.py`, demo `demo_agent_capability.py` |
| **D3** No governed write path | The only write code (`RdfWriter.write_to_jena`) posts to Fuseki's `/update`, which the trust fix removed. Nothing calls it. | An agent **proposes**: `POST /products/{id}/proposals`. A proposal must be authorized with a propose grant (separate from read), parse, conform to the SHACL shapes (the shared core's, and the product's own), and fit the rate limits per agent and per person. Nothing reaches the authoritative product until an owner accepts. Only an owner's token can accept, reject or roll back, and a delegated call can never do any of these. | `tests/trust/test_proposals.py`, demo `demo_agent_proposes.py` |
| **D4** Lineage cannot name a delegator | A signed statement records the producing workload only. | The proposal's statement is signed by the boundary's governed-writer key and names the person (`on_behalf_of`), the chain (`actor_chain`) and the inputs (`derived_from`). An accepted snapshot's statement chains to the proposal's statement and names the acceptor (`accepted_by`). The product's trust entry is the boundary, the producer of record. | `tests/trust/test_proposals.py`, demo `demo_agent_proposes.py` |
| **D5** The audit has no chain | Person and workload, no chain, no link from a write to the reads behind it. | Every record carries the chain, the proposal id, the cited snapshots and the acceptor. A read records the digest of the snapshot it returned. `platform/boundary/audit_trace.py` answers "which agent, for whom, read what, proposed what, and who accepted it" from the records alone. | `tests/trust/test_proposals.py` (trace test), demo `demo_agent_is_the_person.py` |

## How an agent's write works now

```
agent ── IdP token (consent) ──▶ agent-zt (its sidecar, same network namespace)
                              │  edge mint: the analyst's IdP token becomes a token whose user is the analyst
                              │  RFC 8693 exchange for the boundary, bound (cnf) to the agent's certificate
                              ▼
agent ── mTLS + token ──▶ boundary-zt (the boundary's sidecar, same network namespace)
                              │  signature, issuer, audience, expiry, jti, binding, capability policy (user AND agent)
                              ▼
                         boundary loopback listener: verify the forwarded token, check the headers agree,
                         single use → OPA (person ∩ agent ∩ product) → grant for the agent → read → audit
   │
   └─ propose (cites the digest it read) ──▶ boundary: propose grant? parse? SHACL? rate limit?
                                            cited digest read by this pair? → proposal recorded, statement signed
                                                         │
owner ── accept ─────────────────────────────────────────┘  (the owner's own token; never a delegate)
                         → new snapshot of the product + signed statement (proposal, acceptance, inputs)
owner ── roll back ──────▶ previous snapshot restored, rollback signed and audited
```

Every refusal is fail closed: no rows, no proposal, and no change to the product. A proposal whose audit record cannot be
written is not recorded (the boundary writes the audit, then commits).

## What the boundary trusts

- **Identity for a delegated call** comes only from a token the agent's sidecar signed, which the boundary's sidecar
  verified and forwarded on the boundary's loopback listener. The boundary checks the token itself, and the forwarded
  headers must agree with it. On the mTLS listener the `X-ZT-*` headers are never read, so a client cannot make itself
  a delegated caller by sending them.
- **Roles** come from the analyst's IdP credential, carried in the signed token (`roles`, from zero-trust-rs v0.4.2).
  Policy grants by role, so a token without roles gets no access.
- **Only the sidecars reach the boundary's loopback.** Each sidecar shares its workload's network namespace, so the
  loopback is that workload's own. The agent's network cannot reach the boundary's loopback port.
- **The agent's permissions** come from the domain's policy: `allow_agents` names the agent by SPIFFE ID, and
  `agent_columns` lists what it may read as rows. `agent_aggregate_columns` lists what it may count by. An aggregate
  is a count per group, so an agent can be allowed counts it may not read as rows. Both default to nothing.
- **Aggregates suppress small groups.** A count is published only for groups of at least `aggregate_min_group` rows (3
  on the fixture, which is small; production sets a larger number). Suppressed groups are reported as a number, never
  by value. Grouping is allowed only by a public column, because a group key reveals its value.
- **The product's contract** (`require_provenance`, classification, approval) comes from the platform.

## The binding, live

The sidecar binds each delegated token to the certificate of the workload it was issued to. `make agent-check` runs
against the compose stack: it presents the agent's token with the notebook's dev-CA certificate, and the boundary's
sidecar refuses it with `certificate_binding_mismatch`. The agent's own certificate is served. The demos cannot show
this, because the boundary never sees the peer certificate, only the sidecar does.

## Write tiers

Who decided the data decides whether a human gate applies (addendum W1 to W4). A product declares whether what it holds
is **captured** (facts a person or system of record supplied) or **derived** (what a writer computed or judged). The
gate for a write follows the kind of write, the classification of what is written, and who wrote it:

| Write | Service (deterministic) | Agent (delegated) |
|---|---|---|
| captured, any classification incl. `pii` | direct | direct, only when the delegating person is the data subject (their minted `customer_iri`), or holds an intake grant |
| derived, `public` / `internal` | direct | direct |
| derived, `confidential` / `sensitive` | direct, only if the workload is a listed producer | **proposal**: an owner accepts (`409 requires_owner_review` for a direct attempt) |
| derived, `pii` | direct, only if a listed producer | **a proposal the person it describes accepts**, if the value describes exactly one person (`409 requires_subject_consent`); **refused** if it describes several people or none (`422 agent_cannot_create_pii`) |

Every direct write passes the same automated gates as a proposal, fail closed and in the same order: verified identity
(and delegation for agents), a write grant separate from read and propose, person ∩ agent ∩ product policy, the contract's
columns and key, the shapes (SHACL), rate and size limits, and for an agent's derived write, the snapshots it read.
A domain can make the outcome stricter, never looser. An unclassified column counts as personal when it is written.

**The reasoning.** A customer entering an SSN produces the most sensitive data the bank holds, and no human should sit in
that path: the customer decided the values, and the software only carries them. What deserves a human is what the writer
decided. A microservice's derived output was reviewed once, at code review, because its logic is fixed when deployed.
An agent decides per request, so for confidential output the review moves to the write.

**Captured personal data.** `accounts.customer-intake` takes an onboarding agent's write for the customer's own record,
with no human gate. The record's `customer_iri` must be the one minted from the customer's identity (their email and
the `kyc_id` the IdP credential carries, verified through zero-trust-rs's `user_attributes`). A customer writes only their
own record. On read, `ssn` and `address` are masked for everyone except a KYC grant, which sees the last digits. Field-level
encryption is not built here: personal data relies on mTLS in motion, storage encryption at rest in deployment, and masking
on read. Field-level encryption is a deployment choice outside this repo.

**Derived data, three outcomes.** `risk-compliance.score-freshness-summary` (internal) is written directly by the risk
agent. The review note (confidential) is a proposal an owner accepts. A personal column in the summary is refused for the
agent. The risk-scores service writes its sensitive output directly, as a listed producer.

**Subject consent (addendum 2).** A personal value an agent derives is not refused when one person could bless it. The
canonical form of a customer's address is an example: the onboarding agent proposes it, the proposal carries the value
being replaced and the value proposed, and the customer accepts or declines. Only she can. An agent acting for her cannot
accept what it proposed, another customer cannot, and the domain owner cannot (each is a 403). The boundary takes her
identifier from her own IdP-attested identity (the `kyc_id` claim) and requires it to mint the record's `customer_iri`. On
acceptance the snapshot is signed with `consent: subject` and her identity as `accepted_by`; a decline or the two-day
expiry leaves the original in place, audited. The owner can still roll the record back. A domain can switch the mechanism
off, and then the value is refused as before. The standardizer that produces the canonical address is a fixed mapping in
the demo, not an external service.

**A residual the gate cannot close.** Column classification cannot see personal data inside free text. A review note whose
text names a customer is confidential by its column, and goes to an owner for that reason, not because the gate detects the
name.

## The customer intake, live

`make onboarding-check` runs a deterministic mock onboarding agent (`examples/agent-gaps/onboarding_mock.py`) against the
compose stack, through its own sidecar and the boundary's. The mock is scripted, not an LLM, so its outcomes are the
same every run. It acts for one customer and makes three writes:

1. the customer's own record: direct, signed, `201`
2. the same record again: refused as a duplicate, `409`
3. another customer's record: refused, because a customer writes only their own record, `403`

The script exits non-zero if any step differs, and names the step. The target starts the boundary and its sidecar fresh
first, because the writes live in the boundary's memory: a second run without a restart would see the first record.
The customer's `kyc_id` reaches the boundary in the token the sidecar issued (zero-trust-rs v0.4.4, `user_attributes`).

**Operational note.** OPA loads its policies when it starts and does not watch the mounted directories. After a change to a
Rego file, restart the `opa` service (`docker compose up -d --force-recreate --no-deps opa`). A stale OPA refuses writes
with `policy unavailable`, which is the fail-closed behaviour, not a bug in the write path.

## Run the demos

```bash
make policy-test    # OPA: platform, domain and delegation rules (58 cases)
make agent-test     # delegation and governed-write tests, against a real OPA
make agent-demo     # five demos, before and after
```

| Demo | Shows |
|---|---|
| `examples/agent-gaps/demo_agent_is_the_person.py` | D1, D5: before, the agent's read is the analyst's notebook; after, the audit names the person, the agent and the chain |
| `examples/agent-gaps/demo_actor_must_be_proven.py` | D1: before, claimed headers are ignored; after, a wrong peer, a self-signed `act` and a bare claimed header are each 401 |
| `examples/agent-gaps/demo_agent_capability.py` | D2: before, the agent reads `kyc_verdict`; after, the analyst can and the agent acting for them cannot, and a notebook grant does not extend to the agent |
| `examples/agent-gaps/demo_agent_proposes.py` | D3, D4: before, the only write code targets a removed endpoint; after, the scripted agent proposes, bad proposals are refused, the agent cannot accept, and the owner's acceptance is signed |
| `examples/agent-gaps/demo_undo.py` | Undo: before, a bad change is removed by hand and not recorded; after, the owner rolls back and the rollback is signed and audited |
| `examples/agent-gaps/demo_write_tiers.py` | Write tiers: one line per write (caller, kind, classification, outcome, accepted by), then the owner rolls one back |

The demos run on the real clock, use temporary copies of the product state (they never change the repository), and
assert every claim they print. The scripted agent is `examples/agent-gaps/agent.py`.

## The before state

The frozen "before" code is in `examples/agent-gaps/before/`: the boundary as it was at `agents-before`, its OPA policies
and its product files. Nothing in the platform imports it. The same state is tagged in git:

```bash
git checkout agents-before
```

The frozen boundary runs against the live shared libraries (identity, grants, masking, lineage verification), which
these changes did not alter in any way the demos depend on.

## The scripted agent, and why it is not an LLM

The agent is deterministic. It reads the shared core's version (it requires `1.0.0`), reads the risk scores through the
boundary, selects high-risk customers whose scores are older than 90 days, and proposes one review note for each.

This is deliberate. A reproducible demo must produce the same proposals every time, and the claim under test is the
governance: the boundary refuses what the agent is not allowed to do, whichever way the agent decided. A language model
in that loop would make the demos vary, and would not make the governance any stronger.

## Known residuals

These are real limits of this change. Each one is either a production decision or work not yet done.

- **The scripted agent is not an LLM.** That is the point of the demo, but it means nothing here tests how a model
  decides. The governance does not depend on that, and the tests do not claim it does.
- **The demos and tests use a stand-in sidecar.** `platform/delegation/verify.py` mints tokens with the claim shapes
  zt-gateway issues, and the harness routes them to the loopback listener. The compose stack runs the real zt-gateway
  as both sidecars, pinned to tag `v0.4.4` of zero-trust-rs (the Z5 fix and the `user_attributes` claim that the customer-intake check needs).

  The compose stack exercises the real path end to end: the agent's read, and its proposals, go through both sidecars.
- **The sidecar topology is the trust model for the loopback hop.** The boundary trusts `X-ZT-Verified-*` only because
  nothing but its own sidecar can reach that port. Zero-trust-rs's upstream TLS (Z3) is not used for it.
- **The analyst's consent is a stand-in.** The agent is given the analyst's IdP token as its input
  (`agent_runner.py` fetches it from the dev IdP). A real consent flow would give the agent a token the analyst
  granted, with its own scope and lifetime.
- **Aggregate suppression is a count of the suppressed groups.** A determined reader can learn that a group exists below
  the minimum, from the number. Production needs a policy on how many suppressed groups may be reported.
- **Grants in compose come from a dev script.** `tools/dev-gateway/grant_agent.py` creates the read and propose grants
  the owner's approval would create. It is run by hand (`make agent-grants`). It is not an approval flow.
- **`make agent-check` restarts the agent afterwards,** which runs the scripted agent once more. Its proposals are
  pending, not accepted, so the product is unchanged.
- **The onboarding mock is not a model of onboarding.** It is a fixed script with one customer. It shows that the
  identity rule and the write tiers hold through real sidecars; it does not show how an onboarding agent decides what to
  ask a customer.
- **Writes live in the boundary's memory.** A restart resets the intake records; the state directory holds the snapshots
  while the process runs. Production needs a shared store, with personal data under the deployment's encryption.
- **Edge mint and exchange trust the local network.** The sidecar's admin listener takes an IdP credential with no
  bootstrap token of its own, which is correct only because the admin is reachable only from the agent's namespace.
  The bootstrap tokens in the generated registry are a stand-in for SPIRE node attestation, and the static signing keys
  need a rotation procedure before production.
- **The boundary's own replay check is in memory.** A forwarded token is single use at the sidecar and at the boundary.
  The boundary's check is per process, so a second replica would need a shared store for it.
- **The writer's keys and state are in the boundary's container.** The governed writer's signing key is mounted as a
  secret, and its snapshots and attestations are written to the repository's attestation directory, which is gitignored.
- **zero-trust-rs's own gaps apply.** Delegation to remote backends is open work in the gateway, and delegation is not
  available under its SPIRE provider. The boundary is reached over its sidecar's loopback, so neither matters here:
  the sidecar uses token exchange and a plain, non-delegate route. Upstream TLS for remote backends (Z3) is still
  planned work in zero-trust-rs.
- **Proposal and ledger state is in process.** The governed writer's proposals, its version history and the read ledger
  live in the boundary's memory. A restart loses pending proposals and the ledger, so an agent's citations made before a
  restart cannot be checked after it. Production needs a shared store for both, with the audit store as the source.
- **Fixture snapshots.** The product data is the fixture files, and their attestations are signed with dev keys
  (`make trust-keys`). A production snapshot comes from a real producer with its own keys.
- **Dev IdP, dev CA and dev gateway keys.** As in the trust-gaps page, these are for development. Production uses the
  company IdP, SPIRE, and the gateway's own KMS-held keys.
- **A column labelled less sensitive than it is skips review.** Write tiers depend on the classification label. A column
  labelled internal that holds confidential content takes the direct path. The contract checks require a label on every
  column, but they cannot judge whether the label is right.
- **Review queues are the bottleneck.** Every agent proposal waits for an owner. That is the control, and it is also the
  cost: an owner who does not review leaves proposals to expire (after two days by default), and nothing reaches the
  product in the meantime.
- **Reviewed note text is masked.** The review notes are confidential, so the platform floor masks their text on read.
  A domain cannot show it in the clear. Owners who need to read the text need a different decision, which is theirs.
- **Agents are opted in on every product, not only personal ones.** The brief set the default for products with personal
  data. This implementation refuses agents everywhere unless the domain names them, which is stricter, and the tests
  check both cases.
- **Rate limits and size limits are per process.** They bound an agent that goes through one boundary. A fleet of boundary
  replicas would need a shared counter.
