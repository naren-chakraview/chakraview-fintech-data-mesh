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


logger = get_logger(__name__)
metrics = get_metrics_collector()


class TransactionIngestJob:
    """Spark Structured Streaming job for Transactions domain"""

    DOMAIN = "transactions"
    SOURCE_TOPIC = "transactions-raw"
    TARGET_TABLE = f"{DOMAIN}.raw_transactions"
    BATCH_INTERVAL_SECONDS = 300

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
            self.catalog.create_namespace(self.DOMAIN)

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
