from typing import List, Dict, Optional, Any
from pyiceberg.types import (
    NestedField,
    IcebergType,
)
from pyiceberg.partitioning import PartitionSpec, PartitionField
from pyiceberg.schema import Schema


class IcebergSchemaBuilder:
    """Helper to build Iceberg schemas with version tracking"""

    def __init__(self, table_name: str, version: str = "1.0"):
        self.table_name = table_name
        self.version = version
        self.fields: List[NestedField] = []
        self.partition_fields: List[tuple] = []
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
