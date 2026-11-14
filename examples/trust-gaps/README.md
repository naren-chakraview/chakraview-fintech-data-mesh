# Trust gaps: before and after

Five runnable demos. Each prints the frozen "before" behaviour and the live "after" behaviour.
Full write-up: [Trust gaps: before and after](../../docs/case-study/fintech-governance/trust-gaps.md).

```bash
make trust-keys   # once: dev IdP key, dev CA, signed fixture attestations
make trust-demo
```

- `before/` is the frozen code at commit `f949583` (tag `trust-before`). Nothing in the platform imports it.
  The frozen files are unchanged. One exception is worth knowing: the frozen Fuseki config uses a TDB2 namespace
  that Fuseki 5.1 rejects, so it does not start. `demo_side_door.py` runs a scratch copy with only that namespace
  corrected. The live config has the same correction.
- The demos need the `opa` binary on PATH (OPA 1.0.0). `demo_side_door.py` also needs Docker.
