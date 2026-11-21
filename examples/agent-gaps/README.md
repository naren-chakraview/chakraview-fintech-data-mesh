# Agents as governed participants: before and after

Five runnable demos, each printing the frozen "before" behaviour and the live "after" behaviour. Full write-up:
[Agents as governed participants: before and after](../../docs/case-study/fintech-governance/agent-gaps.md).

```bash
make policy-test    # OPA rules, including delegation_test.rego
make agent-test     # delegation and governed-write tests
make agent-demo     # all five demos (needs the opa binary, and the trust dependencies in requirements-trust.txt)
```

- `before/` is the frozen code at tag `agents-before` (`b6dd9ea`): the boundary, its OPA policies, its product files
  and the accounts `RdfWriter`. Nothing in the platform imports it. `_common.py` and `boundary_before_loader.py` load it
  under its own package name.
- `agent.py` is the scripted risk-review agent. It is deterministic on purpose: the governance is what is under test,
  not how the agent decides.
- The gateway in the demos is a stand-in: `platform/delegation/verify.py` mints tokens with the claim shapes the
  zero-trust-rs gateway issues. The live gateway is not yet wired into `docker-compose.yml`.
- The demos use the real clock and temporary copies of the product state. They never write to the repository.

## The compose path (the real sidecars)

```bash
make trust-keys      # dev CA, IdP keys, attestations, and the sidecars' config (tools/dev-gateway/out/)
make agent-up        # postgres, opa, dev-idp, elasticsearch, boundary, boundary-zt, agent-zt
make agent-grants    # DEV ONLY: the read and propose grants an owner's approval would create
make agent-run       # the scripted agent, once, through both sidecars; prints its proposals
```

The agent's network namespace holds the agent and `agent-zt`; the boundary's holds the boundary and `boundary-zt`. The
agent reaches the boundary only through `boundary-zt` on mTLS. The boundary's loopback listener is reachable only from
`boundary-zt`. `agent_runner.py` takes the analyst's IdP token from the dev IdP as the consent stand-in.
