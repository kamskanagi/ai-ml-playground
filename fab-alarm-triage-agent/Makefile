.DEFAULT_GOAL := help
COMPOSE := docker compose
PY := ./.venv/bin/python
PIP := ./.venv/bin/pip

.PHONY: help venv install up down logs seed test lint fmt shell psql clean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

venv: ## Create the local virtualenv
	python3 -m venv .venv && $(PIP) install --upgrade pip

install: venv ## Install backend and MCP deps (editable, with dev extras)
	$(PIP) install -e "backend[dev]" -e "mcp_server[dev]"

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

mcp-local: ## Run the MCP server from the host venv (needs the API on :8000)
	BACKEND_URL=http://localhost:8000 $(PY) mcp_server/server.py

ui: ## Run the dashboard dev server (proxies /api to :8000)
	cd frontend && npx ng serve

test: ## Run all tests
	cd backend && ../.venv/bin/python -m pytest -q
	cd mcp_server && ../.venv/bin/python -m pytest -q
	cd frontend && npx ng test --watch=false

lint: ## Lint and type-check
	./.venv/bin/ruff check backend mcp_server
	./.venv/bin/ruff format --check backend mcp_server
	cd frontend && npx tsc --noEmit -p tsconfig.app.json

fmt: ## Auto-format
	./.venv/bin/ruff format backend mcp_server
	./.venv/bin/ruff check --fix backend mcp_server

psql: ## Open a psql shell
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-fab} -d $${POSTGRES_DB:-fab_mes}

clean: ## Remove the stack and its volumes
	$(COMPOSE) down -v
