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
- `SEMANTIC_LAYER_PATH` — defaults to `data/semantic_layer.yml`

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

### Local Docker build

To test the full stack locally (frontend + backend + agent) in a container:

```bash
docker build -t why-agent:latest .
docker run -p 7860:7860 -e MODEL_BACKEND=replay why-agent:latest
```

Then open `http://localhost:7860`.

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

### HF Spaces environment variables

When deploying to HF Spaces, set these secrets in the Space settings:

| Variable | Value | Purpose |
|----------|-------|---------|
| `MODEL_BACKEND` | `replay` or `minimax` | LLM backend; use `replay` to avoid API costs |
| `MINIMAX_API_KEY` | (API key) | Required only if `MODEL_BACKEND=minimax` |
| `HF_DATASET_ID` | (optional) | Dataset repo ID to auto-download Parquet files on boot |
| `PARQUET_DIR` | `/app/data/parquet` | Path inside container (do not change) |
| `SEMANTIC_LAYER_PATH` | `/app/data/semantic_layer.yml` | Path inside container (do not change) |

**Note:** Paths in the container must use `/app/` prefix, not relative paths.

### HF Spaces deployment procedure

#### Quick start

1. **Create a new Space** on [huggingface.co/spaces](https://huggingface.co/spaces):
   - Owner: your username
   - Space name: `why-agent` (or any name)
   - License: MIT
   - Docker template (or blank)

2. **Link the repo**:
   ```bash
   cd /path/to/why-agent
   git remote add space https://huggingface.co/spaces/{username}/{space-name}
   ```

3. **Push to deploy** (only when ready):
   ```bash
   git push space feat/my-feature:main --force
   ```

4. **Set secrets** in the Space UI → Settings → Repository secrets:
   - `MINIMAX_API_KEY` (if using MiniMax backend)
   - `HF_DATASET_ID` (optional; see below)

#### How the build works

1. HF Spaces detects the `Dockerfile` in the repo root
2. Builds the image (takes ~5–10 minutes the first time)
3. Runs the container on port 7860
4. The `entrypoint.sh` script starts nginx, backend, and frontend via supervisord

#### Auto-downloading Parquet data

If you set `HF_DATASET_ID=ysh99226/why-agent-data`, the entrypoint will:
1. Check if `/app/data/parquet` is empty
2. Run `hf download` to fetch the dataset
3. Timeout after 120 seconds and fall back to `MODEL_BACKEND=replay`

The `hf` command (from `huggingface-hub` package) replaces the deprecated `huggingface-cli`.

#### Git workflow for deployment

**Do NOT push to HF Spaces during development.**

1. **Work on a feature branch:**
   ```bash
   git checkout -b feat/my-feature
   git push origin feat/my-feature
   ```

2. **Open a PR on GitHub** when ready.

3. **Deploy to HF Spaces only when the PR is ready to demo:**
   ```bash
   git push space main:main --force
   ```

   Or, if the feature branch is the one being demoed (before merge):
   ```bash
   git push space feat/my-feature:main --force
   ```

**Why `--force`?** HF Spaces doesn't have a traditional git history. Using `--force` ensures the Space always reflects the exact commit you push, even if the branch history differs from the origin.

---

## Docker build errors & fixes

### "replays/ directory not found" or "missing JSON files"

**Cause:** The Dockerfile expects `replays/` to exist and contain at least one `.json` file for `MODEL_BACKEND=replay` to work.

**Fix:**
```bash
# Create dummy replay if needed
mkdir -p replays
echo '{"scenario": "demo"}' > replays/demo.json
git add replays/demo.json
git commit -m "chore: add demo replay"
```

Then rebuild the Docker image.

### "SEMANTIC_LAYER_PATH not found" or "semantic_layer.yml missing"

**Cause:** The Dockerfile copies `data/semantic_layer_6w.yml` but the file doesn't exist.

**Fix:**
```bash
# Check the actual filename
ls -la data/semantic_layer*

# If using a different name, update the Dockerfile COPY line
COPY data/semantic_layer_6w.yml /app/data/semantic_layer.yml
```

Or, if you're using a different semantic layer file:
```dockerfile
COPY data/YOUR_SEMANTIC_LAYER.yml /app/data/semantic_layer.yml
```

### "supervisord can't find environment variables" or "MODEL_BACKEND not set in child processes"

**Cause:** Environment variables set in `ENV` commands are not automatically passed to supervisord child processes.

**Fix:** The `docker/supervisord.conf` must explicitly read env vars via `environment=` lines:

```ini
[program:backend]
command=/app/.venv/bin/uvicorn ...
environment=PYTHONUNBUFFERED="1",MODEL_BACKEND="replay"
```

Or pass them in the command itself. Rebuild the image after fixing `supervisord.conf`.

### "huggingface-cli: command not found"

**Cause:** The old `huggingface-cli` tool is deprecated. The project uses the newer `hf` command from `huggingface-hub` package.

**Fix:** The Dockerfile includes `huggingface-hub` in `pyproject.toml`. The `entrypoint.sh` script uses `hf download`, which is the correct command.

If the entrypoint still fails:
```bash
# Verify hf is installed
docker run -it why-agent:latest /app/.venv/bin/hf --version

# If missing, add to pyproject.toml
uv add huggingface-hub
```

### "next: command not found" or "Node.js frontend doesn't start"

**Cause:** The Next.js build failed, or the `server.js` file is missing.

**Fix:**
1. Check the build log for `npm run build` errors
2. Ensure `client/frontend/package.json` exists and has a valid build script
3. Rebuild the Docker image:
   ```bash
   docker build --no-cache -t why-agent:latest .
   ```

### "nginx bind: address already in use"

**Cause:** Port 7860 or 80 is already bound on your machine.

**Fix (local testing):**
```bash
docker run -p 8080:7860 -e MODEL_BACKEND=replay why-agent:latest
# Now visit http://localhost:8080
```

On HF Spaces, port 7860 is reserved and managed by the platform — no action needed.

### "ModuleNotFoundError: No module named 'agent'"

**Cause:** The Python path is not set correctly in the container.

**Fix:** The Dockerfile sets `ENV PYTHONPATH=/app`, which should work. If it doesn't:
1. Verify `COPY agent/ /app/agent/` in the Dockerfile
2. Check that the `backend` program in supervisord uses the full venv path: `/app/.venv/bin/uvicorn`

### "API route returns 404" or "Frontend can't reach backend"

**Cause:** nginx is not configured to reverse-proxy to the backend on 127.0.0.1:8000.

**Fix:** Check `docker/nginx.conf`:
```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header X-Real-IP $remote_addr;
    ...
}
```

Rebuild after fixing the config:
```bash
docker build --no-cache -t why-agent:latest .
```

---

## Health check & monitoring

### Verify all services are running

```bash
# Inside the container or from host
curl http://localhost:7860/api/health
# Expected: {"ok":true}

curl http://localhost:7860/
# Expected: HTML (Next.js frontend)

curl -X POST http://localhost:7860/api/investigate \
  -H "Content-Type: application/json" \
  -d '{"question":"Why did revenue go up?"}'
# Expected: Server-Sent Event stream
```

### Check logs in HF Spaces

Click "Logs" in the top right of the Space UI. The logs show:
- nginx startup
- backend startup (uvicorn)
- frontend startup (Node.js)
- Any errors from the agent or tools

### Common troubleshooting flows

**The frontend loads but the backend is down:**
1. Check Space logs (UI → Logs)
2. Verify `PYTHONPATH=/app` is set in the Dockerfile
3. Verify `supervisord.conf` has the correct backend command
4. Rebuild without cache and push:
   ```bash
   git push space feat/my-feature:main --force
   ```

**The API returns 500 errors but logs show nothing:**
1. The agent code may have an unhandled exception
2. Check the agent's error handling in `agent/graph.py`
3. Verify the semantic layer file exists at `/app/data/semantic_layer.yml`
4. Test locally:
   ```bash
   docker run -e MODEL_BACKEND=replay why-agent:latest
   curl http://localhost:7860/api/health
   ```

**Parquet data auto-download timed out, but I want to retry:**
The entrypoint waits 120 seconds for the HF dataset download, then falls back to `MODEL_BACKEND=replay`. If you want a fresh download:
1. Manually clear the parquet directory in the Space (if you have SSH access)
2. Or, restart the Space (UI → Settings → Restart)
3. The entrypoint will retry on next boot

**I pushed to the Space but the changes didn't appear:**
1. Verify you pushed to the correct branch (should push `*:main`):
   ```bash
   git push space feat/my-feature:main --force
   ```

2. HF Spaces can take 5–10 minutes to rebuild. Wait and refresh after 2 minutes.

3. If the Space still doesn't update:
   - Click "Restart" in the Space UI
   - Or delete and recreate the Space

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

Last updated: 2026-05-07
