SHELL := /bin/sh

PYTHON ?= python
NPM ?= npm
COMPOSE ?= docker compose

.PHONY: env up down logs test test-backend test-frontend lint typecheck fmt scan certs clean smoke

env:
	@test -f .env || cp .env.example .env
	@echo "Using .env (copy of .env.example when absent)"

up: env
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=200

test: test-backend test-frontend

test-backend:
	cd backend && $(PYTHON) -m pytest

test-frontend:
	cd frontend && $(NPM) run test

lint:
	cd backend && $(PYTHON) -m ruff check app tests
	cd backend && $(PYTHON) -m ruff format --check app tests
	cd frontend && $(NPM) run lint
	cd frontend && $(NPM) run format:check

typecheck:
	cd backend && $(PYTHON) -m mypy app
	cd frontend && $(NPM) run typecheck

fmt:
	cd backend && $(PYTHON) -m ruff format app tests
	cd backend && $(PYTHON) -m ruff check --fix app tests
	cd frontend && $(NPM) run format

scan:
	cd backend && $(PYTHON) -m bandit -c pyproject.toml -r app -lll
	cd backend && $(PYTHON) -m pip_audit -r requirements.txt
	@if command -v trivy >/dev/null 2>&1; then \
		trivy fs --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed --skip-dirs backend/.venv --skip-dirs frontend/node_modules .; \
	else \
		echo "trivy is not installed locally; the security CI workflow runs the filesystem and image scans."; \
	fi

certs:
	@if command -v bash >/dev/null 2>&1; then \
		bash infra/scripts/generate-certs.sh; \
	elif command -v pwsh >/dev/null 2>&1; then \
		pwsh -NoProfile -File infra/scripts/generate-certs.ps1; \
	else \
		echo "Provide bash or PowerShell with OpenSSL to generate local certificates."; exit 1; \
	fi

smoke:
	@curl -kfsS https://localhost/api/v1/healthz
	@curl -kfsS https://localhost/api/v1/readyz
	@curl -kfsS https://localhost/metrics >/dev/null

clean:
	$(COMPOSE) down -v --remove-orphans
	rm -rf backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache backend/.coverage backend/htmlcov
	rm -rf frontend/dist frontend/coverage
	find backend/app backend/tests -type d -name __pycache__ -prune -exec rm -rf {} +
