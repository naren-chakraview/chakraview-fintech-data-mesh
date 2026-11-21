.PHONY: help install test lint format clean docker-up docker-down policy-test trust-keys trust-test trust-demo trust-smoke agent-test agent-demo agent-up agent-grants agent-run agent-check

help:
	@echo "Available commands:"
	@echo "  make install        Install dependencies"
	@echo "  make test           Run all tests"
	@echo "  make test-unit      Run unit tests only"
	@echo "  make test-integration Run integration tests only"
	@echo "  make lint           Run linting checks"
	@echo "  make format         Format code with black"
	@echo "  make docker-up      Start Docker Compose services"
	@echo "  make docker-down    Stop Docker Compose services"
	@echo "  make clean          Remove build artifacts"
	@echo "  make trust-keys     Create dev IdP/CA/signing keys and signed fixture attestations (gitignored)"
	@echo "  make trust-test     Run the trust unit and integration tests (needs the opa binary)"
	@echo "  make trust-demo     Run the before/after trust demos (needs Docker for the side-door demo)"
	@echo "  make trust-smoke    Smoke-test the running stack through the mTLS gateway (run docker compose up first)"
	@echo "  make agent-test     Delegation and governed-write tests (needs the opa binary; run make policy-test too)"
	@echo "  make agent-demo     Before and after demos for agents as governed participants (needs the opa binary)"
	@echo "  make agent-up       Start the compose stack for the agent path (needs make trust-keys and a .env)"
	@echo "  make agent-grants   DEV ONLY: create the agent's read and propose grants (the approval stand-in)"
	@echo "  make agent-run      Run the scripted agent once through the two sidecars, then show its output"
	@echo "  make agent-check    LIVE: a token bound to the agent's certificate is refused for another workload's"

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v --cov=domains --cov=platform --cov=shared

test-unit:
	pytest tests/unit -v

test-integration:
	pytest tests/integration -v

test-semantic:
	for t in domains/accounts/src/main/python/semantic domains/risk-compliance/src/main/python/semantic domains/transactions/src/main/python/semantic domains/accounts/tests/integration/test_accounts_rdf_e2e.py domains/risk-compliance/tests/test_integration_e2e.py domains/transactions/tests/test_integration_e2e.py tests/contract; do python3 -m pytest -q $$t || exit 1; done

semantic-drift-demo:
	for d in examples/semantic-drift/demo_*.py; do python3 $$d || exit 1; done

policy-test:
	opa check --strict platform/governance/opa-policies domains/*/policy
	opa test platform/governance/opa-policies domains/*/policy -v

trust-keys:
	python3 tools/dev-idp/make_keys.py
	python3 tools/dev-ca/make_ca.py
	python3 tools/dev-keys/make_signing_key.py
	python3 tools/dev-keys/publish_attestations.py
	python3 tools/dev-gateway/make_config.py

trust-test:
	python3 -m pytest tests/unit tests/trust -q

trust-demo:
	for d in examples/trust-gaps/demo_*.py; do python3 $$d || exit 1; done

trust-smoke:
	bash tools/smoke/gateway_smoke.sh

agent-test:
	python3 -m pytest tests/trust/test_delegation.py tests/trust/test_proposals.py -q

agent-demo:
	for d in examples/agent-gaps/demo_*.py; do python3 $$d || exit 1; done

agent-up:
	docker compose up -d --build postgres opa dev-idp elasticsearch boundary boundary-zt agent-zt

agent-grants:
	docker compose exec -T boundary python - < tools/dev-gateway/grant_agent.py

agent-run:
	docker compose up -d --force-recreate --no-deps agent agent-zt
	docker wait chakra-agent
	docker logs chakra-agent

lint:
	flake8 domains platform shared
	mypy domains platform shared

format:
	black domains platform shared tests

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache/ build/ dist/ *.egg-info/

agent-check:
	docker compose -f docker-compose.yml -f tools/dev-gateway/check.override.yml up -d --force-recreate --no-deps agent agent-zt
	sleep 5
	docker exec -i chakra-agent python - < tools/dev-gateway/check_binding.py; rc=$$?; \
	docker compose up -d --force-recreate --no-deps agent agent-zt >/dev/null 2>&1; exit $$rc

