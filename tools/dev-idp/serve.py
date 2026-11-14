"""Dev identity provider: serves the JWKS and mints RS256 tokens for named users in users.yaml.

Development only. Run from the repo root:  python tools/dev-idp/serve.py
Keys are created first by tools/dev-idp/make_keys.py and are never committed.
"""

import json
import sys
from pathlib import Path

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from shared.identity.devtools import mint_token  # noqa: E402

KEYS = Path(__file__).resolve().parent / "keys"
ISSUER = "http://dev-idp:8090"
AUDIENCE = "data-mesh"

app = FastAPI(title="Dev IdP (development only)")


def _load():
    private_pem = (KEYS / "idp-private.pem").read_bytes()
    jwks = json.loads((KEYS / "jwks.json").read_text())
    users = yaml.safe_load((Path(__file__).parent / "users.yaml").read_text())["users"]
    return private_pem, jwks, users


@app.get("/.well-known/jwks.json")
def jwks():
    return _load()[1]


@app.post("/token/{user}")
def token(user: str):
    private_pem, jwks_doc, users = _load()
    if user not in users:
        raise HTTPException(status_code=404, detail="unknown dev user")
    spec = users[user]
    kid = jwks_doc["keys"][0]["kid"]
    return {"access_token": mint_token(
        private_pem, kid,
        issuer=ISSUER, audience=AUDIENCE,
        subject=spec["subject"], roles=spec["roles"], owns=spec["owns"],
    ), "token_type": "Bearer"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090)
