# Chakra Commerce — Fintech Data Mesh

A production-grade reference implementation of a **data mesh architecture** using **Apache Iceberg**, demonstrating decentralized domain ownership, unified analytics, and enterprise governance for fintech.

## What This Demonstrates

- **Decentralized domains** with autonomous schema management (Transactions, Accounts, Risk/Compliance, Counterparties, Market Data)
- **Unified analytical engine** (Spark SQL) querying across domains without breaking boundaries
- **Data products as first-class citizens** with formal SLAs, ownership, and governance
- **Federated governance** — domain-owned policies, self-service access, approval workflows
- **Real-time + analytical duality** — Kafka for hot-path, Iceberg for cold-path analytics
- **Enterprise observability** — freshness, quality, lineage, compliance, cost tracking

## Quick Start

```bash
# Start local environment
docker-compose up -d

# Run a test
pytest tests/integration/test_transactions_ingest.py -v

# Query example
spark-sql -f domains/transactions/queries/transaction-by-account.sql
```

## Structure

- `domains/` — Five fintech domains (each with ingest, schemas, data products, queries)
- `platform/` — Shared infrastructure (catalog, governance, observability, discovery)
- `shared/` — Utilities (schemas, logging, compliance helpers)
- `docs/` — Architecture, production guide, domain documentation
- `tests/` — Integration, compliance, performance tests

## Documentation

- [Architecture Overview](docs/architecture/00-overview.md)
- [Production Guide](docs/production-guide/)
- [Domain Specifications](docs/domains/)

## Status

- ✅ Spec: Complete (2026-04-30)
- 🏗️ Implementation: In Progress
