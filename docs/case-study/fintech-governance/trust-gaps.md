# Trust gaps: before and after

Article 3 of the data mesh series makes one claim: **federated governance is a trust problem, not a policy document.**
This page is the evidence. The governance in this repo was a set of documents and an OPA policy nothing called.
The fix makes every read prove who is asking, which workload is asking, and whether a grant allows it, then masks,
audits and returns. Each gap below has a frozen "before", a live "after", a demo, and a test.

## The gaps

| Gap | Before (`trust-before`) | After (live code) | How it is caught now |
|---|---|---|---|
| **G1** Identity is a claim | `user_id` and `user_role` come from the request body. A body that says `risk_analyst` for a sensitive product is **approved** with no human involved. | A verified JWT (RS256, JWKS, `iss`, `aud`, `sub`, `exp`, `nbf`) gives the subject and roles. Bodies that carry `user_id` or `user_role` get 400. No token gets 401. | `tests/unit/test_identity.py`, `tests/unit/test_access_requests.py`, demo `demo_self_asserted_role.py` |
| **G2** Enforcement nothing calls | `mask_rows` (fail-closed masking plus audit) is only called by unit tests. No read path exists. | Reads go through `platform/boundary/`. The boundary calls `mask_rows` on every read. Masking is decided per column by OPA. | `tests/trust/test_boundary.py`, demo `demo_unused_enforcement.py` |
| **G3** Grants go nowhere | An approval is a dict entry. It is never checked at read time, never expires, and `approval_required` is ignored. | An owner's approval creates a grant in Postgres: `{id, subject, workload_spiffe_id, product_id, columns, purpose, expires_at}`. The boundary checks it on every read the policy marks as needing approval, and records the grant id in the audit. Approval is refused after `approval_sla_hours`. | `tests/trust/test_discovery.py`, `tests/unit/test_grants.py`, demo `demo_unused_enforcement.py` |
| **G4** Open doors | Fuseki exposes `update` and `gsp-rw`. Queries are anonymous and return customer emails. MinIO uses `minioadmin`. The Iceberg catalog has no auth. Everything publishes host ports. | Fuseki keeps `query` and `gsp-r` only. Storage sits on an `internal` Docker network with no published ports. MinIO and catalog credentials come from `.env` with no defaults. SPARQL is parsed and refused if it is an update. | `tests/unit/test_compose_doors.py`, `tests/unit/test_sparql_guard.py`, `tests/trust/test_sparql.py`, demo `demo_side_door.py` |
| **G5** The workload is invisible | Policy input describes a person only. | Every decision carries the verified SPIFFE ID from the client certificate (URI SAN). The gateway verifies the chain. A token alone is 401. | `tests/unit/test_identity.py` (SPIFFE parsing), `tests/trust/test_boundary.py` |
| **G6** No lineage | `platform/lineage/` says nothing about provenance. | A producer signs an in-toto Statement v1 in a DSSE envelope (Ed25519) over the snapshot's SHA-256. Every read reports `lineage_verified`. A tampered snapshot does not verify. | `tests/unit/test_lineage.py`, `tests/trust/test_boundary.py`, demo `demo_lineage.py` |
| **G7** "Federated" is one file | Every product is governed by the platform's single `abac.rego`. Domains have no place to write policy. | Platform guardrails (`guardrails.rego`) plus one policy per product in `domains/<domain>/policy/`. A decision is platform allow **and** domain allow. Masking is the stricter of the platform floor and the domain strategy. A domain cannot loosen a guardrail. | `platform/governance/opa-policies/*_test.rego`, demo `demo_layered_policy.py` |
| **G8** Port clash | OPA and the Iceberg REST catalog both publish host port 8181. | OPA is internal only. Only the mTLS gateway (`127.0.0.1:8443`) and the dev IdP (`127.0.0.1:8090`) publish ports. | `tests/unit/test_compose_doors.py` |

## How a read works now

```
client ── bearer token + mTLS client cert ──▶ gateway (nginx: verifies the chain, forwards the cert)
                                                 │
                                                 ▼
                 boundary: verify JWT → parse SPIFFE ID → OPA decision (platform AND domain)
                           → grant check if approval is required → read snapshot
                           → mask_rows (OPA masking per column, fail closed) → audit
                           → rows + lineage_verified            (any failure: no rows)
```

Every failure path returns an error and no rows: no token, no certificate, an OPA error, a grant-store error, an
unknown column, or an audit write that fails.

## The audit record

Each read writes one record with: subject, roles, workload SPIFFE ID, product, columns, decision, masking strategies,
platform and domain policy revisions (content hashes), grant id, `lineage_verified`, purpose and timestamp. A refused
read writes a `deny` record with the reason.

## Run the stack

The trust services run in Compose on an internal network. Only the mTLS gateway (`127.0.0.1:8443`) and the dev IdP
(`127.0.0.1:8090`) publish ports.

```bash
cp .env.example .env          # then set every value; Compose refuses to start with one missing
make trust-keys               # dev IdP key, dev CA, signed fixture attestations
docker compose up -d postgres opa dev-idp elasticsearch boundary discovery gateway
make trust-smoke              # no cert 400, no token 401, no grant 403, approval, masked read 200
```

Compose starts the services from `platform/Dockerfile`. It pins OPA to `1.0.0`, and the Fuseki and busybox images are
pinned in the domain files.

## Run the demos

```bash
make trust-keys     # dev IdP key, dev CA, signed fixture attestations (gitignored)
make trust-test     # unit and trust tests; needs the opa binary
make trust-demo     # all five demos, before and after; the side-door demo needs Docker
```

Each demo prints a BEFORE section (the frozen code) and an AFTER section (the live code):

| Demo | Shows |
|---|---|
| `examples/trust-gaps/demo_self_asserted_role.py` | G1: a body that claims a role is approved before; after, no token is 401 and a claimed role is 400 |
| `examples/trust-gaps/demo_unused_enforcement.py` | G2, G3: the snapshot is readable in the clear before; after, reads need a grant, are masked and audited, and expire |
| `examples/trust-gaps/demo_side_door.py` | G4: anonymous emails before; after, no write endpoint, and an authorized query returns masked results |
| `examples/trust-gaps/demo_layered_policy.py` | G7: a domain policy that tries to allow unauthenticated reads and unmasked PII is overridden |
| `examples/trust-gaps/demo_lineage.py` | G6: a published snapshot verifies; the same snapshot with one byte changed does not |

## The before state

The frozen "before" code is in `examples/trust-gaps/before/` (backend, enforcement, the single `abac.rego`, the Fuseki
config, and the compose excerpt). Nothing in the platform imports it. The same state is tagged in git:

```bash
git checkout trust-before
```

## Known residuals

These are deliberate, and each one is a production decision that this repo does not make for you.

- **Identity provider.** The dev IdP (`tools/dev-idp/`) mints RS256 tokens for named test users. Production uses the
  company IdP over OIDC. Keys and users in this repo are for development only.
- **Workload identity.** The dev CA (`tools/dev-ca/`) issues client certificates with SPIFFE URI SANs. Production uses
  SPIRE. The gateway is nginx here; production would use Envoy with the same check.
- **Lineage keys.** Signing keys are generated locally and never committed. Production uses KMS or Sigstore.
- **Product reads.** The boundary reads fixture snapshots (`platform/boundary/fixtures/`). The pyiceberg adapter for
  real Iceberg tables is not wired. The lineage check covers the bytes the boundary actually reads.
- **Fuseki authentication.** The stock Fuseki 5.1 image protects `/update` and `/data` with one shared admin password,
  and leaves SPARQL queries anonymous. This change removes the update and read-write endpoints, and keeps queries
  reachable only on the internal network. It does not add per-user auth to Fuseki. The boundary is the only path.
- **Iceberg REST catalog.** The `tabulario/iceberg-rest` image has no authentication of its own. It is internal only.
- **Grant purpose.** A grant is scoped to a purpose string that the caller sends. The platform records and checks it,
  but does not verify the purpose against a register of allowed purposes.
- **Discovery requests.** Access requests are held in memory. Grants are in Postgres.
- **Delegation.** No delegation chain yet (an agent acting for a person, RFC 8693 `act` claims). That is article 4. The
  policy input already has the person and the workload separately, so the chain can be added without redesign.
- **Grafana, Kafka and Schema Registry** still publish host ports, and Grafana's admin password is set from `.env`
  with no default. They are not data stores and are out of scope for this change.
