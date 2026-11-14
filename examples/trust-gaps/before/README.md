# Before: the trust gaps, frozen

These are frozen copies of the governance code at commit `f949583` (tag `trust-before`). Nothing in the
live platform imports them. The demos in `examples/trust-gaps/` load them to show the "before" behaviour.

| Gap | What is wrong | File that shows it |
|---|---|---|
| G1 | Identity is a claim. `user_id` and `user_role` come from the request body and nothing authenticates the caller. | `backend/main.py`, `backend/models.py`, `backend/opa_client.py` |
| G2 | `mask_rows` has no read path. Only the unit tests call it. | `governance/enforce.py` |
| G3 | An approval is a dict entry. It is never checked at read time, never expires, and `approval_required` is ignored. | `backend/main.py` |
| G4 | Open doors. MinIO uses `minioadmin`, the Iceberg catalog has no auth, and Fuseki exposes `update` and `gsp-rw` with no auth. | `docker-compose.excerpt.yml`, `config/fuseki-config.ttl` |
| G5 | The workload is invisible. Policy input describes a person only. | `opa-policies/abac.rego`, `backend/opa_client.py`, `governance/enforce.py` |
| G6 | No lineage. `platform/lineage/` was one line. | (absent in before; see `platform/lineage/`) |
| G7 | "Federated" is one central file. Every product uses the platform's single `abac.rego`. | `opa-policies/abac.rego` |
| G8 | Port clash. OPA and the Iceberg REST catalog both publish host port 8181. | `docker-compose.excerpt.yml` |
