.DEFAULT_GOAL := help
COMPOSE := docker compose
PY := ./.venv/bin/python
PIP := ./.venv/bin/pip

.PHONY: help venv install up down logs seed test lint fmt shell psql clean

help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

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

eval: ## Score the agent on the held-out alarms (needs GROQ_API_KEY)
	$(LOCAL_ENV) $(PY) -m app.eval.run --predictor agent

eval-baseline: ## Score the lookup-table baseline — the bar the agent must clear
	$(LOCAL_ENV) $(PY) -m app.eval.run --predictor baseline-majority-by-code
	$(LOCAL_ENV) $(PY) -m app.eval.run --predictor baseline-always-escalate

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

# --- kubernetes -----------------------------------------------------------

KIND_CLUSTER := fab-triage
K8S_NS := fab-triage

kind-up: ## Create the local kind cluster with an ingress controller
	kind create cluster --config k8s/kind-config.yaml --wait 180s
	kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.3/deploy/static/provider/kind/deploy.yaml
	kubectl -n ingress-nginx wait --for=condition=ready pod \
		--selector=app.kubernetes.io/component=controller --timeout=180s

kind-down: ## Delete the kind cluster
	kind delete cluster --name $(KIND_CLUSTER)

images: ## Build and load images into kind
	docker build -t fab-triage/backend:dev backend
	docker build -t fab-triage/mcp:dev mcp_server
	docker build -t fab-triage/frontend:dev frontend
	kind load docker-image --name $(KIND_CLUSTER) \
		fab-triage/backend:dev fab-triage/mcp:dev fab-triage/frontend:dev

k8s-deploy: images ## Deploy to the kind cluster
	kubectl apply -k k8s/overlays/dev
	kubectl -n $(K8S_NS) rollout status statefulset/postgres --timeout=180s
	kubectl -n $(K8S_NS) rollout status deployment/backend --timeout=180s
	kubectl -n $(K8S_NS) rollout status deployment/mcp --timeout=120s
	kubectl -n $(K8S_NS) rollout status deployment/frontend --timeout=120s

k8s-seed: ## Seed the in-cluster database
	kubectl -n $(K8S_NS) exec deploy/backend -- python -m app.seed.seed

k8s-status: ## What is running
	kubectl -n $(K8S_NS) get pods,svc,ingress

k8s-logs: ## Tail backend logs in the cluster
	kubectl -n $(K8S_NS) logs -l app=backend --tail=100 -f

smoke: ## Check the deployed stack answers
	kubectl -n $(K8S_NS) exec deploy/backend -- \
		python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/ready').read().decode())"
	curl -fsS http://localhost:8081/api/alarms?limit=3 | head -c 200; echo

psql: ## Open a psql shell
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-fab} -d $${POSTGRES_DB:-fab_mes}

clean: ## Remove the stack and its volumes
	$(COMPOSE) down -v
