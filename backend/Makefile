.PHONY: install venv test lint typecheck fmt scan run worker migrate seed seed-demo

PYTHON ?= python

venv:
	$(PYTHON) -m venv .venv

install:
	$(PYTHON) -m pip install -r requirements-dev.txt

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check app tests
	$(PYTHON) -m ruff format --check app tests

typecheck:
	$(PYTHON) -m mypy app

fmt:
	$(PYTHON) -m ruff format app tests
	$(PYTHON) -m ruff check --fix app tests

scan:
	$(PYTHON) -m bandit -c pyproject.toml -r app
	$(PYTHON) -m pip_audit -r requirements.txt

run:
	$(PYTHON) -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

worker:
	$(PYTHON) -m celery -A app.workers.celery_app:celery_app worker --loglevel=INFO --pool=solo

migrate:
	$(PYTHON) -m alembic upgrade head

seed:
	$(PYTHON) -m app.cli.seed

seed-demo:
	$(PYTHON) -m app.cli.seed --demo
