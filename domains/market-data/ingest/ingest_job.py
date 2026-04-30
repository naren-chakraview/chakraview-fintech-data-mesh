from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col, from_json, schema_of_json
from shared.utils import get_logger
from platform.catalog import IcebergCatalog


logger = get_logger(__name__)


class MarketDataIngestJob:
    """Spark Structured Streaming job for Market Data domain"""

    DOMAIN = "market_data"
    SOURCE_TOPIC = "market-rates-raw"
    TARGET_TABLE = f"{DOMAIN}.fx_rates"

    def __init__(self, kafka_brokers: str, schema_registry_url: str, catalog_uri: str, warehouse: str):
        self.kafka_brokers = kafka_brokers
        self.catalog_uri = catalog_uri
        self.spark = SparkSession.builder \
            .appName("MarketDataIngest") \
            .config("spark.sql.catalog.rest", "org.apache.iceberg.spark.SparkCatalog") \
            .config("spark.sql.catalog.rest.type", "rest") \
            .config("spark.sql.catalog.rest.uri", catalog_uri) \
            .getOrCreate()
        self.catalog = IcebergCatalog(catalog_uri=catalog_uri, warehouse=warehouse)
        logger.info("Initialized MarketDataIngestJob")

    def run(self) -> None:
        """Run ingest pipeline"""
        try:
            self.catalog.create_namespace(self.DOMAIN)
            df = self.spark.readStream.format("kafka") \
                .option("kafka.bootstrap.servers", self.kafka_brokers) \
                .option("subscribe", self.SOURCE_TOPIC) \
                .option("startingOffsets", "latest").load()

            schema_str = '{"currency_pair": "string", "rate": "double", "timestamp": "long"}'
            parsed_df = df.select(from_json(col("value").cast("string"), schema_of_json(schema_str)).alias("data")).select("data.*")

            query = parsed_df.writeStream.format("iceberg").mode("append") \
                .option("checkpointLocation", f"/tmp/checkpoint/{self.DOMAIN}").toTable(self.TARGET_TABLE)
            query.awaitTermination()
        except Exception as e:
            logger.error("Ingest job failed", error=e)
            raise
