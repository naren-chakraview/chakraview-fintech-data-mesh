from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col, from_json, schema_of_json, current_timestamp
from shared.utils import get_logger
from platform.catalog import IcebergCatalog


logger = get_logger(__name__)


class AccountIngestJob:
    """Spark Structured Streaming job for Accounts domain"""

    DOMAIN = "accounts"
    SOURCE_TOPIC = "accounts-raw"
    TARGET_TABLE = f"{DOMAIN}.accounts"
    BATCH_INTERVAL_SECONDS = 600

    def __init__(
        self,
        kafka_brokers: str,
        schema_registry_url: str,
        catalog_uri: str,
        warehouse: str,
    ):
        self.kafka_brokers = kafka_brokers
        self.schema_registry_url = schema_registry_url
        self.catalog_uri = catalog_uri
        self.warehouse = warehouse

        self.spark = SparkSession.builder \
            .appName("AccountIngest") \
            .config("spark.sql.catalog.rest", "org.apache.iceberg.spark.SparkCatalog") \
            .config("spark.sql.catalog.rest.type", "rest") \
            .config("spark.sql.catalog.rest.uri", catalog_uri) \
            .getOrCreate()

        self.catalog = IcebergCatalog(
            catalog_uri=catalog_uri,
            warehouse=warehouse,
        )

        logger.info(
            "Initialized AccountIngestJob",
            context={"kafka_brokers": kafka_brokers},
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
            .load()
        logger.info("Reading from Kafka", context={"topic": self.SOURCE_TOPIC})
        return df

    def parse_and_validate(self, df: DataFrame) -> DataFrame:
        """Parse JSON and validate schema"""
        schema_str = """
        {
            "account_id": "string",
            "customer_id": "string",
            "customer_name": "string",
            "account_type": "string",
            "currency": "string",
            "balance": "double",
            "available_balance": "double",
            "status": "string",
            "opened_date": "long",
            "last_updated": "long"
        }
        """
        parsed_df = df.select(
            from_json(col("value").cast("string"), schema_of_json(schema_str)).alias("data")
        ).select("data.*").withColumn("ingest_timestamp", current_timestamp())
        return parsed_df

    def write_to_iceberg(self, df: DataFrame) -> None:
        """Write to Iceberg table"""
        query = df \
            .writeStream \
            .format("iceberg") \
            .mode("append") \
            .option("checkpointLocation", f"/tmp/checkpoint/{self.DOMAIN}") \
            .toTable(self.TARGET_TABLE)
        query.awaitTermination()
        logger.info("Started Iceberg write stream", context={"table": self.TARGET_TABLE})

    def run(self) -> None:
        """Run ingest pipeline"""
        try:
            self.catalog.create_namespace(self.DOMAIN)
            df = self.read_kafka_stream()
            df = self.parse_and_validate(df)
            self.write_to_iceberg(df)
        except Exception as e:
            logger.error("Ingest job failed", error=e, context={"domain": self.DOMAIN})
            raise


def main():
    """Entry point"""
    job = AccountIngestJob(
        kafka_brokers="kafka:9092",
        schema_registry_url="http://schema-registry:8081",
        catalog_uri="http://iceberg-catalog:8181",
        warehouse="s3://data/warehouse",
    )
    job.run()


if __name__ == "__main__":
    main()
