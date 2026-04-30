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
