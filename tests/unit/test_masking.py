import hashlib

import pytest

from shared.compliance.masking import ColumnMaskingPolicy, DataMasker


def test_unclassified_column_is_masked():
    policy = ColumnMaskingPolicy()
    assert policy.should_mask("transactions.raw_transactions", "unknown_col") is True


def test_public_column_is_not_masked():
    policy = ColumnMaskingPolicy()
    policy.add_policy("t", "merchant_id", "public")
    assert policy.should_mask("t", "merchant_id") is False


@pytest.mark.parametrize("classification", ["PUBLIC", "Public", "", "pii"])
def test_non_exact_public_is_masked(classification):
    policy = ColumnMaskingPolicy()
    policy.add_policy("t", "c", classification)
    assert policy.should_mask("t", "c") is True


def test_full_hash_is_sha256_hex():
    assert DataMasker.full_hash("John Doe") == hashlib.sha256(b"John Doe").hexdigest()


def test_apply_known_strategy():
    assert DataMasker.apply("no_mask", "abc") == "abc"


def test_apply_unknown_strategy_raises():
    with pytest.raises(ValueError):
        DataMasker.apply("show_everything", "4111111111111111")
