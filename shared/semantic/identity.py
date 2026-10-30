"""Customer IRI minting. Owned by the Accounts domain.

This is the only place in the repo that implements the customer identity rule.
Every producer and resolver imports it; none may reimplement it.

Rule:
    IRI = {base_url}/customer# + HMAC-SHA256(key, normalize(email) + "|" + normalize(kyc_id))
    normalize(x) = str(x).lower().strip()
    The digest is the full 64-character lowercase hex string.

The key is read from the FINTECH_IRI_KEY environment variable. There is no
default: if the variable is unset or empty, minting raises IriKeyMissingError.
Every producer must receive the same key. Rotating the key re-mints every
customer IRI; see docs/case-study/fintech-semantic-integration/semantic-core-migration.md.

Golden vectors that pin this rule live in semantics/core/identity-vectors.json.
"""

import hashlib
import hmac
import os
from typing import Optional

KEY_ENV_VAR = "FINTECH_IRI_KEY"
DEFAULT_BASE_URL = "https://chakracommerce.com"


class IriKeyMissingError(RuntimeError):
    """Raised when FINTECH_IRI_KEY is not available for minting."""


def normalize(text: str) -> str:
    """Normalize an identifier before minting (lowercase and trim)."""
    return str(text).lower().strip()


def _key_bytes(key: Optional[str]) -> bytes:
    value = key if key is not None else os.environ.get(KEY_ENV_VAR, "")
    if not value:
        raise IriKeyMissingError(
            f"{KEY_ENV_VAR} is not set; customer IRIs cannot be minted without it"
        )
    return value.encode("utf-8")


def mint_customer_iri(
    email: str,
    kyc_id: str,
    key: Optional[str] = None,
    base_url: str = DEFAULT_BASE_URL,
) -> str:
    """Mint the stable Customer IRI for an email and KYC ID.

    Args:
        email: Customer email (normalized before hashing).
        kyc_id: Customer KYC identifier (normalized before hashing).
        key: Explicit key for tests. Production code leaves this as None so
            the key comes from FINTECH_IRI_KEY.
        base_url: Base URL for the IRI namespace.

    Returns:
        IRI of the form {base_url}/customer#<64 lowercase hex characters>.

    Raises:
        IriKeyMissingError: If no key is supplied and FINTECH_IRI_KEY is unset.
    """
    message = f"{normalize(email)}|{normalize(kyc_id)}".encode("utf-8")
    digest = hmac.new(_key_bytes(key), message, hashlib.sha256).hexdigest()
    return f"{base_url}/customer#{digest}"
