# Architecture Decision Records (ADRs)

This directory contains decisions about the data mesh architecture, technology choices, and governance model.

---

## Format

Each ADR follows the standard format:
- **Title**: What decision was made
- **Status**: Proposed | Accepted | Deprecated | Superseded
- **Context**: Why this decision was needed
- **Decision**: What was chosen and why
- **Consequences**: Trade-offs and impacts
- **Alternatives Considered**: Other options that were evaluated

---

## Index

1. **[ADR-0001: Data Mesh Pattern](ADR-0001-data-mesh.md)** - Decentralized ownership with federated governance
2. **[ADR-0002: Iceberg as Lakehouse](ADR-0002-iceberg.md)** - ACID, schema evolution, time-travel
3. **[ADR-0003: OPA for Governance](ADR-0003-governance.md)** - Policy-as-code instead of role-based
4. **[ADR-0004: Kafka + Iceberg Hybrid](ADR-0004-real-time.md)** - Real-time and cost-optimized paths

---

## Decision Timeline

- **2026-04-01**: ADR-0001 accepted (data mesh pattern)
- **2026-04-05**: ADR-0002 accepted (Iceberg choice)
- **2026-04-08**: ADR-0003 accepted (OPA governance)
- **2026-04-12**: ADR-0004 accepted (hybrid real-time/batch)

---

## Related Documentation

- Architecture Overview: [docs/architecture/00-overview.md](../architecture/00-overview.md)
- Data Mesh Principles: [docs/architecture/data-mesh-principles.md](../architecture/data-mesh-principles.md)
- Governance Deep-Dive: [docs/platform/governance.md](../platform/governance.md)
- Real-Time vs Analytics: [docs/architecture/real-time-vs-analytics.md](../architecture/real-time-vs-analytics.md)
