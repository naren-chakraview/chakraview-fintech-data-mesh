"""Run the boundary with its two listeners, in one process so they share the app's state.

- mTLS on :8443 (0.0.0.0): for callers that present a certificate from the internal CA, which is the nginx gateway.
  Delegated (X-ZT-*) headers are never read here.
- loopback on 127.0.0.1:$LOOPBACK_PORT (plain HTTP): for the boundary's own delegation sidecar only. Nothing outside
  this network namespace can reach it, and it is the only listener that accepts forwarded delegated calls.

Run: python -m boundary.serve   (with platform/ on the path, as the Dockerfile sets it)
"""

import asyncio
import os

import uvicorn

from boundary.main import get_app

TLS = {
    "ssl_keyfile": "/certs/server.key",
    "ssl_certfile": "/certs/server.pem",
    "ssl_ca_certs": "/certs/ca.pem",
    "ssl_cert_reqs": 2,  # CERT_REQUIRED: no certificate, no connection
}


async def serve() -> None:
    app = get_app()  # one app, shared by both listeners
    mtls = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8443, **TLS))
    loopback = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=int(os.getenv("LOOPBACK_PORT", "8080")),
    ))
    await asyncio.gather(mtls.serve(), loopback.serve())


if __name__ == "__main__":
    asyncio.run(serve())
