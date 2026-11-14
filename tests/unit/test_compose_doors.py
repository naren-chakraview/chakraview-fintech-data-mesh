"""The doors are closed in the files themselves: no published storage ports, no default credentials, no update endpoint."""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]

INTERNAL_SERVICES = {"minio", "iceberg-catalog", "postgres", "opa", "elasticsearch", "risk-compliance-fuseki", "boundary", "discovery"}


def compose():
    return yaml.safe_load((REPO / "docker-compose.yml").read_text())


def test_storage_and_services_publish_no_host_ports():
    services = compose()["services"]
    published = {name for name in INTERNAL_SERVICES & set(services) if services[name].get("ports")}

    assert published == set()


def test_only_the_gateway_and_dev_idp_have_trust_ports():
    services = compose()["services"]
    trust = {"gateway", "dev-idp", "boundary", "discovery", "opa", "postgres", "minio", "iceberg-catalog",
             "elasticsearch", "risk-compliance-fuseki"}
    published = {name for name in trust if services.get(name, {}).get("ports")}

    assert published == {"gateway", "dev-idp"}


def test_internal_network_is_internal():
    assert compose()["networks"]["internal"]["internal"] is True


def test_no_default_credentials_in_compose():
    text = (REPO / "docker-compose.yml").read_text()

    assert "minioadmin" not in text
    assert not re.search(r"PASSWORD:\s*\$\{[A-Z_]+:-", text)


def test_no_default_credentials_in_domain_composes():
    for path in (REPO / "domains").glob("*/docker-compose.yml"):
        text = path.read_text()
        assert not re.search(r"PASSWORD:\s*\$\{[A-Z_]+:-", text), path
        assert "minioadmin" not in text, path


def test_domain_composes_publish_no_ports():
    for path in (REPO / "domains").glob("*/docker-compose.yml"):
        assert "ports:" not in path.read_text(), path


def test_opa_is_pinned_and_not_published():
    opa = compose()["services"]["opa"]

    assert opa["image"] == "openpolicyagent/opa:1.0.0"
    assert "ports" not in opa


def test_fuseki_configs_have_no_update_or_read_write_store():
    for path in (REPO / "domains").glob("*/config/fuseki-config.ttl"):
        text = path.read_text()
        assert "fuseki:update" not in text, path
        assert "fuseki:gsp-rw" not in text, path
        assert "fuseki:query" in text, path


def test_gateway_forwards_only_to_the_services_and_overwrites_the_cert_header():
    conf = (REPO / "platform/boundary/gateway/nginx.conf").read_text()

    assert "ssl_verify_client on" in conf
    assert conf.count("proxy_set_header X-Client-Cert $ssl_client_escaped_cert") == 2


# R2 and R4: the services accept only the gateway's certificate, and no service holds a CA private key.
def _command(service):
    cmd = compose()["services"][service]["command"]
    return cmd if isinstance(cmd, list) else cmd.split()


def test_boundary_and_discovery_require_a_client_certificate_from_the_internal_ca():
    for service in ("boundary", "discovery"):
        cmd = _command(service)
        assert "--ssl-cert-reqs" in cmd and cmd[cmd.index("--ssl-cert-reqs") + 1] == "2", service
        assert "--ssl-ca-certs" in cmd and cmd[cmd.index("--ssl-ca-certs") + 1] == "/certs/ca.pem", service
        assert "--ssl-certfile" in cmd, service


def test_no_service_mounts_a_ca_private_key():
    for name, service in compose()["services"].items():
        for volume in service.get("volumes", []):
            source = str(volume).split(":")[0]
            assert source not in ("./tools/dev-ca/out", "./tools/dev-ca/out/ca", "./tools/dev-ca/out/internal"), name
            assert not str(volume).endswith("ca.key"), name


def test_fuseki_is_reachable_only_from_the_boundary_network():
    services = compose()["services"]
    assert services["risk-compliance-fuseki"]["networks"] == ["fuseki-risk"]
    assert "fuseki-risk" in services["boundary"]["networks"]
    assert "fuseki-risk" not in services["discovery"]["networks"]
    assert compose()["networks"]["fuseki-risk"]["internal"] is True


def test_gateway_verifies_the_services_and_presents_its_own_certificate():
    conf = (REPO / "platform/boundary/gateway/nginx.conf").read_text()

    assert "proxy_ssl_verify on" in conf
    assert re.search(r"proxy_ssl_certificate\s+/certs/client\.pem;", conf)
    assert re.search(r"proxy_ssl_trusted_certificate\s+/certs/internal-ca\.pem;", conf)
