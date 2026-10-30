# Root conftest: its presence puts the repo root on sys.path so tests can import shared/, platform/, domains/.
import os

# Test-only FINTECH_IRI_KEY so customer IRIs can be minted in tests. The value is public: never use it outside tests.
os.environ.setdefault("FINTECH_IRI_KEY", "test-only-iri-key-do-not-use-in-production")
