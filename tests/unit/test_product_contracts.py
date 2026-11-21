"""Contract CI (addendum W1): every column a readable product holds is classified, and every product that takes direct
writes declares a complete write contract. A column with no classification would be treated as personal at write
time, so an unclassified column is a contract failure here, not a surprise at run time."""

import json
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "platform"))

from boundary import writes  # noqa: E402
from shared.governance.products import column_classifications, load_products  # noqa: E402

PRODUCTS = load_products(REPO / "domains")
FIXTURES = sorted((REPO / "platform/boundary/fixtures").glob("*.json"))


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.name)
def test_every_column_of_a_readable_product_is_classified(fixture):
    product_id = fixture.name.removesuffix(".json")
    product = PRODUCTS.get(product_id)
    assert product is not None, f"{fixture.name} has no data product contract"
    classified = column_classifications(product)
    unclassified = [c for c in json.loads(fixture.read_text())["columns"] if c not in classified]
    assert unclassified == [], f"{product_id}: unclassified columns {unclassified}"


@pytest.mark.parametrize("product_id", sorted(writes.SHAPE_CLASS))
def test_a_direct_write_product_declares_a_complete_contract(product_id):
    contract = writes.contract(PRODUCTS[product_id])
    assert contract["kind"] in {"captured", "derived"}
    assert contract["key"] in column_classifications(PRODUCTS[product_id])
    assert contract["mode"] in {"append", "upsert"}


def test_the_contract_yaml_names_the_kind_on_every_write_product():
    for path in (REPO / "domains").glob("*/data-products/*.yaml"):
        product = yaml.safe_load(path.read_text())
        pid = f"{product['domain']}.{product['name']}"
        if pid in writes.SHAPE_CLASS or pid == "risk-compliance.risk-review-notes":
            assert product.get("write_kind") in {"captured", "derived"}, pid
