# Fab Equipment Alarm Triage Copilot

A tool alarm fires in a semiconductor fab. An agent investigates it over MCP — sensor history,
equipment state, recent recipe changes, past incidents — drafts a root-cause hypothesis and a
recommended disposition with cited evidence, then **stops and waits** for a process engineer to
approve, edit or reject it.

The pause is a real durable interrupt: graph state is checkpointed to Postgres, so a run waiting
for review survives the backend process being killed and resumes on whichever replica receives
the decision.

Sensor data is the [UCI SECOM dataset](https://archive.ics.uci.edu/dataset/179/secom) — 1,567
real process runs, 590 sensors, 104 yield failures. The factory around it is simulated.

```
Angular  ──HTTP──▶  FastAPI  ──▶  Postgres
                       │            ▲
                       │ (agent)    │ MES tables + LangGraph checkpoints
                       ▼            │
                  MCP client ──▶ MCP server ──HTTP──▶ FastAPI /api
```

## Quick start

```bash
make install        # venv + backend and MCP deps
make up             # postgres, backend, mcp, frontend
make seed           # load SECOM and generate the mock MES
open http://localhost:4200
```

Triage needs a model. Copy `.env.example` to `.env` and set `GROQ_API_KEY`; without one the
dashboard and API work fully, but "Run triage" cannot reach a model.

## Secrets

`.env` and every variant (`.env.local`, `.env.production`, …) are gitignored, along with `*.pem`,
`*.key` and `kubeconfig`. Only `.env.example` is tracked, and it holds variable names with empty
values — never a real key.

In Kubernetes, `GROQ_API_KEY` is empty in `k8s/base/kustomization.yaml` by design. Supply it at
deploy time rather than committing it:

```bash
kubectl -n fab-triage create secret generic fab-secrets   --from-literal=POSTGRES_PASSWORD='...'   --from-literal=GROQ_API_KEY='...'   --dry-run=client -o yaml | kubectl apply -f -
```

CI enforces both rules on every build: it fails if any `.env` file becomes tracked, or if a
credential-shaped string appears in a tracked file.

## Commands

```bash
make help           # every target
make test           # backend, MCP and frontend suites
make lint           # ruff + tsc
make eval-baseline  # score the baselines (no API key needed)
make eval           # score the agent on held-out alarms
make kind-up        # local Kubernetes cluster with ingress
make k8s-deploy     # build, load and deploy to it
make smoke          # check the deployed stack answers
```

Postgres is published on host port **5433**, not 5432, to avoid colliding with an existing local
instance. In-cluster and in-network callers still use 5432.

## How it is put together

| Piece | What it does |
|---|---|
| `backend/app/seed/` | Loads SECOM, names 16 sensors, plants labelled fault scenarios |
| `backend/app/services/` | The one MES data-access path, shared by the API and the agent |
| `backend/app/agent/` | The LangGraph triage graph and its durable checkpoint |
| `backend/app/eval/` | Scoring on held-out alarms, with baselines |
| `mcp_server/` | Eight read-only MCP tools over the REST API |
| `frontend/` | Angular review console |
| `k8s/` | Manifests, kustomize overlays, kind cluster config |

Three properties are deliberate and worth preserving:

- **Every MCP tool is read-only.** Recording a disposition is a graph node, not a tool, so the
  agent has no reachable path to approve its own recommendation.
- **Ground truth never leaves the database.** The `alarms` table carries the answers for the eval
  harness; no API response or MCP tool exposes them, and a test crawls every endpoint to prove it.
- **The interrupt node contains nothing but `interrupt()`.** On resume LangGraph replays from the
  checkpoint boundary, not the paused line, so a write there would run twice.

## Incident runbook

### Backend pods are in CrashLoopBackOff right after a first deploy

Expected, and self-healing. The backend creates its tables at startup, so it exits if Postgres
is not accepting connections yet, and Kubernetes restarts it until the database is up. On a
fresh cluster this is typically three or four restarts.

```bash
kubectl -n fab-triage get pods
kubectl -n fab-triage logs -l app=backend --tail=20 | grep -i "resolve host\|OperationalError"
```

`failed to resolve host 'postgres'` is the harmless version. Only investigate if the restart
count keeps climbing *after* `postgres-0` reports Ready — that points at credentials or the
ConfigMap rather than ordering.

### A triage run is stuck in `running`

The agent is still working, or it died mid-investigation. Runs do not time out on their own.

```bash
kubectl -n fab-triage logs -l app=backend --tail=200 | grep -i "triage\|groq\|mcp"
curl -s localhost:8081/api/agent-runs/<id>/trace | jq '.[-3:]'
```

The trace is written step by step as the run proceeds, so the last entry shows where it stopped.
Common causes: the MCP server is unreachable (see below), or Groq is rate-limiting. There is no
resume for a crashed run — start a new one. The alarm is untouched, because nothing is recorded
until `propose`.

### A run is stuck in `awaiting_review`

**This is not a fault.** It means the agent finished and is waiting for a human — which it will do
indefinitely, by design. Check the queue for a pending disposition and decide on it.

```bash
curl -s localhost:8081/api/agent-runs/<id> | jq '.status, .disposition.status'
```

If the pod restarted while it was waiting, the run is still resumable: state lives in Postgres,
not in the process.

### The MCP server is unreachable

The agent will still reach `awaiting_review` — tool failures come back as
`{"error": ...}` values rather than crashing the run — but the recommendation will be poorly
evidenced and confidence will be low.

```bash
kubectl -n fab-triage get pods -l app=mcp
kubectl -n fab-triage logs -l app=mcp --tail=50
kubectl -n fab-triage exec deploy/backend -- \
  python -c "import urllib.request;print(urllib.request.urlopen('http://mcp:9000/mcp').status)"
```

The MCP server depends on the backend, not the other way round, so restart it alone:

```bash
kubectl -n fab-triage rollout restart deployment/mcp
```

### Groq is rate-limiting or erroring

Proposals will come back as `escalate` at zero confidence with a `structured output fallback`
note on the run. That is the intended failure mode — an agent that cannot reason hands the alarm
to a human rather than waving the lot through.

```bash
kubectl -n fab-triage logs -l app=backend --tail=100 | grep -i "rate\|429\|groq"
curl -s localhost:8081/api/agent-runs/<id> | jq '.error'
```

No action is needed for correctness. If it persists, reduce load by lowering `MAX_TOOL_CALLS` in
the ConfigMap, or switch `GROQ_MODEL` to a smaller model.

### Checkpoint tables are growing

LangGraph writes a checkpoint per super-step to `checkpoints`, `checkpoint_blobs` and
`checkpoint_writes`. Completed runs never need theirs again.

```sql
SELECT pg_size_pretty(pg_total_relation_size('checkpoint_blobs'));

-- Safe to delete: threads whose run finished more than 30 days ago.
DELETE FROM checkpoints c
USING agent_runs r
WHERE c.thread_id = r.thread_id
  AND r.status IN ('completed', 'failed')
  AND r.ended_at < now() - interval '30 days';
```

Never delete checkpoints for a run in `awaiting_review` — that is the state an engineer's
decision will resume.

### The dashboard loads but shows no alarms

The database is empty, or the API is unreachable from nginx.

```bash
curl -s localhost:8081/api/alarms?limit=1          # through the ingress
kubectl -n fab-triage exec deploy/backend -- python -m app.seed.seed
```

Re-seeding is destructive and drops existing agent runs along with the alarms they reference.

### Rolling back

Images are tagged, so roll the deployment back rather than rebuilding:

```bash
kubectl -n fab-triage rollout undo deployment/backend
kubectl -n fab-triage rollout status deployment/backend
```

Paused runs are unaffected — their state is in Postgres, and any replica of any version can
resume them, provided the graph's node names have not changed. **If a release renames or removes
a graph node, drain reviews before deploying it:** a checkpoint referring to a node that no
longer exists cannot be resumed.

## Evaluation

The harness scores the agent on 30 held-out alarms it has never seen. The headline number is not
accuracy — it is `unsafe_continue_rate`, the fraction of lots that should have been held and were
marked `continue`. A wrong hold costs an hour; a wrong continue costs a lot of wafers.

Baselines set the floor, and are worth running first:

| Predictor | Action accuracy | On ambiguous codes | Unsafe continue |
|---|---|---|---|
| always-escalate | 26.7% | 23.5% | 0.0% |
| majority-by-code | 73.3% | 52.9% | 33.3% |

`always-escalate` is perfectly safe and useless, which is why safety is never the only number.
`majority-by-code` is a lookup table on the alarm code; it scores 100% on the five scenarios with
unique codes and 0% on both that share an ambiguous one. Compare any agent against its
**ambiguous-code** column, since that is where reasoning actually shows.

## Licence and data

SECOM is published by UCI for research use. Everything else here is a simulation and should not be
mistaken for a real manufacturing execution system.
