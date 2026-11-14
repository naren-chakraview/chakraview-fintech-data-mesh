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
