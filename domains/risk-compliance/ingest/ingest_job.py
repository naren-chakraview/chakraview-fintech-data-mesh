from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col, from_json, schema_of_json, current_timestamp
from shared.utils import get_logger
from platform.catalog import IcebergCatalog


logger = get_logger(__name__)


class RiskComplianceIngestJob:
    """Spark Structured Streaming job for Risk/Compliance domain"""

    DOMAIN = "risk_compliance"
    SOURCE_TOPIC = "risk-scores-raw"
    TARGET_TABLE = f"{DOMAIN}.fraud_scores"

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
            .appName("RiskComplianceIngest") \
            .config("spark.sql.catalog.rest", "org.apache.iceberg.spark.SparkCatalog") \
            .config("spark.sql.catalog.rest.type", "rest") \
            .config("spark.sql.catalog.rest.uri", catalog_uri) \
            .getOrCreate()

        self.catalog = IcebergCatalog(
            catalog_uri=catalog_uri,
            warehouse=warehouse,
        )

        logger.info(
            "Initialized RiskComplianceIngestJob",
            context={"kafka_brokers": kafka_brokers},
        )

    def read_kafka_stream(self) -> DataFrame:
        """Read from Kafka topic"""
        df = self.spark \
            .readStream \
            .format("kafka") \
            .option("kafka.bootstrap.servers", self.kafka_brokers) \
            .option("subscribe", self.SOURCE_TOPIC) \
            .option("startingOffsets", "latest") \
            .load()
        return df

    def parse_and_validate(self, df: DataFrame) -> DataFrame:
        """Parse JSON and validate schema"""
        schema_str = """
        {
            "transaction_id": "string",
            "account_id": "string",
            "fraud_score": "double",
            "risk_level": "string",
            "kyc_status": "string",
            "sanctions_match": "boolean",
            "aml_flag": "boolean",
            "evaluated_at": "long"
        }
        """
        parsed_df = df.select(
            from_json(col("value").cast("string"), schema_of_json(schema_str)).alias("data")
        ).select("data.*")
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
