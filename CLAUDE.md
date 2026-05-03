# CLAUDE.md

Instructions for Claude Code working on `why-agent`.

For the **project rationale, business insight, demo strategy, and team plan**, read [`README.md`](./README.md) first. This file is operational instructions only — it does not repeat the why.

---

## Your role

You are the primary code-writer for this project. The human team supervises, reviews, and pairs — they do not type code. For team responsibilities and how the work is split, see [`README.md`](./README.md) §10.

**Default behavior:**
- When given a task, complete it end-to-end. Don't stop halfway to ask permission for obvious next steps.
- Run code you write. Verify it works before declaring it done.
- If a test fails or output looks wrong, debug it; don't hand it back broken.
- Match the existing code style. Don't reformat or "improve" code outside the requested change.

**Hard blocks (do not do, even if asked casually — require an explicit "yes, do it"):**
- Add a second LLM-orchestration framework alongside LangGraph
- Add a vector DB, embedding model, or RAG retrieval layer (this is also a "new dependency" — the block wins)
- Add authentication, multi-tenancy, or user accounts
- Push to `main` once the public demo URL is live (branch + PR instead — see workflow)
- Change any value in the "Locked decisions" table below

**Ask first, then proceed (a quick "ok" is enough):**
- Add a new dependency that isn't in the approved list (and isn't on the hard-block list above)
- Add a new file at the repo root or create a new top-level directory
- Restructure more than 3 files in one change

---

## What this project is, in 3 lines

A single LangGraph agent that investigates "why did metric X move?" by calling four tools against any DuckDB-on-Parquet dataset the user provides. Described by a YAML semantic layer. Served by Llama-3.3-70B on AMD MI300X via vLLM, with MiniMax API as a dev/fallback backend. Demoed in a Streamlit app deployed to Streamlit Community Cloud.

If a task you're given doesn't fit that shape, push back before coding.

---

## Locked decisions — do not change without explicit human approval

| Decision | Value |
|---|---|
| Architecture | Single agent. Not multi-agent. |
| Tool count | 4. Not 5, not 6, not 3. |
| Orchestration | LangGraph. Not CrewAI, AutoGen, raw SDK loops, etc. |
| Model (prod) | `meta-llama/Llama-3.3-70B-Instruct`, BF16, via vLLM |
| Model (dev) | `MiniMax-M1` via MiniMax API (`MINIMAX_API_KEY`) |
| Data engine | DuckDB on Parquet. No Postgres, no Snowflake. |
| Semantic layer | Single YAML file, hand-written. No dbt, no Cube. |
| UI | Streamlit. Not Next.js, not Gradio, not FastAPI-only. |
| Hosting | Streamlit Community Cloud. Not DOKS, not App Platform. |
| License | MIT |
| Repo name | `why-agent` |

If you find yourself wanting to change one of these, stop and ask before proceeding.

---

## The four tools — exact contract

These are the only tools the agent has. Implement them exactly:

```python
def inspect_schema(table: str | None = None) -> dict:
    """List tables (no arg) or describe one table (cols, types, business
    meaning) by reading from the semantic layer + Parquet metadata."""

def run_sql(query: str, max_rows: int = 100) -> dict:
    """Execute a read-only SELECT against DuckDB. Returns
    {rows, truncated, row_count, execution_ms}. Reject non-SELECT statements."""

def compare_periods(metric: str, before: dict, after: dict, segment: dict | None = None) -> dict:
    """Headline diff: by how much did `metric` change between two windows?
    Use this FIRST when the question is 'did X move, and how much?'.
    Returns one row: {before_value, after_value, abs_delta, pct_delta}.
    Does NOT tell you which slice caused the change — call decompose_metric for that."""

def decompose_metric(metric: str, dimensions: list[str], time_window: dict) -> dict:
    """Drill-down: WHICH slice of `metric` drove the movement?
    Use this AFTER compare_periods has confirmed a delta and you need to
    attribute it. For each dimension, slices `metric` over `time_window` and
    ranks slices by anomaly magnitude (deviation vs. baseline). Returns ranked slices.
    Does NOT compute a headline before/after number — call compare_periods for that."""
```

**Rules:**
- Tool inputs are validated with Pydantic models (`agent/tools/schemas.py`)
- Tool outputs are JSON-serializable dicts
- **Tool errors must be agent-recoverable strings, never silent failures and never raised exceptions.** Catch every exception inside the tool and return `{"error": "<one-line message>", "hint": "<what to try next>"}`. The `hint` is what lets the agent self-correct on the next turn — write it for the model.
- Each tool's docstring is its description to the LLM. Write it for the model.

If a feature seems to require a 5th tool, propose it but do not add it. Most "5th tool" requests are reasoning concerns that belong in prompts, not tools.

---

## Repository structure (target)
why-agent/
├── README.md                        # human-facing project doc
├── CLAUDE.md                        # this file
├── LICENSE                          # MIT
├── pyproject.toml                   # uv-managed
├── .python-version                  # 3.12
├── .env.example
├── .gitignore
├── streamlit_app.py                 # Streamlit Cloud entrypoint
│
├── agent/
│   ├── __init__.py
│   ├── graph.py                     # LangGraph state machine
│   ├── state.py                     # Pydantic state models
│   ├── client.py                    # Multi-backend LLM client
│   ├── prompts/
│   │   ├── system.md
│   │   └── critique.md
│   └── tools/
│       ├── __init__.py
│       ├── schemas.py               # Pydantic input/output models
│       ├── inspect_schema.py
│       ├── run_sql.py
│       ├── decompose_metric.py
│       └── compare_periods.py
│
├── data/
│   ├── extract/
│   ├── parquet/                     # gitignored
│   └── semantic_layer.yml
│
├── replays/                         # Pre-recorded investigations (JSON)
│
├── docker/
│   ├── Dockerfile.vllm              # MI300X serving image
│   └── docker-compose.yml
│
├── scripts/
│   ├── start_vllm.sh                # Provision droplet + vLLM
│   ├── stop_vllm.sh                 # DESTROY droplet (not stop)
│   └── record_replay.py             # Save canonical investigation
│
├── tests/
│   ├── test_tools.py
│   ├── test_client_backends.py      # MUST exist — verifies MODEL_BACKEND switch
│   └── test_agent_smoke.py
│
└── docs/
└── (additional notes if needed)

When asked to add files, place them by purpose. Don't create new top-level directories without asking.

---

## Environment & dependencies

- Python: **3.12+**
- Package manager: **uv** (not pip, not poetry)
- Lint/format: **Ruff** (use `ruff check --fix` and `ruff format`)
- Type checker: **Pyright** locally (editor or `uv run pyright`). No type checker in CI for hackathon scope — annotations are a guide for the editor and the LLM, not a CI gate.

When adding a dep:
```bash
uv add <package>          # runtime
uv add --dev <package>    # dev only
```

**Approved deps (no need to ask):**
`langgraph`, `langchain-anthropic`, `langchain-openai`, `pydantic`, `duckdb`, `pyarrow`, `streamlit`, `pyyaml`, `langsmith`, `python-dotenv`

**Ask before adding:**
Anything else, especially: vector DBs, embedding libs, additional agent frameworks, ORM libraries, web frameworks beyond Streamlit, anything heavyweight.

---

## Running things

Canonical commands. If you need to run the project, this is what to type — don't invent variants.

```bash
# Install / sync deps
uv sync

# Run the Streamlit app (the demo entrypoint)
uv run streamlit run streamlit_app.py

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_client_backends.py -v

# Lint + format (must pass before declaring a task done)
uv run ruff check --fix
uv run ruff format

# Optional local type check (not in CI)
uv run pyright

# Record a replay (writes replays/<scenario_id>.json)
uv run python scripts/record_replay.py --scenario <id>
```

Required env vars (see `.env.example`):

```
MODEL_BACKEND=minimax | vllm | replay
MINIMAX_API_KEY=...                      # required when MODEL_BACKEND=minimax
VLLM_ENDPOINT=http://host:8000/v1        # required when MODEL_BACKEND=vllm — include /v1
REPLAY_SCENARIO_ID=...                   # required when MODEL_BACKEND=replay (or pass to get_llm())
PARQUET_DIR=data/parquet                 # default
SEMANTIC_LAYER_PATH=data/semantic_layer.yml
```

---

## Three model backends — env-switchable

The LLM client (`agent/client.py`) MUST support three backends switched by env var:

```bash
MODEL_BACKEND=minimax      # ChatOpenAI-compatible client pointed at MiniMax API, MiniMax-M1
MODEL_BACKEND=vllm         # ChatOpenAI pointed at VLLM_ENDPOINT
MODEL_BACKEND=replay       # Read pre-recorded JSON, no real LLM call
```

This is **critical infrastructure**. Implement it before any agent work. Every other piece of the codebase imports from `agent.client.get_llm()` and never instantiates an LLM directly.

`replay` mode reads from `replays/<scenario_id>.json` and yields the same message/tool-call sequence the live agent produced when recorded. It is essential for the public demo when the GPU is off.

Because this is critical infrastructure, `tests/test_client_backends.py` must exist and assert: each `MODEL_BACKEND` value (`minimax`, `vllm`, `replay`) returns a client of the expected type, and an unknown value raises a clear error. This test runs without network — `minimax` and `vllm` paths assert on construction, not invocation.

---

## Coding conventions

- **Sync by default.** DuckDB has no async API, LangGraph nodes are sync, Streamlit is sync. Use `async def` only at the LLM-client boundary (e.g. `langchain-anthropic.ainvoke`) and only if it actually buys concurrency. Do not wrap sync DuckDB calls in `async def`.
- **Pydantic v2** for all structured data: tool inputs, agent state, semantic layer.
- **Type-annotate public functions** — tool signatures, graph nodes, anything imported across modules. Return types included. Annotations are not enforced in CI for hackathon scope; if you want enforcement, run `pyright` locally before committing. Don't claim "typed everywhere" without a checker — pick consistency over a slogan.
- **No print()** in agent code. Use `logger = logging.getLogger(__name__)`. Print is fine in scripts.
- **No magic strings.** Tool names, backend names, scenario IDs go in `agent/constants.py` as named constants.
- **Tests are smoke tests, not unit tests.** Verify the tool runs and returns expected shape; don't mock heavily.
- **Docstrings on public functions.** Tool docstrings are read by the LLM — write them for that audience.

Example tool implementation shape:

```python
# agent/tools/run_sql.py
from pydantic import BaseModel, Field
import duckdb
import logging

logger = logging.getLogger(__name__)

class RunSqlInput(BaseModel):
    query: str = Field(description="A read-only SELECT statement.")
    max_rows: int = Field(default=100, ge=1, le=1000)

class RunSqlOutput(BaseModel):
    rows: list[dict]
    truncated: bool
    row_count: int
    execution_ms: float
    error: str | None = None

def run_sql(args: RunSqlInput, conn: duckdb.DuckDBPyConnection) -> RunSqlOutput:
    """Execute a read-only DuckDB query. Returns rows or an error.
    Use this AFTER inspecting the schema, not before."""
    ...
```

---

## What "done" means

A task is done when:
1. Code runs without error (`uv run ...`)
2. The new behavior is verified — by a smoke test, a manual run, or both
3. Ruff is clean (`ruff check` and `ruff format` pass)
4. The relevant docstring is updated if the contract changed
5. README.md or CLAUDE.md is updated if a locked decision changed (rare)

Not done if:
- "It should work" — verify it does
- Tests pass but you didn't run the actual code
- You added TODOs without flagging them at the end of your message

---

## Workflow

- **Always work on a feature branch. Never commit directly to `main`.** Create a branch for every task, then open a PR to merge into `main`. Branch naming: `<type>/<short-slug>` (e.g. `feat/inspect-schema`, `fix/sql-injection-guard`).
- Commits: Short, imperative subject. ("Add inspect_schema tool", not "Added schema inspection.")
- Don't squash commits into single mega-commits. Atomic changes preferred.
- Don't open GitHub PRs/issues programmatically unless asked. Draft the PR description and let the human merge.

When you finish a task, your reply should include:
1. What you changed (1-2 sentences)
2. Files touched
3. How you verified it works
4. Anything you noticed but didn't fix (so the human can decide)

---

## Things that are out of scope

If asked to do any of these, push back:

- Multi-agent orchestration (Coordinator/Worker/Critic split, etc.)
- Vector RAG over documents (the semantic layer is small enough to live in the prompt)
- Authentication, OAuth, or user sessions
- Generating the semantic layer from raw schema (out of scope for this project)
- Cross-source data joining (warehouse + logs + APIs)
- Fine-tuning or LoRA training
- Anything that requires Kubernetes
- Custom domain or DNS work
- A "production hardening" pass — rate limits, retries with backoff, circuit breakers. Out of scope for a hackathon demo.

If a request implies one of these, ask: "this looks like X which we marked out of scope. Are you sure?"

---

## Demo discipline

- Don't claim "60 seconds" anywhere in copy. Use "minutes vs hours."
- Every demo scenario must have a recorded replay committed before the public URL goes live.
- The Streamlit app must always work — if every backend is down, replay mode still answers.
- The public URL is the only way judges access the demo. Don't break it.
- (Tool error handling lives in the tool contract section above, not here.)

---

## When you are unsure

- The agent should be boring and predictable, not clever.
- Prefer fewer features finished over more features attempted.
- If a decision has two reasonable answers, pick the simpler one and flag it in your reply.
- If you find a real bug in the code, fix it inline and mention it.

---

*Updated: when locked decisions change, when the team split changes, or when a new convention is added. Otherwise, leave it alone.*