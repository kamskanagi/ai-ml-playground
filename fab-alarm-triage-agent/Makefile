.DEFAULT_GOAL := help
COMPOSE := docker compose
PY := ./.venv/bin/python
PIP := ./.venv/bin/pip

.PHONY: help venv install up down logs seed test lint fmt shell psql clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

venv: ## Create the local virtualenv
	python3 -m venv .venv && $(PIP) install --upgrade pip

install: venv ## Install backend deps (editable, with dev extras)
	$(PIP) install -e "backend[dev]"

up: ## Start the stack
	$(COMPOSE) up -d --build

down: ## Stop the stack
	$(COMPOSE) down

logs: ## Tail backend logs
	$(COMPOSE) logs -f backend

seed: ## Load SECOM and generate the mock MES (inside the container)
	$(COMPOSE) exec backend python -m app.seed.seed

LOCAL_ENV := POSTGRES_HOST=localhost POSTGRES_PORT=5433 PYTHONPATH=backend

seed-local: ## Seed from the host venv against the compose Postgres
	$(LOCAL_ENV) $(PY) -m app.seed.seed

dev: ## Run the API from the host venv with reload
	$(LOCAL_ENV) $(PY) -m uvicorn app.main:app --reload --port 8000

test: ## Run backend tests
	cd backend && ../.venv/bin/python -m pytest -q

lint: ## Lint and type-check
	./.venv/bin/ruff check backend
	./.venv/bin/ruff format --check backend

fmt: ## Auto-format
	./.venv/bin/ruff format backend
	./.venv/bin/ruff check --fix backend

psql: ## Open a psql shell
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-fab} -d $${POSTGRES_DB:-fab_mes}

clean: ## Remove the stack and its volumes
	$(COMPOSE) down -v
