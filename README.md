---
title: why-agent
emoji: 🔍
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# why-agent — internal working doc

Owners: Mapo, Isa

This is **our** working doc. It's where we record what we agreed on,
why we agreed on it, and who owns what. Update it when decisions change.

---

## 1. What we're building

An autonomous root-cause agent for data. User asks **"why did metric X
move?"** — agent investigates and returns a structured report with an
evidence chain. Works against any user-provided DuckDB/Parquet dataset.
Built on AMD MI300X, deployed to HF Spaces via Docker.

Working name: **Why Agent**. Repo name: `why-agent`.

---

## 2. Why this, not something else

We considered three other directions and rejected them. The reasoning
matters — it's our defense if we're tempted to scope-creep later.

| Considered | Why we rejected it |
|---|---|
| Multi-agent research over arXiv | Crowded space (Undermind, Elicit, Consensus). No clear users beyond PhD niche. |
| Conflict-aware research agent | Intellectually interesting, no real buyer. "Neat" ≠ "needed." |
| Generic NL-to-SQL agent | Saturated. Every cloud and BI vendor ships one. We can't out-product Snowflake. |
| Multi-agent diagnostic system | One capable agent teaches us more about agent fundamentals than orchestrating several shallow ones. |

What makes *why-agent* the right pick:
- **Real users**: any data team at any company > a few hundred people.
- **Real gap**: only Tellius does autonomous RCA, and it's closed enterprise. No OSS equivalent.
- **Plays to us**: Isa lives this problem at PayPal; Mapo has shipped RAG + agentic systems.
- **Beyond simple RAG**: required by the hackathon brief, naturally true here.

---

## 3. Business insight (the thing this fixes)

Every company runs on metrics. When a metric moves unexpectedly, an
analyst spends 30–90 minutes doing *mechanical* work:

Confirm the drop is real
Decompose by every dimension they can think of
Find the anomalous slice
Drill in further
Cross-check related signals
Write up the conclusion


This is expert-level but repetitive. It's exactly the shape of work
agents do well. But today's tools answer **"what is X?"**, not
**"why did X change?"**.

The market split:
- **Descriptive layer** (NL-to-SQL): saturated. Snowflake Cortex,
  Databricks Genie, Hex, Julius, Looker+Gemini, etc.
- **Diagnostic layer** (autonomous RCA): one closed-source vendor
  (Tellius). Nothing in OSS. **This is where we play.**

Our wedge in one sentence:
> *What Looker shows you, why-agent investigates for you.*

---

## 4. Architecture overview

```
Judge / user                            Cost
│                                  ────
▼
┌──────────────────────────────┐        $0
│ HF Spaces (Docker)           │
│ Next.js frontend             │
│ FastAPI backend              │
│ Agent + tools + data         │
└──────────────┬───────────────┘
               │ HTTPS, OpenAI-compat
               ▼
┌──────────────────────────────┐        $1.99/hr
│ AMD MI300X droplet           │        (when ON)
│ vLLM + Qwen3-30B-A3B         │
└──────────────────────────────┘
```

**Three logical pieces:**
1. **The model** — vLLM serving Qwen3-30B-A3B on MI300X. Heavy, expensive.
2. **The agent** — Python code (LangGraph + FastAPI). Light, runs anywhere.
3. **The data** — DuckDB on Parquet + a YAML semantic layer. Tiny.

The UI (Next.js) and agent (FastAPI) run together in a Docker container on
HF Spaces. The model is reached via HTTPS to the AMD droplet.

### Why this split

- The model needs a GPU. Nothing else does.
- HF Spaces is free; GPU droplets are $1.99/hr.
- The agent can fall back to MiniMax API when the GPU is off.
- Iteration speed: code changes don't redeploy the GPU.

### Two model backends, env-switchable
MODEL_BACKEND=minimax     → MiniMax API (MiniMax-M1). Use for dev/fallback (no GPU).
MODEL_BACKEND=vllm        → MI300X. Use for integration & demo.

This is critical infrastructure — every LLM call goes through `agent.client.get_llm()`.

---

## 5. The agent

### Loop

```
plan → decompose → drill → cross-check → critique → report
↑                                          │
└────── if evidence weak, loop back ───────┘
```

A LangGraph state machine. Each step is an explicit node. State persists
across the whole investigation.

When critique returns **VERDICT: weak**, its justification text is stored
in `state.critique_feedback` and injected into the next phase's system
prompt as a targeted directive — so the agent retries the *specific* gap
identified, rather than re-exploring from scratch and burning retry budget.

### The four tools

We deliberately have only four. Fewer integrations = fewer demo
failure modes. Hypothesis tracking lives in agent prompt + memory,
not in a tool.

| Tool | Purpose |
|---|---|
| `inspect_schema(table)` | Returns columns, types, sample values, business descriptions from semantic layer |
| `run_sql(query)` | Executes a read-only DuckDB query, returns rows |
| `decompose_metric(metric, dims)` | Slices metric by each dim, ranks slices by anomaly magnitude |
| `compare_periods(metric, before, after, segment)` | Quantifies how a slice changed between two windows |

Tools were cut from six. **Resist re-adding them.** The agent gets
smarter by reasoning better, not by having more tools.

### What "beyond simple RAG" means here

| Simple RAG | why-agent |
|---|---|
| 1 retrieval | Many SQL queries, planned |
| 1 generation | Multi-step loop |
| Static | Hypothesis-driven branching |
| No self-eval | Self-critique before reporting |
| Document-bound | Operates on live structured data |

---

## 6. Data + semantic layer

### Dataset

why-agent works against **any user-provided data** — drop Parquet files
into `data/parquet/` and point the semantic layer at them. There is no
fixed dataset baked into the project.

The current demo dataset is a marketing/CRM extract:

| File | Contents |
|---|---|
| `campaigns.parquet` | Campaign metadata and performance metrics |
| `client_first_purchase_date.parquet` | Customer acquisition timeline |
| `holidays.parquet` | Holiday calendar for seasonality context |
| `messages.parquet` | Message-level send/open/click events |

**DuckDB view registration:** All `*.parquet` files in `PARQUET_DIR` are registered as independent DuckDB views named after their file stem. There are no implicit JOINs between views — cross-table queries require explicit `INNER JOIN` / `LEFT JOIN` clauses. The agent learns which tables need joining from the `joins` section returned by `inspect_schema`, and writes SQL with explicit joins. This keeps the system generic: any set of parquet files is registered as-is, and the semantic layer YAML defines the relationships.

### The semantic layer

A single `data/semantic_layer.yml` file. Defines:

- **Tables**: column names, types, business meaning, and primary keys (supports composite PKs via a list)
- **Metrics**: named measures the agent can compute (`open_rate`, `messages_sent`, etc.)
- **Dimensions**: slicing axes for decomposition (`channel`, `topic`, `eventually_converted`, etc.)
- **Relationships**: join keys between tables
- **Filters**: globally applied rules (e.g., exclude test campaigns)
- **Value labels**: what enum values mean (e.g., `bulk` vs `trigger` vs `transactional`)
- **Gotchas**: dataset-specific analysis pitfalls surfaced to the agent at plan time

This artifact is **the contract between Isa and Mapo**. Isa produces
it; Mapo consumes it. Once it stabilizes, both of us build forward
without blocking each other.

---

## 7. Tech stack (locked)

| Layer | Choice |
|---|---|
| Hosting | HF Spaces via Docker |
| Frontend | Next.js (React + TypeScript) |
| Backend | FastAPI + LangGraph agent |
| Orchestration | LangGraph |
| Model | Qwen3-30B-A3B |
| Inference | vLLM on ROCm |
| Hardware | AMD MI300X (1 GPU) |
| Data engine | DuckDB |
| Data format | Parquet |
| Semantic layer | YAML |
| Tracing | LangSmith (free tier) |
| Validation | Pydantic |
| Deps | uv |
| Lint | Ruff |
| Containers | Docker |


## 8. Demo strategy

### Two modes the public URL supports

- 🟢 **Live MI300X mode** — full live agent against the GPU.
  Available during scheduled windows we post.
- 💬 **MiniMax fallback** — for ad-hoc questions when the GPU is off. Set `MODEL_BACKEND=minimax`.

### Demo scenarios (rehearsed, deterministic)

1. **Why did message open rate drop in the most recent campaign?**
   Expected: specific campaign/segment underperformance, tied to send-time or audience slice.
2. **Why did new customer acquisition spike in a particular month?**
   Expected: campaign concentration or holiday effect in the acquisition data.
3. **Why is weekend engagement consistently lower than weekday?**
   Expected: structural pattern, agent should distinguish from anomaly.

Scenario 1 is our hero demo.

### One thing to verify early

Run scenario 1 end-to-end on Day 3. If the agent can't reach the
conclusion from the data alone, we need a different question. **Don't
wait until Day 5 to find out.**

---

## 9. Cost & GPU budget

We have $100 in AMD Developer Cloud credits = ~50 GPU-hours.

| Phase | GPU hrs | $ |
|---|---|---|
| Day 0 — validate vLLM + Llama 70B serves | 3 | $6 |
| Days 1–2 — local build (no GPU) | 0 | $0 |
| Day 3 — first integration | 4 | $8 |
| Day 4 — iteration & prompt tuning | 6 | $12 |
| Day 5 — record replays + polish | 8 | $16 |
| Day 6 — demo day | 12 | $24 |
| **Reserve** | **17** | **$34** |
| **Total** | **50** | **$100** |

### Rules
- **DESTROY the droplet, don't stop it.** Stopped droplets still bill.
- Credits expire 30 days after activation. Activate close to use.
- One GPU only — never the 8x ($15.92/hr will burn through credits in 6 hours).
- ~$5 of our own money for a 200GB block volume to cache model weights
  across droplet recreations is a sensible add-on. Worth confirming.

---

## 10. Team split & ownership

The split mirrors the architecture: Isa owns *data + meaning*,
Mapo owns *agent + interface*. The handoff is `semantic_layer.yml`.

### Isa owns
- Demo dataset — Parquet files in `data/parquet/`
- Semantic layer YAML
- Ground-truth validation: "is the agent's answer actually right?"
- Build-in-public post about the data layer

### Mapo owns
- LangGraph state machine + agent loop
- The four tools (Pydantic schemas, implementations)
- LLM client (multi-backend switching)
- Next.js UI + FastAPI backend
- vLLM-on-MI300X setup scripts
- HF Spaces deployment
- Build-in-public post about the agent design

### Shared
- Demo script & live narration
- README, submission video, final pitch
- Day-end sync (15 min) to surface blockers

---

## 11. Day-by-day plan (rough)

| Day | Mapo | Isa | Joint |
|---|---|---|---|
| **0** (pre) | Validate vLLM on MI300X, write `start_vllm.sh`, destroy droplet | Prepare demo Parquet files, drop into `data/parquet/` | Repo scaffolded, README locked |
| **1** | Agent loop + tools against Anthropic API | Draft `semantic_layer.yml` v1 | Agree on tool I/O signatures |
| **2** | First end-to-end agent investigation working | Refine semantic layer, prep demo scenarios | Smoke-test with provided dataset |
| **3** | Switch to vLLM backend, run scenario 1 live | Validate scenario 1 ground truth | First real demo run; identify gaps |
| **4** | Prompt tuning, self-critique node | Scenario 2 + 3 ground truth | Build-in-public posts |
| **5** | UI polish, deploy to HF Spaces | Final dataset cleanup, write evaluation notes | Rehearse demo |
| **6** | Final fixes, submission prep | Final fixes, submission prep | Submit + pitch |

### What's allowed to slip
- Scenario 3 (the structural-pattern one)
- Streamlit polish beyond functional
- Build-in-public posts after the first two

### What is NOT allowed to slip
- Scenario 1 working end-to-end by Day 3
- Public URL up and demoable by Day 5

---

## 12. Risks & open questions

### Risks we can name today

1. **vLLM-on-MI300X setup stalls Day 1.** Mitigation: validate on Day 0,
   keep Anthropic API fallback always wired.
2. **The "right answer" for our chosen scenario isn't reachable from
   the data alone.** Mitigation: pick scenario on Day 0; smoke-test
   end-to-end by Day 3.
3. **HF Spaces memory limit exceeded by data + agent + process overhead.** Mitigation: keep Parquet files under 500 MB total; profile
   on Day 2.
4. **Live demo timing variance — agent takes 90s instead of 60s.**
   Mitigation: don't claim "60 seconds"; frame as "minutes vs hours."
5. **One of us gets sick.** Mitigation: README + repo are clear enough
   the other can demo solo.

### Open questions to resolve early

- [ ] Which specific question is our hero demo?
- [ ] Is the semantic layer accurate enough for the demo dataset?
- [ ] Do we pay $5 for the model-weights block volume?
- [ ] Do we want a custom domain, or is the HF Spaces URL fine? *(default: HF Spaces URL fine)*

---

## 13. Working agreements

- **Decisions go in this doc.** If we changed our minds, edit it. No
  re-litigating in chat.
- **Day-end sync, 15 min.** Just blockers and tomorrow's priority.
- **Push to main freely until Day 4.** From Day 5: PRs only.
- **No new tools, libraries, or scope past Day 3** without explicit
  agreement from both of us.
- **The semantic layer is a contract.** Once stable, breaking changes
  require a heads-up.

---

## 14. Implementation status

| Component | Status |
|---|---|
| LLM client — 2 backends (`minimax`, `vllm`) | ✅ done |
| Pydantic state model (`InvestigationState`) | ✅ done |
| LangGraph state machine (6-phase loop) | ✅ done |
| `inspect_schema` tool | ✅ done — derived dimensions surface SQL expression |
| `run_sql` tool | ✅ done |
| `compare_periods` tool | ✅ done |
| `decompose_metric` tool | ✅ done |
| System + critique prompts | ✅ done |
| REPL for local testing | ✅ done |
| Next.js UI + FastAPI backend | ✅ done |
| Demo dataset in `data/parquet/` | ✅ done |
| vLLM Docker + MI300X scripts | ✅ done |
| HF Spaces deployment | ✅ done |

---

## 15. Getting started (dev setup)

```bash
# Prerequisites: Python 3.12+, uv installed
git clone https://github.com/Isa-Mapo-Hackathon/why-agent
cd why-agent
uv sync

# Copy and fill in .env
cp .env.example .env
# Set MINIMAX_API_KEY (get from MiniMax dashboard)
# PARQUET_DIR defaults to data/parquet — point at data/dev for the toy dataset

# Run the test suite (120 tests, no network required)
uv run pytest

# Interactive REPL against the real MiniMax API
uv run python scripts/repl_graph.py
# > Q: Why did PR activity drop on Oct 21 2018?

# Lint + format (must be clean before any commit)
uv run ruff check --fix && uv run ruff format

# Run the app — FastAPI backend + Next.js frontend
uv run uvicorn client.backend.main:app --reload --port 8000  # Terminal 1
cd client/frontend && npm run dev                             # Terminal 2
```

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `MODEL_BACKEND` | Yes | `minimax` or `vllm` |
| `MINIMAX_API_KEY` | When `MODEL_BACKEND=minimax` | MiniMax API key |
| `VLLM_ENDPOINT` | When `MODEL_BACKEND=vllm` | e.g. `http://host:8000/v1` |
| `PARQUET_DIR` | No | Path to Parquet files (default: `data/parquet`) |
| `SEMANTIC_LAYER_PATH` | No | Default: `data/semantic_layer.yml` |

---

## 16. Running Locally (Full Stack)

**Terminal 1 — FastAPI backend:**

```bash
uv run uvicorn client.backend.main:app --reload --port 8000
```

Backend runs at `http://localhost:8000`. Check health at `http://localhost:8000/api/health`.

**Terminal 2 — Next.js frontend:**

```bash
cd client/frontend
npm install  # first time only
npm run dev
```

Frontend runs at `http://localhost:3000`.

### Common development commands

| Task | Command |
|------|---------|
| Install/sync deps | `uv sync` |
| Add dependency | `uv add <package>` (runtime) or `uv add --dev <package>` (dev) |
| Run all tests | `uv run pytest -v` |
| Run one test file | `uv run pytest tests/test_tools.py -v` |
| Lint & auto-fix | `uv run ruff check --fix` |
| Format code | `uv run ruff format` |
| Type check (optional) | `uv run pyright` |
| Run FastAPI backend | `uv run uvicorn client.backend.main:app --reload --port 8000` |
| Run Next.js frontend | `cd client/frontend && npm run dev` |
| Build Next.js | `cd client/frontend && npm run build` |
| Build Docker image | `docker build -t why-agent:latest .` |

---

## 17. Development & Testing

### Running tests

```bash
# All tests
uv run pytest

# Single file
uv run pytest tests/test_tools.py -v

# Single test
uv run pytest tests/test_tools.py::test_inspect_schema -v

# With print output
uv run pytest -s
```

Tests are **smoke tests** — we verify that tools run without crashing and return the expected JSON shape. Mocking is minimal.

### Code quality gates (required before commit)

```bash
uv run ruff check --fix    # Fix lint issues
uv run ruff format         # Format code
```

Both must pass before committing. Set up a pre-commit hook to automate:

```bash
cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash
uv run ruff check --fix && uv run ruff format || exit 1
EOF
chmod +x .git/hooks/pre-commit
```

### Using the REPL (interactive testing)

```bash
# Against MiniMax API (requires MINIMAX_API_KEY)
export MODEL_BACKEND=minimax
uv run python scripts/repl_graph.py
# > Q: Why did message open rate drop?
# > Q: Why does weekend engagement differ?
```

---

## 18. Deployment to HF Spaces

why-agent is designed to deploy to Hugging Face Spaces via Docker. The included `Dockerfile` is multi-stage and includes everything: Python agent, FastAPI backend, Next.js frontend, and nginx reverse proxy.

### Quick deploy (3 steps)

**1. Push code to HF Spaces:**

```bash
# Set up remote once (replace with your Spaces URL)
git remote add space https://huggingface.co/spaces/YOUR_USERNAME/why-agent.git

# Then push (HF Spaces auto-detects Dockerfile and builds)
git push space main
```

**2. Set environment variables in HF Spaces Settings:**

Go to Space Settings > Variables and add:

| Variable | Value |
|----------|-------|
| `MODEL_BACKEND` | `replay` (recommended) or `vllm` if you have a GPU endpoint |
| `MINIMAX_API_KEY` | Only if using `MODEL_BACKEND=minimax` |
| `VLLM_ENDPOINT` | Only if using `MODEL_BACKEND=vllm` (e.g. `http://vllm-api.example.com:8000/v1`) |
| `HF_DATASET_ID` | Optional: e.g. `username/why-agent-data` (auto-downloads at boot) |

**3. Verify:**

```bash
curl https://YOUR_SPACE_URL/api/health
```

Should return: `{"ok": true}`

### Model backends explained

| Backend | Use case | Cost | Setup |
|---------|----------|------|-------|
| **minimax** | Dev/fallback LLM for ad-hoc questions | ~$0.01/query | Set `MINIMAX_API_KEY` |
| **vllm** | High-quality, fast inference on GPU | $1.99/hr (AMD MI300X) | Set `VLLM_ENDPOINT` |

### Docker: build and run locally

```bash
# Build
docker build -t why-agent:latest .

# Run
docker run -p 7860:7860 -e MODEL_BACKEND=replay why-agent:latest
```

Then visit `http://localhost:7860`.

### Environment variables reference (complete)

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_BACKEND` | — | LLM backend: `minimax` or `vllm` |
| `MINIMAX_API_KEY` | — | MiniMax API key (if using minimax backend) |
| `VLLM_ENDPOINT` | — | vLLM server URL (if using vllm backend; include `/v1`) |
| `PARQUET_DIR` | `/app/data/parquet` | Path to Parquet dataset directory |
| `SEMANTIC_LAYER_PATH` | `/app/data/semantic_layer.yml` | Path to semantic layer YAML |
| `HF_DATASET_ID` | — | HF Dataset ID to auto-download at boot (optional) |
| `LANGSMITH_API_KEY` | — | LangSmith API key for tracing (optional) |

### Health check endpoints

```bash
# Health check
curl http://localhost:7860/api/health
# Returns: {"ok": true}

# Demo questions
curl http://localhost:7860/api/demo-questions
# Returns: {"questions": [...]}

# Investigate (POST)
curl -X POST http://localhost:7860/api/investigate \
  -H "Content-Type: application/json" \
  -d '{"question": "Why did open rate drop?"}'
# Streams Server-Sent Events (SSE)
```

### Troubleshooting deployment

| Issue | Solution |
|-------|----------|
| Build fails with npm error | Ensure Node 20+ installed; run `npm install --legacy-peer-deps` locally |
| API returns 500 | Check HF Spaces logs; verify `PARQUET_DIR` and `SEMANTIC_LAYER_PATH` exist |
| vLLM endpoint unreachable | Verify `VLLM_ENDPOINT` includes `/v1`; check GPU server is running |
| Data not loading | Set `HF_DATASET_ID` to auto-download, or manually COPY Parquet files into Dockerfile |

---

## 19. Architecture & Project Structure

```
why-agent/
├── agent/                           # Core agent logic
│   ├── graph.py                     # LangGraph state machine (6-phase loop)
│   ├── state.py                     # Pydantic InvestigationState model
│   ├── client.py                    # Multi-backend LLM client
│   ├── constants.py                 # Named constants (backends, tools, demo questions)
│   ├── tools/                       # The four tools
│   │   ├── inspect_schema.py       # Returns table metadata + business context
│   │   ├── run_sql.py              # Execute read-only DuckDB queries
│   │   ├── compare_periods.py      # Quantify metric change between windows
│   │   └── decompose_metric.py     # Slice metric by dimensions, rank anomalies
│   └── prompts/                     # System + critique prompts (markdown)
│       ├── system.md
│       └── critique.md
│
├── client/
│   ├── backend/                     # FastAPI server
│   │   ├── main.py                 # GET /health, POST /api/investigate
│   │   ├── deps.py                 # Dependency injection
│   │   ├── sse.py                  # Server-Sent Events formatting
│   │   └── tests/
│   └── frontend/                    # Next.js app (React + TypeScript)
│       ├── src/app/page.tsx        # Main UI page
│       ├── src/app/api/investigate # Next.js API route (optional)
│       └── package.json
│
├── data/
│   ├── parquet/                     # Dataset files (user-provided; gitignored)
│   ├── semantic_layer.yml           # Business metadata, metrics, dimensions, joins
│   └── root_cause/                  # Ground-truth documentation
│
├── tests/                           # Python smoke tests
│   ├── test_tools.py               # Tool execution and output shape
│   ├── test_client_backends.py     # Verify backends (minimax, vllm)
│   └── test_graph_smoke.py         # Agent state machine and critique tests
│
├── docker/                          # Container config
│   ├── entrypoint.sh               # Boot script (handles HF Dataset download)
│   ├── nginx.conf                  # Reverse proxy (routes / to Next.js, /api/* to FastAPI)
│   └── supervisord.conf            # Process management (nginx, FastAPI, Next.js)
│
├── scripts/                         # Utilities
│   └── repl_graph.py               # Interactive REPL for testing the agent
│
├── Dockerfile                      # Multi-stage: Next.js + Python + nginx
├── pyproject.toml                  # Dependencies + test config
├── Dockerfile                      # Deployment image
├── .env.example                    # Environment template
├── CLAUDE.md                       # Implementation decisions & constraints
├── README.md                       # This file (project overview + business context)
└── docs/
    └── why-agent-architecture.png  # Diagram
```

---

## 20. Coding conventions

Per CLAUDE.md, follow these when writing code:

1. **Sync by default** — DuckDB and LangGraph nodes are sync. Use `async def` only at the LLM boundary.
2. **Pydantic v2** — All structured data (tool inputs/outputs, state, semantic layer).
3. **Type annotations** — Required on public functions (args + return type).
4. **No print()** — Use `logger = logging.getLogger(__name__)` in agent code.
5. **No magic strings** — Backend names, tool names, scenario IDs go in `agent/constants.py`.
6. **Tool docstrings for the LLM** — Write them as if the model will read them (be descriptive about what it does and when to use it).

### Example tool implementation

```python
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

class MyToolInput(BaseModel):
    query: str = Field(description="A human-readable query or metric name.")

class MyToolOutput(BaseModel):
    result: dict
    error: str | None = None

def my_tool(args: MyToolInput) -> dict:
    """Use this tool to analyze X. Returns a dict with 'result' (the data) and optional 'error'."""
    try:
        result = ...
        return {"result": result}
    except Exception as exc:
        logger.exception("Tool failed for query: %s", args.query)
        return {"error": str(exc), "hint": "Try phrasing the query differently"}
```

---

## 21. Locked decisions (do not change without explicit approval)

These decisions are locked per CLAUDE.md. Changing any requires discussion:

| Decision | Value | Why |
|----------|-------|-----|
| Architecture | Single agent (not multi-agent) | Simpler to debug, easier to understand agentic fundamentals |
| Tool count | 4 tools (fixed) | Fewer integrations = fewer demo failure modes |
| Orchestration | LangGraph (not CrewAI, AutoGen, etc.) | Explicit state machine, good tracing, community support |
| Model (prod) | Llama-3.3-70B (vLLM) | Open-source, fast on MI300X, no licensing |
| Model (dev) | MiniMax-M2.7 (API fallback) | No GPU required, quick iteration |
| Data engine | DuckDB on Parquet | Embedded, column-oriented, single query engine |
| Semantic layer | Single YAML file (hand-written) | Simple, no tooling overhead, easy to version |
| UI | Next.js frontend + FastAPI backend | Modern stack, full SSE streaming, resizable sidebar |
| Hosting | HF Spaces via Docker | Free, simple, community-friendly |
| License | MIT | Open-source, permissive |

If a task seems to require changing one of these, pause and ask before proceeding.

---

## 22. Risks & known limitations

1. **Parquet size** — Keep total Parquet data under 500 MB to fit in HF Spaces' memory limit. Profile on Day 2.
2. **Investigation latency** — Agent might take 60–120 seconds on a fallback model. Frame demos as "minutes vs hours," not "60 seconds."
3. **GPU availability** — The MI300X droplet costs $1.99/hr. Use `MODEL_BACKEND=replay` when the GPU is off.
4. **Concurrent requests** — HF Spaces free tier queues additional requests (no parallelism). For production, use a dedicated server.
5. **Concurrent requests** — HF Spaces free tier may queue additional requests. For sustained load, use a dedicated server.

---

## 23. Resources & links

- AMD Developer Hackathon: https://lablab.ai/ai-hackathons/amd-developer
- AMD Developer Cloud docs: https://www.amd.com/en/developer/resources/cloud-access/amd-developer-cloud.html
- LangGraph docs: https://langchain-ai.github.io/langgraph/
- vLLM on ROCm: https://docs.vllm.ai/en/latest/getting_started/amd-installation.html
- MiniMax API: https://platform.minimaxi.chat/
- Hugging Face Spaces: https://huggingface.co/spaces