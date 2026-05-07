# Contributing to why-agent

Thank you for your interest in contributing! This guide covers the development setup, testing workflow, and code quality standards.

---

## Prerequisites

- **Python 3.12+** (check `.python-version`)
- **uv** — modern Python package manager ([install](https://docs.astral.sh/uv/))
- **Node.js 20+** — for the Next.js frontend (optional, only if modifying frontend)
- **Git** — for version control

---

## Development Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/Isa-Mapo-Hackathon/why-agent.git
cd why-agent
uv sync
```

This installs both runtime and dev dependencies (pytest, ruff, pyright).

### 2. Set up environment

```bash
cp .env.example .env
```

Then edit `.env` with your secrets:
- `MODEL_BACKEND` — use `minimax` or `replay` for local development
- `MINIMAX_API_KEY` — get from [MiniMax dashboard](https://platform.minimaxi.chat/)
- `PARQUET_DIR` — defaults to `data/parquet`

### 3. Verify setup

```bash
uv run pytest -v
```

Should run ~15+ tests without errors.

---

## Running the Application

### Option A: Streamlit (Python-only, simplest)

```bash
uv run streamlit run streamlit_app.py
```

Opens at `http://localhost:8501`. Uses the Streamlit UI to ask questions directly to the agent.

### Option B: FastAPI + Next.js (full stack)

**Terminal 1 — FastAPI backend:**
```bash
cd /home/ysh/dev/why-agent
uv run fastapi run client/backend/main.py
```

Backend runs at `http://localhost:8000`. Check health at `http://localhost:8000/api/health`.

**Terminal 2 — Next.js frontend:**
```bash
cd /home/ysh/dev/why-agent/client/frontend
npm install  # if not done yet
npm run dev
```

Frontend runs at `http://localhost:3000`.

Navigate to `http://localhost:3000` to see the full Next.js interface.

---

## Common Development Commands

| Task | Command |
|------|---------|
| **Install deps** | `uv sync` |
| **Add a dependency** | `uv add <package>` (runtime) or `uv add --dev <package>` (dev) |
| **Run tests** | `uv run pytest -v` |
| **Run one test file** | `uv run pytest tests/test_agent_smoke.py -v` |
| **Lint code** | `uv run ruff check --fix` |
| **Format code** | `uv run ruff format` |
| **Type check** (optional) | `uv run pyright` |
| **Run Streamlit** | `uv run streamlit run streamlit_app.py` |
| **Run FastAPI** | `uv run fastapi run client/backend/main.py` |
| **Run Next.js dev** | `cd client/frontend && npm run dev` |

---

## Testing

### Philosophy

Tests are **smoke tests**, not unit tests. We verify:
- Tools run without crashing
- Output has the expected shape (JSON, dict keys, etc.)
- Error handling is recoverable

We do **not** mock heavily or test implementation details.

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

### Adding a test

1. Add a `.py` file in `tests/` or `client/backend/tests/`
2. Write a function named `test_*`
3. Use `assert` statements
4. Run `uv run pytest` to verify

Example:
```python
def test_my_feature():
    from agent.tools import run_sql
    result = run_sql(...)
    assert "rows" in result
    assert isinstance(result["rows"], list)
```

---

## Code Quality

Before any commit, code must pass:

```bash
uv run ruff check --fix    # Fix lint errors automatically
uv run ruff format         # Format to standard style
```

These two commands are **required** — CI will reject commits that don't pass.

Optional (not in CI, but recommended):
```bash
uv run pyright             # Type checking (editor runs this too)
```

---

## Repository Structure

```
why-agent/
├── agent/                      # Core agent logic
│   ├── graph.py               # LangGraph state machine
│   ├── state.py               # Pydantic state models
│   ├── client.py              # Multi-backend LLM client
│   ├── constants.py           # Named constants (backends, tool names, demo questions)
│   ├── tools/                 # The four tools
│   │   ├── inspect_schema.py
│   │   ├── run_sql.py
│   │   ├── compare_periods.py
│   │   └── decompose_metric.py
│   └── prompts/               # System + critique prompts
│
├── client/
│   ├── backend/               # FastAPI server
│   │   ├── main.py            # GET /health, POST /api/investigate
│   │   ├── deps.py            # Dependency injection (graph instance)
│   │   ├── sse.py             # Server-Sent Events formatting
│   │   └── tests/
│   └── frontend/              # Next.js app
│       ├── src/app/page.tsx   # Main page
│       └── package.json
│
├── data/
│   ├── parquet/               # Dataset files (gitignored)
│   └── semantic_layer.yml     # Metadata + business context
│
├── tests/                      # Python smoke tests
│   ├── test_tools.py
│   ├── test_client_backends.py
│   └── test_agent_smoke.py
│
├── docs/                       # Documentation
│   ├── CONTRIBUTING.md        # This file
│   ├── RUNBOOK.md             # Deployment guide
│   └── why-agent-architecture.png
│
├── streamlit_app.py           # Standalone Streamlit UI
├── pyproject.toml             # Python deps + commands
├── docker/                    # Containers
│   ├── Dockerfile             # Multi-stage build
│   ├── entrypoint.sh          # HF Spaces boot script
│   ├── nginx.conf             # Reverse proxy config
│   └── supervisord.conf       # Process management
│
└── README.md                  # Project overview + business context
```

---

## Architecture Overview

```
┌─────────────────────────────────┐
│ Streamlit UI                    │
│ (streamlit_app.py)              │
└────────────┬────────────────────┘
             │
       ┌─────┴──────┐
       │            │
       ▼            ▼
┌──────────────┐ ┌──────────────────┐
│ Next.js      │ │ FastAPI Backend  │
│ (client/     │ │ (client/backend/ │
│  frontend/)  │ │  main.py)        │
└──────────────┘ └────────┬─────────┘
                          │
                    ┌─────▼─────┐
                    │ LangGraph │
                    │ Agent     │
                    └─────┬─────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
          ▼               ▼               ▼
    ┌──────────┐  ┌──────────────┐  ┌──────────┐
    │DuckDB    │  │Pydantic      │  │LLM Client│
    │(Parquet) │  │Tools Schemas │  │(3 backends)
    └──────────┘  └──────────────┘  └──────────┘
```

---

## Common Issues & Solutions

### ModuleNotFoundError: No module named 'agent'

**Solution:** Make sure you're in the repo root and have run `uv sync`.

```bash
cd /home/ysh/dev/why-agent
uv sync
```

### Tests fail with "No MINIMAX_API_KEY"

**Solution:** Use `MODEL_BACKEND=replay` for local testing. Replay mode doesn't call any LLM.

```bash
export MODEL_BACKEND=replay
uv run pytest
```

### Ruff formatting conflicts with editor

**Solution:** Use the commands above — they're the source of truth.

```bash
uv run ruff format
uv run ruff check --fix
```

### Next.js frontend doesn't build

**Solution:** Make sure Node 20+ is installed and `npm install` ran successfully.

```bash
node --version  # should be v20+
cd client/frontend
npm install
npm run build
```

---

## Coding Conventions

Per `CLAUDE.md`, follow these conventions:

1. **Sync by default** — DuckDB has no async API. Use `async def` only at the LLM boundary.
2. **Pydantic v2** — All structured data (tool inputs/outputs, state, semantic layer).
3. **Type annotations** — Required on public functions (args and return type).
4. **No print()** — Use `logger = logging.getLogger(__name__)` in agent code.
5. **No magic strings** — Backend names, tool names, scenario IDs go in `agent/constants.py`.
6. **Tool docstrings for the LLM** — Write them as if the model will read them.

Example tool:

```python
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

class MyToolInput(BaseModel):
    query: str = Field(description="A human-readable query.")

def my_tool(args: MyToolInput) -> dict:
    """Use this tool to do X. Returns a dict with 'result' and optional 'error'."""
    try:
        result = ...
        return {"result": result}
    except Exception as exc:
        logger.exception("Failed")
        return {"error": str(exc), "hint": "Try Y instead"}
```

---

## Deployment

### Remote push rules

The repo has two git remotes with different push policies:

| Remote | Purpose | When to push |
|--------|---------|-------------|
| `origin` (GitHub) | Source of truth, PRs, CI | Every commit — always push here |
| `space` (HF Spaces) | Deployment target | **Only when opening a PR** |

```bash
# Normal dev — push to GitHub only
git push origin feat/my-feature

# Deploy to HF Spaces — only when PR is ready
git push space feat/my-feature:main --force
```

HF Spaces triggers a full Docker rebuild on every push. **Do not push to `space` during iteration** — only when the branch is ready for demo/review and a PR is being opened.

See [`docs/RUNBOOK.md`](./RUNBOOK.md) for:
- Full HF Spaces deployment procedure
- Environment variables for production
- Docker build and troubleshooting
- Health check and monitoring

---

## Reporting Issues

If you find a bug or have a feature request:
1. Check existing issues in GitHub
2. Provide a minimal reproduction (code snippet + data)
3. Include your environment (Python version, OS, backend)

---

## Getting Help

- **CLAUDE.md** — Implementation decisions and locked constraints
- **README.md** — Business context and architecture
- **Agent code** — Read `agent/graph.py` to understand the loop; read `agent/tools/` to see tool contracts
- **LangGraph docs** — https://langchain-ai.github.io/langgraph/
- **Pydantic docs** — https://docs.pydantic.dev/

---

Last updated: 2025-05-06
