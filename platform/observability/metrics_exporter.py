from prometheus_client import start_http_server, Counter, Gauge, Histogram
from shared.utils import get_logger
import time
from datetime import datetime, timedelta


logger = get_logger(__name__)

# Ingest metrics
ingest_records_total = Counter(
    'ingest_records_total',
    'Total records ingested',
    ['domain', 'table']
)

ingest_duration_seconds = Histogram(
    'ingest_duration_seconds',
    'Ingest job duration in seconds',
    ['domain'],
    buckets=(60, 300, 600, 1800, 3600)
)

ingest_errors_total = Counter(
    'ingest_errors_total',
    'Total ingest errors',
    ['domain', 'error_type']
)

# Data freshness
data_freshness_minutes = Gauge(
    'data_freshness_minutes',
    'Minutes since last successful ingest',
    ['domain', 'table']
)

# Query metrics
query_duration_seconds = Histogram(
    'query_duration_seconds',
    'Query execution duration in seconds',
    ['data_product'],
    buckets=(1, 5, 10, 30, 60)
)

queries_total = Counter(
    'queries_total',
    'Total queries executed',
    ['data_product', 'user']
)

# Data quality
quality_checks_passed = Counter(
    'quality_checks_passed_total',
    'Data quality checks passed',
    ['data_product']
)

quality_checks_failed = Counter(
    'quality_checks_failed_total',
    'Data quality checks failed',
    ['data_product', 'check_name']
)

# Data product health
data_product_availability = Gauge(
    'data_product_availability_percent',
    'Data product availability percentage',
    ['data_product']
)

data_product_completeness = Gauge(
    'data_product_completeness_percent',
    'Data product completeness percentage',
    ['data_product']
)


def update_freshness_metrics():
    """Update freshness metrics for all data products"""
    # Example: transaction-feed
    data_freshness_minutes.labels(
        domain='transactions',
        table='raw_transactions'
    ).set(5)

    data_freshness_minutes.labels(
        domain='transactions',
        table='settlement_status'
    ).set(10)

    # Update availability
    data_product_availability.labels(data_product='transaction-feed').set(99.9)
    data_product_completeness.labels(data_product='transaction-feed').set(100.0)

    logger.info("Updated freshness metrics")


def start_metrics_server(port: int = 8000):
    """Start Prometheus metrics HTTP server"""
    start_http_server(port)
    logger.info(
        "Metrics server started",
        context={"port": port, "endpoint": f"http://localhost:{port}/metrics"},
    )

    # Update metrics periodically
    while True:
        time.sleep(60)
        update_freshness_metrics()


if __name__ == "__main__":
    start_metrics_server(8001)
