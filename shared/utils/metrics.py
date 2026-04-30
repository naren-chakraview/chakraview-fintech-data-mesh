from prometheus_client import Counter, Histogram, Gauge, Registry
from typing import Optional


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
