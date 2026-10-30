"""D3 and D4: identity collisions and copies of the identity rule.

D4: the drifted rule truncated SHA-256 to 8 hex characters, so two different
customers can mint the same IRI. D3: the rule was copied into three files
that each tested only themselves, so the copies could drift apart unnoticed.
"""

import math
import re
from pathlib import Path

from _loader import BEFORE_ROOT, REPO_ROOT, SEMANTIC_DIR, build_graphs  # noqa: F401
from _loader import load_module

PAIR = [
    ("customer111830@example.com", "KYC0111830"),
    ("customer130865@example.com", "KYC0130865"),
]


def odds(n, bits):
    """Birthday-bound probability of at least one collision among n IRIs."""
    space = 2 ** bits
    return -math.expm1(-n * (n - 1) / (2 * space))


def print_odds():
    print("Birthday-bound collision odds")
    print(f"  {'customers':>10}  {'32-bit (8 hex, before)':>24}  {'256-bit (64 hex, after)':>24}")
    for n in (10_000, 77_000, 100_000, 1_000_000):
        print(f"  {n:>10,}  {odds(n, 32) * 100:>23.2f}%  {odds(n, 256):>24.3e}")


def count_identity_copies():
    """Count top-level semantic modules that compute SHA-256 for customer IRIs."""
    def hashing_modules(root):
        found = []
        for path in root.glob("domains/*/src/main/python/semantic/*.py"):
            if "sha256" in path.read_text():
                found.append(path)
        return found

    before_files = hashing_modules(BEFORE_ROOT)
    after_files = hashing_modules(REPO_ROOT) + [
        p for p in (REPO_ROOT / "shared" / "semantic").glob("*.py") if "sha256" in p.read_text()
    ]
    print("\nD3 copies of the identity rule")
    print(f"  before: {len(before_files)} semantic modules compute SHA-256 for customer IRIs")
    print(f"  after:  {len(after_files)} module(s) compute it: "
          + ", ".join(str(p.relative_to(REPO_ROOT)) for p in after_files))


if __name__ == "__main__":
    before_iris = {}
    before_resolver = load_module("before", "accounts", "iri_resolver").IriResolver()
    after_resolver = load_module("after", "accounts", "iri_resolver").IriResolver()

    print("D4 identity collision: the same two customers, minted by each rule\n")
    for email, kyc in PAIR:
        before_iris[(email, kyc)] = before_resolver.mint_customer_iri(email, kyc)
        print(f"  before  {email} / {kyc} -> {before_iris[(email, kyc)]}")
    print()
    for email, kyc in PAIR:
        print(f"  after   {email} / {kyc} -> {after_resolver.mint_customer_iri(email, kyc)}")
    before_values = list(before_iris.values())
    after_values = [after_resolver.mint_customer_iri(e, k) for e, k in PAIR]
    print(f"\n  before collides: {before_values[0] == before_values[1]}")
    print(f"  after collides:  {after_values[0] == after_values[1]}\n")

    print_odds()
    count_identity_copies()
