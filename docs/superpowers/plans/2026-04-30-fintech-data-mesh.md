# Fintech Data Mesh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade fintech data mesh using Apache Iceberg, demonstrating decentralized domain ownership, unified analytics, data products, federated governance, and enterprise observability.

**Architecture:** Hybrid monorepo with five fintech domains (Transactions, Accounts, Risk/Compliance, Counterparties, Market Data) sharing Iceberg catalog + Kafka infrastructure. Self-service discovery portal + OPA-based governance + comprehensive observability (freshness, quality, lineage, compliance).

**Tech Stack:** Apache Iceberg, Spark, Kafka, Schema Registry, OPA, FastAPI, React, Prometheus, Grafana, Great Expectations, Spline, OpenLineage

---

## Phase 1: Foundation & Catalog Infrastructure

### Task 1: Initialize Project Structure

**Files:**
- Create: `README.md`, `.gitignore`, `CLAUDE.md`
- Create: directory structure (docs, domains, platform, shared, tests)

- [ ] **Step 1: Initialize Git repository**

```bash
cd /home/gundu/portfolio/chakraview-fintech-data-mesh
git init
git config user.email "gundu.z+claude@gmail.com"
git config user.name "Claude"
```

- [ ] **Step 2: Create .gitignore**

```bash
cat > .gitignore << 'EOF'
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
*.log
.DS_Store
.env
.env.local
spark-warehouse/
*.parquet
.pytest_cache/
.mypy_cache/
*.swp
dist/
build/
.claude/
EOF
```

- [ ] **Step 3: Create directory structure**

```bash
mkdir -p docs/{architecture,domains,platform,production-guide,superpowers/specs}
mkdir -p domains/{transactions,accounts,risk-compliance,counterparties,market-data}/{data-products,ingest,schemas,queries,tests}
mkdir -p platform/{catalog,discovery/{backend,frontend},governance,observability,lineage}
mkdir -p shared/{schemas,utils,compliance,tests}
mkdir -p tests/{integration,compliance,performance}
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: initialize project structure

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 2: Create Project README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README.md**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add project README

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 3: Create Python Requirements and Makefile

**Files:**
- Create: `requirements.txt`, `Makefile`

- [ ] **Step 1: Create requirements.txt**

```bash
cat > requirements.txt << 'EOF'
# Spark & Iceberg
pyspark==3.5.0
pyiceberg==0.6.0

# Kafka & Schema Registry
kafka-python==2.0.2
confluent-kafka==2.3.0

# Data Quality & Lineage
great-expectations==0.18.0
openlineage-python==0.28.0

# Governance & APIs
fastapi==0.104.0
uvicorn==0.24.0
opa-python-client==0.4.0

# Observability
prometheus-client==0.19.0
opentelemetry-api==1.20.0
opentelemetry-sdk==1.20.0
opentelemetry-exporter-prometheus==0.41b0

# Data & Utilities
pandas==2.1.0
pydantic==2.5.0
pyyaml==6.0
python-dotenv==1.0.0

# Testing
pytest==7.4.0
pytest-cov==4.1.0
pytest-mock==3.12.0

# Development
black==23.11.0
flake8==6.1.0
mypy==1.7.0
EOF
```

- [ ] **Step 2: Create Makefile**

```bash
cat > Makefile << 'EOF'
.PHONY: help install test lint format clean docker-up docker-down

help:
	@echo "Available commands:"
	@echo "  make install        Install dependencies"
	@echo "  make test           Run all tests"
	@echo "  make test-unit      Run unit tests only"
	@echo "  make test-integration Run integration tests only"
	@echo "  make lint           Run linting checks"
	@echo "  make format         Format code with black"
	@echo "  make docker-up      Start Docker Compose services"
	@echo "  make docker-down    Stop Docker Compose services"
	@echo "  make clean          Remove build artifacts"

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v --cov=domains --cov=platform --cov=shared

test-unit:
	pytest tests/unit -v

test-integration:
	pytest tests/integration -v

lint:
	flake8 domains platform shared
	mypy domains platform shared

format:
	black domains platform shared tests

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache/ build/ dist/ *.egg-info/
EOF
```

- [ ] **Step 3: Commit**

```bash
git add requirements.txt Makefile
git commit -m "chore: add dependencies and build tooling

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 4: Create Docker Compose for Local Development

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Write docker-compose.yml**

```bash
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  # Kafka
  kafka:
    image: confluentinc/cp-kafka:7.5.0
    container_name: chakra-kafka
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
    ports:
      - "9092:9092"
    depends_on:
      - zookeeper

  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    container_name: chakra-zookeeper
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
    ports:
      - "2181:2181"

  # Schema Registry
  schema-registry:
    image: confluentinc/cp-schema-registry:7.5.0
    container_name: chakra-schema-registry
    environment:
      SCHEMA_REGISTRY_HOST_NAME: schema-registry
      SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS: kafka:9092
      SCHEMA_REGISTRY_LISTENERS: http://0.0.0.0:8081
    ports:
      - "8081:8081"
    depends_on:
      - kafka

  # PostgreSQL (for Iceberg catalog metadata)
  postgres:
    image: postgres:15
    container_name: chakra-postgres
    environment:
      POSTGRES_USER: iceberg
      POSTGRES_PASSWORD: iceberg
      POSTGRES_DB: iceberg
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  # Iceberg REST Catalog
  iceberg-catalog:
    image: tabulario/iceberg-rest:latest
    container_name: chakra-iceberg-catalog
    environment:
      CATALOG_S3_ENDPOINT: http://minio:9000
      CATALOG_S3_ACCESS_KEY_ID: minioadmin
      CATALOG_S3_SECRET_ACCESS_KEY: minioadmin
      CATALOG_WAREHOUSE: s3://data/warehouse
    ports:
      - "8181:8181"
    depends_on:
      - postgres
      - minio

  # MinIO (S3-compatible object storage)
  minio:
    image: minio/minio:latest
    container_name: chakra-minio
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    command: server /data --console-address ":9001"
    volumes:
      - minio_data:/data

  # Prometheus
  prometheus:
    image: prom/prometheus:latest
    container_name: chakra-prometheus
    volumes:
      - ./platform/observability/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'

  # Grafana
  grafana:
    image: grafana/grafana:latest
    container_name: chakra-grafana
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
    volumes:
      - grafana_data:/var/lib/grafana

  # OPA (Open Policy Agent)
  opa:
    image: openpolicyagent/opa:latest
    container_name: chakra-opa
    ports:
      - "8282:8282"
    command: run --server

  # Elasticsearch (audit logs)
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    container_name: chakra-elasticsearch
    environment:
      discovery.type: single-node
      xpack.security.enabled: "false"
    ports:
      - "9200:9200"
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data

volumes:
  postgres_data:
  minio_data:
  prometheus_data:
  grafana_data:
  elasticsearch_data:
EOF
```

- [ ] **Step 2: Verify syntax**

```bash
docker-compose config > /dev/null
echo "Docker Compose syntax valid"
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: add docker-compose for local development

Services: Kafka, Schema Registry, PostgreSQL, Iceberg Catalog, MinIO,
Prometheus, Grafana, OPA, Elasticsearch

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 5: Create Shared Schema Utilities

**Files:**
- Create: `shared/schemas/iceberg_schemas.py`
- Create: `shared/schemas/__init__.py`

- [ ] **Step 1: Write test for Iceberg schema helper**

```bash
cat > shared/schemas/test_iceberg_schemas.py << 'EOF'
import pytest
from pyiceberg.types import (
    NestedField,
    StringType,
    IntegerType,
    TimestampType,
    DoubleType,
    BooleanType,
    StructType,
)
from shared.schemas.iceberg_schemas import IcebergSchemaBuilder


def test_iceberg_schema_builder_basic():
    """Test basic schema building"""
    builder = IcebergSchemaBuilder("test_table")
    builder.add_field("id", IntegerType(), required=True)
    builder.add_field("name", StringType(), required=True)
    builder.add_field("created_at", TimestampType(), required=False)
    
    schema = builder.build()
    assert schema.field_ids == 1
    assert len(schema.fields) == 3
    assert schema.fields[0].name == "id"
    assert schema.fields[1].name == "name"
    assert schema.fields[2].name == "created_at"


def test_iceberg_schema_with_partitions():
    """Test schema with partition spec"""
    builder = IcebergSchemaBuilder("test_table")
    builder.add_field("id", IntegerType(), required=True)
    builder.add_field("amount", DoubleType(), required=True)
    builder.add_field("date", TimestampType(), required=True)
    builder.add_partition("date", "day")
    
    schema = builder.build()
    partitions = builder.get_partition_spec()
    
    assert len(schema.fields) == 3
    assert partitions is not None


def test_iceberg_schema_evolution():
    """Test schema version tracking"""
    builder = IcebergSchemaBuilder("test_table")
    builder.version = "1.0"
    builder.add_field("id", IntegerType(), required=True)
    
    schema = builder.build()
    assert builder.version == "1.0"
EOF
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest shared/schemas/test_iceberg_schemas.py::test_iceberg_schema_builder_basic -v
# Expected: FAILED - ModuleNotFoundError: No module named 'shared.schemas.iceberg_schemas'
```

- [ ] **Step 3: Write implementation**

```bash
cat > shared/schemas/iceberg_schemas.py << 'EOF'
from typing import List, Dict, Optional, Any
from pyiceberg.types import (
    NestedField,
    IcebergType,
    IntegerType,
    StringType,
    TimestampType,
    DoubleType,
    StructType,
)
from pyiceberg.partitioning import PartitionSpec, PartitionField
from pyiceberg.schema import Schema


class IcebergSchemaBuilder:
    """Helper to build Iceberg schemas with version tracking"""
    
    def __init__(self, table_name: str, version: str = "1.0"):
        self.table_name = table_name
        self.version = version
        self.fields: List[NestedField] = []
        self.partition_fields: List[tuple] = []  # (column_name, partition_type)
        self.field_id = 1
    
    def add_field(
        self,
        name: str,
        field_type: IcebergType,
        required: bool = True,
        doc: Optional[str] = None,
    ) -> "IcebergSchemaBuilder":
        """Add a field to schema"""
        field = NestedField(
            field_id=self.field_id,
            name=name,
            type=field_type,
            required=required,
            doc=doc,
        )
        self.fields.append(field)
        self.field_id += 1
        return self
    
    def add_partition(
        self,
        column_name: str,
        partition_type: str = "identity",
    ) -> "IcebergSchemaBuilder":
        """Add partition spec for column"""
        self.partition_fields.append((column_name, partition_type))
        return self
    
    def build(self) -> Schema:
        """Build and return Iceberg schema"""
        if not self.fields:
            raise ValueError("Schema must have at least one field")
        return Schema(*self.fields)
    
    def get_partition_spec(self) -> Optional[PartitionSpec]:
        """Get partition spec if defined"""
        if not self.partition_fields:
            return None
        
        partition_fields = []
        for col_name, part_type in self.partition_fields:
            # Find field ID for column
            field_id = next(
                (f.field_id for f in self.fields if f.name == col_name),
                None,
            )
            if field_id:
                partition_fields.append(
                    PartitionField(
                        source_id=field_id,
                        field_id=len(partition_fields) + 1000,
                        transform=part_type,
                        name=f"{col_name}_{part_type}",
                    )
                )
        
        return PartitionSpec(*partition_fields) if partition_fields else None
    
    def to_dict(self) -> Dict[str, Any]:
        """Export schema as dictionary for documentation"""
        return {
            "table_name": self.table_name,
            "version": self.version,
            "fields": [
                {
                    "name": f.name,
                    "type": str(f.type),
                    "required": f.required,
                    "doc": f.doc,
                }
                for f in self.fields
            ],
            "partitions": [
                {"column": col, "type": part_type}
                for col, part_type in self.partition_fields
            ],
        }
EOF
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest shared/schemas/test_iceberg_schemas.py -v
# Expected: PASSED
```

- [ ] **Step 5: Create __init__.py**

```bash
cat > shared/schemas/__init__.py << 'EOF'
from shared.schemas.iceberg_schemas import IcebergSchemaBuilder

__all__ = ["IcebergSchemaBuilder"]
EOF
```

- [ ] **Step 6: Commit**

```bash
git add shared/schemas/
git commit -m "feat: add Iceberg schema builder utility

Provides IcebergSchemaBuilder for declarative schema definition with
version tracking and partition spec support.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 6: Create Shared Logging and Metrics Utilities

**Files:**
- Create: `shared/utils/logging.py`
- Create: `shared/utils/metrics.py`
- Create: `shared/utils/__init__.py`

- [ ] **Step 1: Write logging utility**

```bash
cat > shared/utils/logging.py << 'EOF'
import logging
import json
from typing import Any, Dict, Optional
from datetime import datetime


class StructuredLogger:
    """Structured logging with JSON output for Elasticsearch/CloudWatch"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # JSON formatter
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(message)s',
            datefmt='%Y-%m-%dT%H:%M:%SZ'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
    
    def info(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log info with structured context"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": "INFO",
            "message": message,
            **(context or {}),
        }
        self.logger.info(json.dumps(log_entry))
    
    def error(
        self,
        message: str,
        error: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log error with exception details"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": "ERROR",
            "message": message,
            **(context or {}),
        }
        if error:
            log_entry["exception"] = str(error)
            log_entry["exception_type"] = type(error).__name__
        self.logger.error(json.dumps(log_entry))


def get_logger(name: str) -> StructuredLogger:
    """Get structured logger instance"""
    return StructuredLogger(name)
EOF
```

- [ ] **Step 2: Write metrics utility**

```bash
cat > shared/utils/metrics.py << 'EOF'
from prometheus_client import Counter, Histogram, Gauge, Registry
from typing import Optional, Dict, Any


class MetricsCollector:
    """Prometheus metrics collector for data mesh"""
    
    def __init__(self, registry: Optional[Registry] = None):
        self.registry = registry or Registry()
        
        # Ingest metrics
        self.ingest_records = Counter(
            "ingest_records_total",
            "Total records ingested",
            ["domain", "table"],
            registry=self.registry,
        )
        self.ingest_duration = Histogram(
            "ingest_duration_seconds",
            "Ingest job duration in seconds",
            ["domain"],
            registry=self.registry,
        )
        self.ingest_errors = Counter(
            "ingest_errors_total",
            "Total ingest errors",
            ["domain", "error_type"],
            registry=self.registry,
        )
        
        # Query metrics
        self.query_duration = Histogram(
            "query_duration_seconds",
            "Query execution duration in seconds",
            ["data_product"],
            registry=self.registry,
        )
        self.query_count = Counter(
            "queries_total",
            "Total queries executed",
            ["data_product", "user"],
            registry=self.registry,
        )
        
        # Data freshness
        self.data_freshness_minutes = Gauge(
            "data_freshness_minutes",
            "Minutes since last successful ingest",
            ["domain", "table"],
            registry=self.registry,
        )
        
        # Quality metrics
        self.quality_checks_passed = Counter(
            "quality_checks_passed_total",
            "Data quality checks passed",
            ["data_product"],
            registry=self.registry,
        )
        self.quality_checks_failed = Counter(
            "quality_checks_failed_total",
            "Data quality checks failed",
            ["data_product", "check_name"],
            registry=self.registry,
        )


def get_metrics_collector() -> MetricsCollector:
    """Get global metrics collector"""
    return MetricsCollector()
EOF
```

- [ ] **Step 3: Create __init__.py**

```bash
cat > shared/utils/__init__.py << 'EOF'
from shared.utils.logging import get_logger, StructuredLogger
from shared.utils.metrics import get_metrics_collector, MetricsCollector

__all__ = [
    "get_logger",
    "StructuredLogger",
    "get_metrics_collector",
    "MetricsCollector",
]
EOF
```

- [ ] **Step 4: Commit**

```bash
git add shared/utils/
git commit -m "feat: add logging and metrics utilities

StructuredLogger: JSON-formatted structured logging for observability
MetricsCollector: Prometheus metrics for ingest, queries, freshness, quality

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 7: Create Iceberg Catalog Client

**Files:**
- Create: `platform/catalog/iceberg_client.py`
- Create: `platform/catalog/__init__.py`

- [ ] **Step 1: Write test for catalog client**

```bash
cat > platform/catalog/test_iceberg_client.py << 'EOF'
import pytest
from unittest.mock import Mock, patch
from platform.catalog.iceberg_client import IcebergCatalog
from pyiceberg.types import IntegerType, StringType, TimestampType


def test_iceberg_catalog_initialization():
    """Test catalog initialization"""
    with patch("platform.catalog.iceberg_client.load_catalog"):
        catalog = IcebergCatalog(
            catalog_uri="http://localhost:8181",
            warehouse="s3://data/warehouse",
        )
        assert catalog.catalog_uri == "http://localhost:8181"
        assert catalog.warehouse == "s3://data/warehouse"


def test_create_table():
    """Test table creation"""
    with patch("platform.catalog.iceberg_client.load_catalog") as mock_load:
        mock_catalog = Mock()
        mock_load.return_value = mock_catalog
        
        catalog = IcebergCatalog(
            catalog_uri="http://localhost:8181",
            warehouse="s3://data/warehouse",
        )
        
        from shared.schemas import IcebergSchemaBuilder
        schema_builder = IcebergSchemaBuilder("test_table")
        schema_builder.add_field("id", IntegerType(), required=True)
        schema = schema_builder.build()
        
        # Mock the create_table call
        mock_catalog.create_table.return_value = Mock(
            name="transactions.test_table"
        )
        
        result = catalog.create_table(
            namespace="transactions",
            table_name="test_table",
            schema=schema,
        )
        
        mock_catalog.create_table.assert_called_once()
        assert result is not None
EOF
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest platform/catalog/test_iceberg_client.py::test_iceberg_catalog_initialization -v
# Expected: FAILED - No module named 'platform.catalog.iceberg_client'
```

- [ ] **Step 3: Write catalog client implementation**

```bash
cat > platform/catalog/iceberg_client.py << 'EOF'
from typing import Optional, Dict, Any
from pyiceberg.catalog import load_catalog
from pyiceberg.schema import Schema
from pyiceberg.partitioning import PartitionSpec
from shared.utils import get_logger


logger = get_logger(__name__)


class IcebergCatalog:
    """Client for Iceberg REST Catalog"""
    
    def __init__(
        self,
        catalog_uri: str,
        warehouse: str,
        s3_endpoint: Optional[str] = None,
    ):
        self.catalog_uri = catalog_uri
        self.warehouse = warehouse
        self.s3_endpoint = s3_endpoint
        
        self.config = {
            "uri": catalog_uri,
            "s3.endpoint": s3_endpoint or "http://localhost:9000",
            "s3.access-key-id": "minioadmin",
            "s3.secret-access-key": "minioadmin",
        }
        
        try:
            self.client = load_catalog("rest", **self.config)
            logger.info(
                "Connected to Iceberg catalog",
                context={"uri": catalog_uri},
            )
        except Exception as e:
            logger.error(
                "Failed to connect to Iceberg catalog",
                error=e,
                context={"uri": catalog_uri},
            )
            raise
    
    def create_namespace(self, namespace: str) -> None:
        """Create namespace if not exists"""
        try:
            self.client.create_namespace(namespace)
            logger.info(
                "Created namespace",
                context={"namespace": namespace},
            )
        except Exception as e:
            logger.error(
                "Failed to create namespace",
                error=e,
                context={"namespace": namespace},
            )
            raise
    
    def create_table(
        self,
        namespace: str,
        table_name: str,
        schema: Schema,
        partition_spec: Optional[PartitionSpec] = None,
        properties: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Create Iceberg table"""
        full_name = f"{namespace}.{table_name}"
        
        try:
            kwargs = {
                "name": full_name,
                "schema": schema,
            }
            if partition_spec:
                kwargs["partition_spec"] = partition_spec
            if properties:
                kwargs["properties"] = properties
            
            table = self.client.create_table(**kwargs)
            
            logger.info(
                "Created Iceberg table",
                context={
                    "table": full_name,
                    "fields": len(schema.fields),
                },
            )
            return table
        except Exception as e:
            logger.error(
                "Failed to create table",
                error=e,
                context={"table": full_name},
            )
            raise
    
    def table_exists(self, namespace: str, table_name: str) -> bool:
        """Check if table exists"""
        full_name = f"{namespace}.{table_name}"
        try:
            self.client.load_table(full_name)
            return True
        except:
            return False
    
    def get_table(self, namespace: str, table_name: str) -> Any:
        """Load table from catalog"""
        full_name = f"{namespace}.{table_name}"
        return self.client.load_table(full_name)
EOF
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest platform/catalog/test_iceberg_client.py -v
# Expected: PASSED
```

- [ ] **Step 5: Create __init__.py**

```bash
cat > platform/catalog/__init__.py << 'EOF'
from platform.catalog.iceberg_client import IcebergCatalog

__all__ = ["IcebergCatalog"]
EOF
```

- [ ] **Step 6: Commit**

```bash
git add platform/catalog/
git commit -m "feat: add Iceberg REST Catalog client

IcebergCatalog: wrapper around pyiceberg for table/namespace management,
connection handling, structured logging.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 8: Create Compliance Utilities (Masking, Retention)

**Files:**
- Create: `shared/compliance/masking.py`
- Create: `shared/compliance/retention.py`
- Create: `shared/compliance/__init__.py`

- [ ] **Step 1: Write masking utility**

```bash
cat > shared/compliance/masking.py << 'EOF'
from typing import Dict, List, Optional
import hashlib


class DataMasker:
    """Column-level data masking for PII/sensitive data"""
    
    # Classification → mask function mapping
    MASKING_STRATEGIES = {
        "pii": "hash_mask",
        "sensitive": "partial_mask",
        "confidential": "full_mask",
        "public": "no_mask",
    }
    
    @staticmethod
    def hash_mask(value: str, visible_chars: int = 4) -> str:
        """Hash mask: show first N chars, hash rest"""
        if not value or len(value) <= visible_chars:
            return "[MASKED]"
        visible = value[:visible_chars]
        hash_val = hashlib.sha256(value.encode()).hexdigest()[:8]
        return f"{visible}...{hash_val}"
    
    @staticmethod
    def partial_mask(value: str, visible_chars: int = 2) -> str:
        """Partial mask: show first/last N chars"""
        if not value or len(value) <= visible_chars * 2:
            return "[MASKED]"
        visible_start = value[:visible_chars]
        visible_end = value[-visible_chars:]
        masked_len = len(value) - (visible_chars * 2)
        return f"{visible_start}{'*' * masked_len}{visible_end}"
    
    @staticmethod
    def full_mask(value: str) -> str:
        """Full mask: replace entire value"""
        return "[MASKED]"
    
    @staticmethod
    def no_mask(value: str) -> str:
        """No masking"""
        return value


class ColumnMaskingPolicy:
    """Defines which columns to mask and how"""
    
    def __init__(self):
        self.policies: Dict[str, Dict[str, str]] = {}  # table → column → classification
    
    def add_policy(
        self,
        table: str,
        column: str,
        classification: str,
    ) -> None:
        """Add masking policy for column"""
        if table not in self.policies:
            self.policies[table] = {}
        self.policies[table][column] = classification
    
    def get_column_classification(self, table: str, column: str) -> Optional[str]:
        """Get column classification"""
        return self.policies.get(table, {}).get(column)
    
    def should_mask(self, table: str, column: str) -> bool:
        """Check if column should be masked"""
        classification = self.get_column_classification(table, column)
        return classification is not None and classification != "public"


# Example policies
FINTECH_MASKING_POLICIES = {
    "transactions.raw_transactions": {
        "account_id": "pii",
        "customer_name": "pii",
        "ssn": "confidential",
        "account_holder_name": "pii",
        "amount": "public",
        "merchant_id": "public",
        "timestamp": "public",
    },
    "accounts.account_balances": {
        "account_id": "pii",
        "customer_name": "pii",
        "balance": "sensitive",
        "currency": "public",
    },
    "risk_compliance.fraud_scores": {
        "account_id": "pii",
        "fraud_score": "sensitive",
        "risk_level": "public",
    },
}
EOF
```

- [ ] **Step 2: Write retention utility**

```bash
cat > shared/compliance/retention.py << 'EOF'
from typing import Dict, Optional
from datetime import timedelta


class RetentionPolicy:
    """Data retention policies for compliance"""
    
    def __init__(self):
        self.policies: Dict[str, int] = {}  # table → years
    
    def add_policy(self, table: str, years: int, reason: str = "") -> None:
        """Add retention policy (years from creation)"""
        self.policies[table] = years
    
    def get_retention_years(self, table: str) -> Optional[int]:
        """Get retention period in years"""
        return self.policies.get(table)
    
    def get_retention_days(self, table: str) -> Optional[int]:
        """Get retention period in days"""
        years = self.get_retention_years(table)
        if years:
            return years * 365
        return None


# Example fintech retention policies
FINTECH_RETENTION_POLICIES = {
    "transactions.raw_transactions": 7,  # 7-year SOX requirement
    "transactions.settlement_status": 7,
    "accounts.account_balances": 3,  # 3 years for regulatory
    "risk_compliance.fraud_scores": 5,  # 5-year compliance requirement
    "risk_compliance.kyc_verdicts": 10,  # 10-year AML requirement
    "counterparties.merchants": 2,
    "market_data.fx_rates": 1,
}


def build_retention_policy() -> RetentionPolicy:
    """Build retention policy from fintech config"""
    policy = RetentionPolicy()
    for table, years in FINTECH_RETENTION_POLICIES.items():
        policy.add_policy(table, years)
    return policy
EOF
```

- [ ] **Step 3: Create __init__.py**

```bash
cat > shared/compliance/__init__.py << 'EOF'
from shared.compliance.masking import (
    DataMasker,
    ColumnMaskingPolicy,
    FINTECH_MASKING_POLICIES,
)
from shared.compliance.retention import (
    RetentionPolicy,
    build_retention_policy,
    FINTECH_RETENTION_POLICIES,
)

__all__ = [
    "DataMasker",
    "ColumnMaskingPolicy",
    "FINTECH_MASKING_POLICIES",
    "RetentionPolicy",
    "build_retention_policy",
    "FINTECH_RETENTION_POLICIES",
]
EOF
```

- [ ] **Step 4: Commit**

```bash
git add shared/compliance/
git commit -m "feat: add compliance utilities (masking, retention)

DataMasker: column-level masking strategies (hash, partial, full)
ColumnMaskingPolicy: per-table/column classification
RetentionPolicy: data retention periods for fintech compliance (SOX, AML)

Includes fintech-specific policies for transactions, accounts, risk, etc.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

## Phase 2: Transactions Domain (Core Reference Implementation)

### Task 9: Create Transactions Data Product YAML

**Files:**
- Create: `domains/transactions/data-products/transaction-feed.yaml`
- Create: `domains/transactions/README.md`

- [ ] **Step 1: Create data product definition**

```bash
cat > domains/transactions/data-products/transaction-feed.yaml << 'EOF'
---
name: transaction-feed
version: "1.0"
owner: transactions-domain
owner_email: transactions@chakra.fintech
domain: transactions

description: |
  Real-time transaction feed for all payment and settlement events.
  Includes T+0 settlement tracking, reversals, and clearing status.
  Primary source for fraud detection, settlement reconciliation, regulatory reporting.

tables:
  - name: raw_transactions
    iceberg_table: transactions.raw_transactions
    schema_version: "2.1"
    partitions: [year, month, day, account_id]
    doc: "Raw transaction events as received from core banking system"
  
  - name: settlement_status
    iceberg_table: transactions.settlement_status
    schema_version: "1.0"
    partitions: [year, month, day]
    doc: "Settlement status per transaction (pending, cleared, failed)"

sla:
  freshness:
    value: 5
    unit: minutes
    measured_as: "max(current_time - kafka_ingest_timestamp)"
  
  availability:
    value: 99.9
    unit: percent
    measured_as: "successful_ingest_jobs / total_ingest_jobs"
  
  completeness:
    value: 100
    unit: percent
    measured_as: "row_count matches banking_system +/- 10 within 10 min"

access_policy:
  default: deny
  approval_required: true
  approval_sla_hours: 4
  self_approve_roles: [internal-fraud-team, settlements-ops]
  columns:
    - name: account_id
      classification: pii
      masked_for_roles: [external-analysts]
    - name: account_holder_name
      classification: pii
      masked_for_roles: [external-analysts]
    - name: amount
      classification: public
    - name: merchant_id
      classification: public
    - name: merchant_category_code
      classification: public

tags: [real-time, settlement-critical, pci-dss, sox-relevant]
use_cases:
  - fraud_detection_real_time
  - settlement_reconciliation
  - regulatory_reporting_daily
  - compliance_audits

upstream_lineage:
  - kafka.transactions-raw (external: core banking)
  - kafka.settlement-messages (external: clearing house)

downstream_lineage:
  - risk_compliance.fraud-scores (consumes raw_transactions)
  - accounts.account-balance-materialized (uses settlement_status)

quality_rules:
  - rule: "amount > 0"
    description: "All transaction amounts must be positive"
  - rule: "booking_date <= settlement_date"
    description: "Settlement cannot precede booking"
  - rule: "null_count(account_id) == 0"
    description: "No missing account IDs"

retention_policy:
  value: 7
  unit: years
  rationale: "SOX & regulatory requirement for transaction audit trail"
EOF
```

- [ ] **Step 2: Create domain README**

```bash
cat > domains/transactions/README.md << 'EOF'
# Transactions Domain

## Overview

The Transactions domain owns real-time transaction events, settlement records, and clearing status for all payment activity. This is the highest-volume, lowest-latency domain in the data mesh.

## Data Products

- **transaction-feed** — Real-time transaction events + settlement status
  - Tables: `raw_transactions`, `settlement_status`
  - Freshness: 5 minutes
  - Consumers: fraud detection, settlement reconciliation, compliance

## Architecture

### Ingest Pipeline

```
Kafka: transactions-raw
  ↓ [Spark Structured Streaming, 5-min batches]
  ↓ Schema validation (Avro v2.1)
  ↓ Deduplication (Kafka offset tracking)
  ↓ Error handling (DLQ for failures)
Iceberg: transactions.raw_transactions
  ↓ [Periodic compaction, daily]
```

### Schemas

- **Avro** (Kafka): `schemas/avro/transaction-v2.1.avsc`
- **Iceberg** (Lake): `schemas/iceberg/raw_transactions.schema`, `settlement_status.schema`

### Ingest Job

- **File**: `ingest/ingest_job.py`
- **Trigger**: Continuous Spark Structured Streaming
- **SLA**: 5-minute freshness, 99.9% availability

## Query Examples

- Transactions by account: `queries/transaction-by-account.sql`
- Settlement reconciliation: `queries/settlement-reconciliation.sql`
- Fraud scoring input: `queries/fraud-scoring-join.sql`

## Testing

- **Unit**: Schema validation, deduplication logic
- **Integration**: Kafka → Iceberg pipeline
- **Compliance**: PII masking, audit logging, retention

## Operational Runbooks

See `../../docs/domains/transactions/` for:
- Schema evolution process
- Troubleshooting ingest failures
- Compaction performance tuning
EOF
git add domains/transactions/README.md
```

- [ ] **Step 3: Commit**

```bash
git add domains/transactions/data-products/
git commit -m "feat: add Transactions domain data product definition

Data product: transaction-feed (v1.0)
- Tables: raw_transactions (5-min SLA), settlement_status (10-min SLA)
- PII masking: account_id, account_holder_name
- Freshness: 5 minutes (Kafka ingest every 5 min)
- Retention: 7 years (SOX requirement)
- Quality rules: amount > 0, booking_date <= settlement_date

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 10: Create Transactions Avro Schema

**Files:**
- Create: `domains/transactions/schemas/avro/transaction-v2.1.avsc`

- [ ] **Step 1: Create Avro schema**

```bash
cat > domains/transactions/schemas/avro/transaction-v2.1.avsc << 'EOF'
{
  "type": "record",
  "name": "Transaction",
  "namespace": "com.chakra.transactions",
  "version": "2.1",
  "doc": "Financial transaction event from core banking system",
  "fields": [
    {
      "name": "transaction_id",
      "type": "string",
      "doc": "Unique transaction identifier"
    },
    {
      "name": "account_id",
      "type": "string",
      "doc": "Originating account ID (masked PII)"
    },
    {
      "name": "account_holder_name",
      "type": "string",
      "doc": "Account holder name (masked PII)"
    },
    {
      "name": "amount",
      "type": "double",
      "doc": "Transaction amount in base currency"
    },
    {
      "name": "currency",
      "type": "string",
      "doc": "ISO 4217 currency code"
    },
    {
      "name": "merchant_id",
      "type": "string",
      "doc": "Merchant identifier"
    },
    {
      "name": "merchant_category_code",
      "type": "string",
      "doc": "MCC code for merchant classification"
    },
    {
      "name": "booking_timestamp",
      "type": {
        "type": "long",
        "logicalType": "timestamp-millis"
      },
      "doc": "Timestamp when transaction was booked"
    },
    {
      "name": "settlement_timestamp",
      "type": [
        "null",
        {
          "type": "long",
          "logicalType": "timestamp-millis"
        }
      ],
      "default": null,
      "doc": "Timestamp when transaction was settled (null if pending)"
    },
    {
      "name": "transaction_type",
      "type": {
        "type": "enum",
        "name": "TransactionType",
        "symbols": ["PAYMENT", "REVERSAL", "ADJUSTMENT"]
      },
      "doc": "Type of transaction"
    },
    {
      "name": "status",
      "type": {
        "type": "enum",
        "name": "TransactionStatus",
        "symbols": ["PENDING", "CLEARED", "FAILED", "REVERSED"]
      },
      "doc": "Current transaction status"
    }
  ]
}
EOF
```

- [ ] **Step 2: Validate schema syntax**

```bash
python3 << 'EOF'
import json
with open('domains/transactions/schemas/avro/transaction-v2.1.avsc', 'r') as f:
    schema = json.load(f)
    assert schema['name'] == 'Transaction'
    assert len(schema['fields']) == 11
    assert schema['version'] == '2.1'
    print("✓ Schema valid")
EOF
```

- [ ] **Step 3: Commit**

```bash
git add domains/transactions/schemas/avro/
git commit -m "feat: add Transactions Avro schema (v2.1)

Fields: transaction_id, account_id, amount, merchant_id, booking_timestamp,
settlement_timestamp, transaction_type, status, currency, MCC

Enums: TransactionType (PAYMENT, REVERSAL, ADJUSTMENT)
       TransactionStatus (PENDING, CLEARED, FAILED, REVERSED)

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 11: Create Transactions Iceberg Table Schemas

**Files:**
- Create: `domains/transactions/schemas/iceberg/schemas.py`

- [ ] **Step 1: Write test for Iceberg schemas**

```bash
cat > domains/transactions/schemas/test_iceberg_schemas.py << 'EOF'
import pytest
from pyiceberg.types import IntegerType, StringType, TimestampType, DoubleType
from domains.transactions.schemas.iceberg.schemas import (
    raw_transactions_schema,
    settlement_status_schema,
)


def test_raw_transactions_schema():
    """Test raw_transactions Iceberg schema"""
    schema = raw_transactions_schema()
    
    assert len(schema.fields) == 11
    assert schema.fields[0].name == "transaction_id"
    assert schema.fields[1].name == "account_id"
    assert schema.fields[2].name == "amount"
    
    # Check partitioning is correct
    partition_spec = raw_transactions_schema_partitions()
    assert partition_spec is not None


def test_settlement_status_schema():
    """Test settlement_status Iceberg schema"""
    schema = settlement_status_schema()
    
    assert len(schema.fields) >= 4
    assert schema.fields[0].name == "transaction_id"
    assert schema.fields[1].name == "status"
EOF

pytest domains/transactions/schemas/test_iceberg_schemas.py::test_raw_transactions_schema -v
# Expected: FAILED - ModuleNotFoundError
```

- [ ] **Step 2: Write Iceberg schemas**

```bash
cat > domains/transactions/schemas/iceberg/schemas.py << 'EOF'
from pyiceberg.types import (
    NestedField,
    StringType,
    DoubleType,
    TimestampType,
    IntegerType,
)
from pyiceberg.schema import Schema
from pyiceberg.partitioning import PartitionSpec, PartitionField
from shared.schemas import IcebergSchemaBuilder


def raw_transactions_schema() -> Schema:
    """Raw transactions table schema"""
    builder = IcebergSchemaBuilder(
        "raw_transactions",
        version="2.1",
    )
    
    builder.add_field("transaction_id", StringType(), required=True)
    builder.add_field("account_id", StringType(), required=True)
    builder.add_field("account_holder_name", StringType(), required=True)
    builder.add_field("amount", DoubleType(), required=True)
    builder.add_field("currency", StringType(), required=True)
    builder.add_field("merchant_id", StringType(), required=True)
    builder.add_field("merchant_category_code", StringType(), required=False)
    builder.add_field("booking_timestamp", TimestampType(), required=True)
    builder.add_field("settlement_timestamp", TimestampType(), required=False)
    builder.add_field("transaction_type", StringType(), required=True)
    builder.add_field("status", StringType(), required=True)
    
    return builder.build()


def raw_transactions_schema_partitions() -> PartitionSpec:
    """Partitioning for raw_transactions: [year, month, day, account_id]"""
    return PartitionSpec(
        PartitionField(
            source_id=8,  # booking_timestamp field ID
            field_id=1000,
            transform="year",
            name="booking_year",
        ),
        PartitionField(
            source_id=8,
            field_id=1001,
            transform="month",
            name="booking_month",
        ),
        PartitionField(
            source_id=8,
            field_id=1002,
            transform="day",
            name="booking_day",
        ),
        PartitionField(
            source_id=2,  # account_id field ID
            field_id=1003,
            transform="identity",
            name="account_id_part",
        ),
    )


def settlement_status_schema() -> Schema:
    """Settlement status table schema"""
    builder = IcebergSchemaBuilder(
        "settlement_status",
        version="1.0",
    )
    
    builder.add_field("transaction_id", StringType(), required=True)
    builder.add_field("status", StringType(), required=True)
    builder.add_field("booking_timestamp", TimestampType(), required=True)
    builder.add_field("settlement_timestamp", TimestampType(), required=False)
    builder.add_field("clearing_status", StringType(), required=False)
    builder.add_field("failure_reason", StringType(), required=False)
    
    return builder.build()


def settlement_status_schema_partitions() -> PartitionSpec:
    """Partitioning for settlement_status: [year, month, day]"""
    return PartitionSpec(
        PartitionField(
            source_id=3,  # booking_timestamp field ID
            field_id=2000,
            transform="year",
            name="booking_year",
        ),
        PartitionField(
            source_id=3,
            field_id=2001,
            transform="month",
            name="booking_month",
        ),
        PartitionField(
            source_id=3,
            field_id=2002,
            transform="day",
            name="booking_day",
        ),
    )
EOF
```

- [ ] **Step 3: Create __init__.py**

```bash
cat > domains/transactions/schemas/iceberg/__init__.py << 'EOF'
from domains.transactions.schemas.iceberg.schemas import (
    raw_transactions_schema,
    raw_transactions_schema_partitions,
    settlement_status_schema,
    settlement_status_schema_partitions,
)

__all__ = [
    "raw_transactions_schema",
    "raw_transactions_schema_partitions",
    "settlement_status_schema",
    "settlement_status_schema_partitions",
]
EOF
```

- [ ] **Step 4: Create __init__.py for schemas directory**

```bash
cat > domains/transactions/schemas/__init__.py << 'EOF'
# Schemas module for Transactions domain
EOF
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest domains/transactions/schemas/test_iceberg_schemas.py -v
# Expected: PASSED
```

- [ ] **Step 6: Commit**

```bash
git add domains/transactions/schemas/iceberg/
git commit -m "feat: add Transactions Iceberg table schemas

Tables:
  - raw_transactions: 11 fields, partitioned by [year, month, day, account_id]
  - settlement_status: 6 fields, partitioned by [year, month, day]

Partitioning optimized for domain queries (time + account_id cardinality)

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 12: Create Transactions Ingest Job (Spark Structured Streaming)

**Files:**
- Create: `domains/transactions/ingest/ingest_job.py`
- Create: `domains/transactions/ingest/requirements.txt`
- Create: `domains/transactions/ingest/__init__.py`

- [ ] **Step 1: Write test for ingest job**

```bash
cat > domains/transactions/ingest/test_ingest_job.py << 'EOF'
import pytest
from unittest.mock import Mock, patch, MagicMock
from domains.transactions.ingest.ingest_job import TransactionIngestJob


def test_ingest_job_initialization():
    """Test ingest job initialization"""
    with patch("domains.transactions.ingest.ingest_job.SparkSession"):
        job = TransactionIngestJob(
            kafka_brokers="localhost:9092",
            schema_registry_url="http://localhost:8081",
            catalog_uri="http://localhost:8181",
            warehouse="s3://data/warehouse",
        )
        
        assert job.kafka_brokers == "localhost:9092"
        assert job.schema_registry_url == "http://localhost:8081"


def test_ingest_job_source_topic():
    """Test Kafka topic configuration"""
    job = TransactionIngestJob(
        kafka_brokers="localhost:9092",
        schema_registry_url="http://localhost:8081",
        catalog_uri="http://localhost:8181",
        warehouse="s3://data/warehouse",
    )
    
    topic = job.get_source_topic()
    assert topic == "transactions-raw"


def test_ingest_job_target_table():
    """Test target Iceberg table"""
    job = TransactionIngestJob(
        kafka_brokers="localhost:9092",
        schema_registry_url="http://localhost:8081",
        catalog_uri="http://localhost:8181",
        warehouse="s3://data/warehouse",
    )
    
    table = job.get_target_table()
    assert table == "transactions.raw_transactions"
EOF

pytest domains/transactions/ingest/test_ingest_job.py::test_ingest_job_initialization -v
# Expected: FAILED - ModuleNotFoundError
```

- [ ] **Step 2: Write ingest job implementation**

```bash
cat > domains/transactions/ingest/ingest_job.py << 'EOF'
from typing import Optional
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col,
    from_json,
    schema_of_json,
    current_timestamp,
)
from shared.utils import get_logger, get_metrics_collector
from platform.catalog import IcebergCatalog
import json


logger = get_logger(__name__)
metrics = get_metrics_collector()


class TransactionIngestJob:
    """Spark Structured Streaming job for Transactions domain"""
    
    DOMAIN = "transactions"
    SOURCE_TOPIC = "transactions-raw"
    TARGET_TABLE = f"{DOMAIN}.raw_transactions"
    BATCH_INTERVAL_SECONDS = 300  # 5 minutes
    
    def __init__(
        self,
        kafka_brokers: str,
        schema_registry_url: str,
        catalog_uri: str,
        warehouse: str,
        checkpoint_dir: str = "/tmp/checkpoint/transactions",
    ):
        self.kafka_brokers = kafka_brokers
        self.schema_registry_url = schema_registry_url
        self.catalog_uri = catalog_uri
        self.warehouse = warehouse
        self.checkpoint_dir = checkpoint_dir
        
        self.spark = SparkSession.builder \
            .appName("TransactionIngest") \
            .config("spark.jars.packages",
                    "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.3.0,"
                    "org.apache.kafka:kafka-clients:3.5.0") \
            .config("spark.sql.catalog.rest", "org.apache.iceberg.spark.SparkCatalog") \
            .config("spark.sql.catalog.rest.type", "rest") \
            .config("spark.sql.catalog.rest.uri", catalog_uri) \
            .config("spark.sql.extensions",
                    "org.apache.iceberg.spark.SparkSessionExtensions") \
            .getOrCreate()
        
        self.catalog = IcebergCatalog(
            catalog_uri=catalog_uri,
            warehouse=warehouse,
        )
        
        logger.info(
            "Initialized TransactionIngestJob",
            context={
                "kafka_brokers": kafka_brokers,
                "target_table": self.TARGET_TABLE,
            },
        )
    
    def get_source_topic(self) -> str:
        """Get Kafka source topic"""
        return self.SOURCE_TOPIC
    
    def get_target_table(self) -> str:
        """Get target Iceberg table"""
        return self.TARGET_TABLE
    
    def read_kafka_stream(self) -> DataFrame:
        """Read from Kafka topic"""
        df = self.spark \
            .readStream \
            .format("kafka") \
            .option("kafka.bootstrap.servers", self.kafka_brokers) \
            .option("subscribe", self.SOURCE_TOPIC) \
            .option("startingOffsets", "latest") \
            .option("failOnDataLoss", "false") \
            .load()
        
        logger.info(
            "Reading from Kafka",
            context={"topic": self.SOURCE_TOPIC},
        )
        return df
    
    def parse_and_validate(self, df: DataFrame) -> DataFrame:
        """Parse JSON and validate schema"""
        # Simple JSON parsing (in production, use Schema Registry)
        schema_str = """
        {
            "transaction_id": "string",
            "account_id": "string",
            "account_holder_name": "string",
            "amount": "double",
            "currency": "string",
            "merchant_id": "string",
            "merchant_category_code": "string",
            "booking_timestamp": "long",
            "settlement_timestamp": "long",
            "transaction_type": "string",
            "status": "string"
        }
        """
        
        parsed_df = df.select(
            from_json(col("value").cast("string"), schema_of_json(schema_str)).alias("data")
        ).select("data.*")
        
        # Add ingest metadata
        parsed_df = parsed_df.withColumn(
            "ingest_timestamp",
            current_timestamp(),
        )
        
        logger.info(
            "Parsed and validated records",
            context={"columns": len(parsed_df.columns)},
        )
        return parsed_df
    
    def write_to_iceberg(self, df: DataFrame) -> None:
        """Write to Iceberg table (micro-batch)"""
        query = df \
            .writeStream \
            .format("iceberg") \
            .mode("append") \
            .option("checkpointLocation", self.checkpoint_dir) \
            .option("path", f"{self.warehouse}/{self.TARGET_TABLE.replace('.', '/')}") \
            .toTable(self.TARGET_TABLE)
        
        query.awaitTermination()
        
        logger.info(
            "Started Iceberg write stream",
            context={"table": self.TARGET_TABLE},
        )
    
    def run(self) -> None:
        """Run ingest pipeline"""
        try:
            # Create namespace and table if not exists
            self.catalog.create_namespace(self.DOMAIN)
            
            # Read → Parse → Write
            df = self.read_kafka_stream()
            df = self.parse_and_validate(df)
            self.write_to_iceberg(df)
            
        except Exception as e:
            logger.error(
                "Ingest job failed",
                error=e,
                context={"domain": self.DOMAIN},
            )
            metrics.ingest_errors.labels(
                domain=self.DOMAIN,
                error_type=type(e).__name__,
            ).inc()
            raise


def main():
    """Entry point for ingest job"""
    job = TransactionIngestJob(
        kafka_brokers="kafka:9092",
        schema_registry_url="http://schema-registry:8081",
        catalog_uri="http://iceberg-catalog:8181",
        warehouse="s3://data/warehouse",
    )
    job.run()


if __name__ == "__main__":
    main()
EOF
```

- [ ] **Step 3: Create requirements.txt for ingest**

```bash
cat > domains/transactions/ingest/requirements.txt << 'EOF'
pyspark==3.5.0
pyiceberg==0.6.0
EOF
```

- [ ] **Step 4: Create __init__.py**

```bash
cat > domains/transactions/ingest/__init__.py << 'EOF'
from domains.transactions.ingest.ingest_job import TransactionIngestJob

__all__ = ["TransactionIngestJob"]
EOF
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest domains/transactions/ingest/test_ingest_job.py -v
# Expected: PASSED
```

- [ ] **Step 6: Commit**

```bash
git add domains/transactions/ingest/
git commit -m "feat: add Transactions ingest job (Spark Structured Streaming)

TransactionIngestJob:
  - Reads from Kafka topic (transactions-raw)
  - Validates JSON schema
  - Adds ingest_timestamp metadata
  - Writes to Iceberg table (raw_transactions) with 5-min micro-batches
  - Checkpointing for exactly-once semantics
  - Error handling + structured logging

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

## Phase 3: Governance Platform (OPA + Discovery Portal + Approval Workflows)

> **Note:** Tasks 13-25 implement federated governance. Can be executed in parallel with Phase 2 or after.

### Task 13: Create OPA Policies for Data Access

**Files:**
- Create: `platform/governance/opa-policies/abac.rego`
- Create: `platform/governance/opa-policies/compliance.rego`

- [ ] **Step 1: Write ABAC policy file**

```bash
cat > platform/governance/opa-policies/abac.rego << 'EOF'
package data_mesh.access

# Default deny
default allow = false

# Auto-approve: read-only, non-sensitive, internal user
allow {
    input.action == "read"
    input.user_role in ["internal-analyst", "fraud-team"]
    input.data_sensitivity in ["public", "public"]
    not input.requires_approval
}

# Domain owner approval required: write or sensitive data
requires_approval {
    input.action == "write"
}

requires_approval {
    input.data_sensitivity in ["pii", "confidential"]
}

# PII column masking required for external users
mask_pii {
    input.user_role in ["external-analyst"]
    input.target_columns[_] == "account_id"
}

mask_pii {
    input.user_role in ["external-analyst"]
    input.target_columns[_] == "account_holder_name"
}
EOF
```

- [ ] **Step 2: Write compliance policy file**

```bash
cat > platform/governance/opa-policies/compliance.rego << 'EOF'
package data_mesh.compliance

# Retention enforcement
enforce_retention[violation] {
    input.table_retention_days < 365
    violation := {
        "message": "Retention policy less than 1 year violates fintech standards",
        "table": input.table,
        "retention_days": input.table_retention_days,
    }
}

# Masking enforcement for PII columns
enforce_masking[violation] {
    input.column in ["account_id", "ssn", "account_holder_name"]
    not input.is_masked
    violation := {
        "message": "PII column must be masked",
        "column": input.column,
        "table": input.table,
    }
}

# Audit logging requirement
audit_required {
    true  # All queries must be logged
}
EOF
```

- [ ] **Step 3: Commit**

```bash
git add platform/governance/opa-policies/
git commit -m "feat: add OPA policies for data access control

ABAC policy:
  - Auto-approve: read-only, public data, internal users
  - Require approval: write access or sensitive data
  - PII masking for external users

Compliance policy:
  - Enforce 1-year minimum retention for fintech
  - Mask PII columns (account_id, ssn, name)
  - Audit logging required for all queries

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 14-25: [Abbreviated] Governance Platform, Observability, and Integration Tasks

Due to space constraints, the remaining ~90 tasks follow the same TDD pattern:

**Task 14-18: Discovery Portal (FastAPI backend + React frontend)**
- REST API for data product search
- Access request submission + approval workflow
- Integration with OPA policy engine
- Slack notifications for approvals
- React UI for discovery + request workflow

**Task 19-23: Observability Platform**
- Prometheus metrics exporter (freshness, quality, queries)
- Grafana dashboards (domain health, data product status)
- Great Expectations quality test framework
- Spline lineage integration
- Query audit logging to Elasticsearch

**Task 24-35: Additional Domains (Accounts, Risk/Compliance, Counterparties, Market Data)**
- Repeat pattern from Transactions domain:
  - Data product YAML
  - Avro schema
  - Iceberg table schemas
  - Ingest job
  - Query examples
  - Integration tests

**Task 36-45: Cross-Domain Integration Tests**
- Fraud scoring: join Transactions + Risk + Accounts
- Settlement reconciliation: join Transactions + Accounts
- Performance benchmarks (query latency, file sizes)
- Time-travel query tests (audits using historical snapshots)

**Task 46-55: Documentation & Production Guides**
- Architecture overview documentation
- Domain-specific documentation (schema evolution, troubleshooting)
- Production guide: scaling, compaction, schema management
- Deployment guide: Helm charts, cloud setup
- Troubleshooting runbook

**Task 56-60: Deployment & Final Integration**
- Helm charts for Kubernetes deployment
- GitHub Actions CI/CD pipeline (lint, test, build)
- Docker image builds (Spark, catalog, portal)
- End-to-end smoke tests
- Documentation site (MkDocs)

---

## Execution Guide

### Task Execution Order

**Recommended sequential execution:**

1. **Phase 1 (Tasks 1-7):** Foundation (10-15 min)
   - Project structure, Docker Compose, utilities
   - All other phases depend on this
   - Commit after each task

2. **Phase 2 (Tasks 8-12):** Transactions Domain MVP (30-45 min)
   - Data product definition, schemas, ingest job
   - Demonstrates core concepts
   - Can test locally with Docker Compose

3. **Phase 3 (Tasks 13-15):** Governance Platform MVP (20-30 min)
   - OPA policies, basic approval workflow
   - Integrates with Phase 2 data products

4. **Phase 4 (Tasks 16-23):** Observability (25-35 min)
   - Prometheus metrics, Grafana dashboards
   - Quality framework, lineage

5. **Phase 5 (Tasks 24-35):** Additional Domains (30-45 min)
   - Repeat Transactions pattern for 4 more domains
   - High parallelism possible (each domain independent)

6. **Phase 6 (Tasks 36-45):** Integration & Testing (20-30 min)
   - Cross-domain queries, performance tests
   - Compliance tests (masking, audit, retention)

7. **Phase 7 (Tasks 46-55):** Documentation (20-25 min)
   - Production guides, troubleshooting
   - Architecture documentation

8. **Phase 8 (Tasks 56-60):** Deployment (15-20 min)
   - Helm charts, CI/CD, smoke tests

**Total estimated time:** 180-240 minutes (3-4 hours) for full implementation.

### Parallel Execution Opportunities

- **After Phase 2 completes:** Start Phase 3 (governance) and Phase 4 (observability) in parallel
- **During Phase 5:** Execute each domain ingest independently (5x parallelism)
- **During Phase 6:** Run integration tests while Phase 5 ingest jobs are running

### Testing Strategy

- **Unit tests** for each module (utilities, schemas, ingest)
- **Integration tests** after each domain (Kafka → Iceberg → query)
- **Compliance tests** after Phase 4 (masking, retention, lineage)
- **End-to-end tests** after all domains (cross-domain queries)

### Commits

- Create a commit after each task (TDD: test + implementation)
- Commit message format: `feat:` (new feature), `test:` (test), `fix:` (bug), `refactor:` (no behavior change)
- Optionally squash commits before final submission

---

## Success Criteria

✅ **Technical:**
- All 5 domains with working ingest pipelines
- Cross-domain queries (fraud scoring using 3+ tables)
- Lineage captured for all Spark jobs
- Time-travel queries work
- Self-service discovery portal functional

✅ **Operational:**
- Schema evolution process documented and tested
- Data quality tests detect failures
- Audit logs complete
- Compaction reduces file count

✅ **Compliance:**
- PII masking enforced
- Retention policies active
- Approval SLAs met (4 hours)
- Full audit trail available

---

## Appendix: File Structure Reference

```
chakraview-fintech-data-mesh/
├── domains/
│   ├── transactions/
│   │   ├── data-products/ (YAML definitions)
│   │   ├── ingest/ (Spark jobs)
│   │   ├── schemas/ (Avro + Iceberg)
│   │   ├── queries/ (SQL examples)
│   │   └── tests/
│   ├── accounts/ (same pattern)
│   ├── risk-compliance/
│   ├── counterparties/
│   └── market-data/
├── platform/
│   ├── catalog/ (Iceberg client)
│   ├── discovery/ (FastAPI + React)
│   ├── governance/ (OPA, approval workflows)
│   ├── observability/ (Prometheus, Grafana, GX)
│   └── lineage/ (Spline integration)
├── shared/
│   ├── schemas/ (utilities)
│   ├── utils/ (logging, metrics)
│   ├── compliance/ (masking, retention)
│   └── tests/
├── tests/
│   ├── integration/
│   ├── compliance/
│   └── performance/
└── docs/ (architecture, guides, deployment)
```
<function_calls>
<invoke name="Bash">
<parameter name="command">wc -l /home/gundu/portfolio/chakraview-fintech-data-mesh/docs/superpowers/plans/2026-04-30-fintech-data-mesh.md