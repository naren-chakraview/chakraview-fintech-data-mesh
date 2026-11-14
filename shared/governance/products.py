"""Data product definitions from domains/*/data-products/*.yaml."""

from pathlib import Path
from typing import Dict

import yaml

# Lowest to highest sensitivity; a product is classified by its most sensitive column.
CLASSIFICATION_ORDER = ["public", "sensitive", "confidential", "pii", "restricted"]


def product_classification(product: dict) -> str:
    """Highest column classification; restricted when there are no columns or a value is unknown."""
    columns = (product.get("access_policy") or {}).get("columns") or []
    levels = [column.get("classification") for column in columns]
    if not levels or any(level not in CLASSIFICATION_ORDER for level in levels):
        return "restricted"
    return max(levels, key=CLASSIFICATION_ORDER.index)


def column_classifications(product: dict) -> Dict[str, str]:
    """Column name to classification. Columns with an unknown value are left out, so they are masked."""
    columns = (product.get("access_policy") or {}).get("columns") or []
    return {
        column["name"]: column["classification"]
        for column in columns
        if column.get("classification") in CLASSIFICATION_ORDER
    }


def product_policy_input(product: dict) -> dict:
    """The product fields the policy sees. approval_required defaults to True (fail closed)."""
    access = product.get("access_policy") or {}
    return {
        "id": f"{product['domain']}.{product['name']}",
        "domain": product["domain"],
        "name": product["name"],
        "owner": product.get("owner", ""),
        "classification": product_classification(product),
        "approval_required": bool(access.get("approval_required", True)),
        "approval_sla_hours": int(access.get("approval_sla_hours", 4)),
        "require_provenance": bool(access.get("require_provenance", False)),
    }


def load_products(domains_dir: Path) -> Dict[str, dict]:
    """Load every data product, keyed by "<domain>.<name>"."""
    products: Dict[str, dict] = {}
    for yaml_file in sorted(Path(domains_dir).glob("*/data-products/*.yaml")):
        with open(yaml_file, "r") as handle:
            product = yaml.safe_load(handle)
        products[f"{product['domain']}.{product['name']}"] = product
    return products
