.PHONY: help install test lint format clean docker-up docker-down

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

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v --cov=domains --cov=platform --cov=shared

test-unit:
	pytest tests/unit -v

test-integration:
	pytest tests/integration -v

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
