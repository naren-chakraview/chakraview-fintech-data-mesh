"""G4: open doors below the policy. Before, anyone can read customer emails from Fuseki, and writes depend on
one shared admin password.

Needs Docker (the demo starts Fuseki 5.1.0 containers on a scratch volume).

What the stock Fuseki 5.1 image actually does (checked, see shiro.ini in the image):
  - /*/update and /*/data are protected by one shared admin password (Shiro authcBasic).
  - SPARQL queries are anonymous (/**=anon).
So the brief's "update with no auth" does not hold for this image. Queries are the open door.

Before: an anonymous query returns customer emails. An anonymous write is refused (401), but anyone with
        the shared admin password can write.
After:  the live config has no update endpoint and no read-write graph store. The same write gets 404,
        even with the admin password. Through the boundary, an authorized query returns masked emails and
        an INSERT is refused (400).
"""

import shutil
import subprocess
from datetime import timedelta
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _loader import BEFORE, line, section  # noqa: E402
from shared.testing.harness import REPO, WORKLOADS, open_stack  # noqa: E402

IMAGE = "stain/jena-fuseki:5.1.0"
BUSYBOX = "busybox:1.36"
LIVE_CONFIG = REPO / "domains/risk-compliance/config/fuseki-config.ttl"
BEFORE_CONFIG = BEFORE / "config/fuseki-config.ttl"
PRODUCT = "risk-compliance.risk-scores"
SUBJECT = "risk.analyst@chakra.fintech"
PURPOSE = "fraud-review"
FINTECH = "http://chakracommerce.com/fintech#"
CUSTOMERS = [("urn:cust:1", "john@acme.com", "John Doe"), ("urn:cust:2", "jane@acme.com", "Jane Roe")]


def docker(*args: str, check: bool = True) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args[:2])} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def docker_available() -> bool:
    return shutil.which("docker") is not None and subprocess.run(
        ["docker", "info"], capture_output=True).returncode == 0


def runnable_before_config(scratch: Path) -> Path:
    """The frozen before config, with only the TDB2 vocabulary namespace corrected.

    The frozen file uses http://jena.apache.org/2016/09/TDB2#, which Fuseki 5.1 rejects, so it never starts.
    Only the namespace is changed here, in a scratch copy. The endpoints are exactly as frozen.
    """
    text = BEFORE_CONFIG.read_text().replace("http://jena.apache.org/2016/09/TDB2#", "http://jena.apache.org/2016/tdb#")
    target = scratch / "before-config.ttl"
    target.write_text(text)
    return target


ADMIN = ("admin", "demo-only")


def start_fuseki(name: str, volume: str, config: Path) -> str:
    docker("rm", "-f", name, check=False)
    docker("run", "-d", "--name", name, "-p", "127.0.0.1::3030",
           "-v", f"{volume}:/fuseki-base/databases", "-v", f"{config}:/fuseki/config.ttl:ro",
           "-e", f"ADMIN_PASSWORD={ADMIN[1]}", IMAGE,
           "/jena-fuseki/fuseki-server", "--conf", "/fuseki/config.ttl")
    port = docker("port", name, "3030").rsplit(":", 1)[-1]
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base}/risk_compliance/sparql", params={"query": "ASK {}"}, timeout=2).status_code == 200:
                return base
        except httpx.HTTPError:
            pass
        time.sleep(1)
    logs = docker("logs", name, check=False)
    raise RuntimeError(f"Fuseki did not start:\n{logs[-800:]}")


def seed_statements() -> str:
    lines = [f'<{s}> <{FINTECH}customerEmail> "{e}" ; <{FINTECH}customerName> "{n}" .' for s, e, n in CUSTOMERS]
    return "INSERT DATA {\n" + "\n".join(lines) + "\n}"


def before(scratch: Path, volume: str) -> None:
    base = start_fuseki("trust-demo-before", volume, runnable_before_config(scratch))
    endpoint = f"{base}/risk_compliance"
    anonymous = httpx.post(f"{endpoint}/update", content=seed_statements(),
                           headers={"Content-Type": "application/sparql-update"})
    print(f"anonymous INSERT DATA                       -> HTTP {anonymous.status_code}")
    admin = httpx.post(f"{endpoint}/update", content=seed_statements(), auth=ADMIN,
                       headers={"Content-Type": "application/sparql-update"})
    print(f"INSERT DATA with the shared admin password  -> HTTP {admin.status_code} (writes are open to it)")
    query = "SELECT ?email WHERE { ?c <%scustomerEmail> ?email }" % FINTECH
    rows = httpx.post(f"{endpoint}/sparql", data={"query": query},
                      headers={"Accept": "application/sparql-results+json"}).json()
    emails = [b["email"]["value"] for b in rows["results"]["bindings"]]
    print(f"anonymous SELECT emails                     -> {emails}")
    docker("rm", "-f", "trust-demo-before", check=False)


def after(scratch: Path, volume: str) -> None:
    base = start_fuseki("trust-demo-after", volume, LIVE_CONFIG)
    endpoint = f"{base}/risk_compliance"
    update = httpx.post(f"{endpoint}/update", content=seed_statements(), auth=ADMIN,
                        headers={"Content-Type": "application/sparql-update"})
    print(f"INSERT DATA with the admin password, live   -> HTTP {update.status_code} (no update endpoint)")

    with open_stack(fuseki_endpoints={"risk-compliance": f"{endpoint}/sparql"}) as stack:
        token = stack.token(SUBJECT, roles=["risk_analyst"])
        stack.grants.create(subject=SUBJECT, workload_spiffe_id=WORKLOADS["notebook"], product_id=PRODUCT,
                            columns=["customerEmail", "customerName"], purpose=PURPOSE,
                            expires_at=stack.now + timedelta(hours=1))
        client = stack.boundary()
        headers = stack.headers(token)
        sparql = (f"PREFIX f: <{FINTECH}>\nSELECT ?email ?name WHERE {{ "
                  f"?c f:customerEmail ?email ; f:customerName ?name }}")
        r = client.post(f"/products/{PRODUCT}/sparql?purpose={PURPOSE}", json={"query": sparql}, headers=headers)
        bindings = r.json()["results"]["bindings"] if r.status_code == 200 else []
        print(f"authorized SELECT through the boundary      -> {r.status_code}")
        for b in bindings:
            print(f"   email={b['email']['value']}  name={b['name']['value']}")

        write = client.post(f"/products/{PRODUCT}/sparql?purpose={PURPOSE}",
                            json={"query": f"PREFIX f: <{FINTECH}>\nINSERT DATA {{ <urn:x> f:customerEmail \"a@b.c\" }}"},
                            headers=headers)
        print(f"INSERT through the boundary                 -> {write.status_code} {write.json()['detail']}")
    docker("rm", "-f", "trust-demo-after", check=False)


def main() -> int:
    if not docker_available():
        print("Docker is not available; the side-door demo needs it to run Fuseki.")
        return 2
    line("G4 side door")
    scratch = Path(tempfile.mkdtemp(prefix="trust-demo-"))
    volume = f"trust-demo-{uuid.uuid4().hex[:8]}"
    try:
        docker("volume", "create", volume)
        docker("run", "--rm", "-v", f"{volume}:/fuseki-base/databases", BUSYBOX,
               "sh", "-c", "mkdir -p /fuseki-base/databases/risk_compliance && chown -R 100:101 /fuseki-base/databases")
        section("BEFORE (frozen config, runnable copy)")
        before(scratch, volume)
        section("AFTER (live config)")
        after(scratch, volume)
    finally:
        docker("rm", "-f", "trust-demo-before", "trust-demo-after", check=False)
        docker("volume", "rm", "-f", volume, check=False)
        shutil.rmtree(scratch, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
