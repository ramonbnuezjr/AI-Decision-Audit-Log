# AI Decision Audit Log

[![Tests](https://img.shields.io/badge/tests-140%20passed-brightgreen)](https://github.com/ramonbnuezjr/AI-Decision-Audit-Log)
[![Coverage](https://img.shields.io/badge/coverage-97.37%25-brightgreen)](https://github.com/ramonbnuezjr/AI-Decision-Audit-Log)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

A lightweight governance primitive for any LLM-powered agent. Intercepts every AI model
call — Anthropic (Claude), OpenAI (GPT-4o), and local models via llama-cpp-python — and
persists a structured audit record to a local SQLite database. Every call is queryable,
reconstructable, and exportable.

> **Governance gap this closes:** Most AI deployments have zero persistent record of what
> the model was asked and what it said. This project builds that record as a reusable
> wrapper — not a one-off feature.

## Prerequisites

- Python 3.11+
- macOS with Apple Silicon (M1/M2/M3) for Metal GPU acceleration, **or** any platform for CPU-only

## Setup

```bash
# Clone and enter the project
git clone https://github.com/ramonbnuezjr/AI-Decision-Audit-Log.git
cd AI-Decision-Audit-Log

# Create virtual environment
python -m venv .venv && source .venv/bin/activate

# Install with dev dependencies
# NOTE: llama-cpp-python requires a build step. On Apple Silicon with Metal:
CMAKE_ARGS="-DLLAMA_METAL=on" pip install -e ".[dev]"

# CPU-only (no Metal GPU):
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Configure environment
cp .env.example .env
# Edit .env — fill in ANTHROPIC_API_KEY and/or OPENAI_API_KEY at minimum
```

## Local Model Setup (llama.cpp)

No API key required. Runs entirely on-device via Metal GPU on Apple Silicon.

### Recommended model for M2 Mini / M2 Pro with 8 GB unified memory

**Llama 3.2 3B Instruct Q4_K_M** — Meta's latest small model, ~2.0 GB on disk, leaves ~3 GB
free headroom alongside macOS. Verified working on M2 Mini 8 GB.

> **Why not Mistral 7B?** Mistral 7B Q4_K_M is ~4.4 GB. On an 8 GB M2 Mini (macOS baseline
> ~2.5 GB + model + Python process), it leaves < 1 GB free and causes system thrashing.
> Use a 3B model for 8 GB machines; Mistral 7B is suitable for 16 GB+.

```bash
mkdir -p models

# Download Llama 3.2 3B Instruct Q4_K_M (~2.0 GB) — verified on M2 Mini 8 GB
curl -L -o models/llama-3.2-3b-instruct.Q4_K_M.gguf \
  "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
```

Then set in `.env`:

```
LLAMA_MODEL_PATH=./models/llama-3.2-3b-instruct.Q4_K_M.gguf
LLAMA_N_CTX=2048       # conservative for 8 GB
LLAMA_N_GPU_LAYERS=-1  # all layers on Metal GPU
LLAMA_N_THREADS=4
```

> **Note on startup:** The first `capture --provider llama_cpp` call loads the model into
> Metal GPU memory (~10–20 seconds). Subsequent calls in the same session are fast.
> `ggml_metal_init: skipping kernel_*_bf16` messages are normal — M2 does not support BF16
> kernels; llama.cpp uses F16/F32 automatically with no impact on output quality.

## Running Tests

```bash
pytest                          # Run all tests with coverage (≥90% required)
pytest tests/unit/              # Unit tests only
pytest tests/integration/       # Integration tests only
pytest --no-cov                 # Skip coverage (faster iteration)
```

## CLI Usage

### Capture a prompt

```bash
# Anthropic
python -m src.main capture \
  --prompt "Explain transformer architecture in 2 sentences." \
  --provider anthropic \
  --session-id ses-001 \
  --user-id user-001

# OpenAI
python -m src.main capture \
  --prompt "What is the NIST AI RMF?" \
  --provider openai \
  --session-id ses-002

# llama.cpp (local model — no API key needed)
python -m src.main capture \
  --prompt "Summarise the key points." \
  --provider llama_cpp \
  --session-id ses-003 \
  --max-tokens 512
```

### Query the audit log

```bash
# All entries
python -m src.main query

# Reconstruct a conversation
python -m src.main query --session-id ses-001

# Per-user activity
python -m src.main query --user-id user-001

# Errors and flagged calls only
python -m src.main query --errors-only
```

### Export to JSON

```bash
python -m src.main export --format json --output ./audit_export.json
```

### Model usage summary

```bash
python -m src.main summary
# PROVIDER     MODEL                                            CALLS    OK   ERR    IN TOK   OUT TOK
# llama_cpp    ./models/llama-3.2-3b-instruct.Q4_K_M.gguf       278   278     0     56641     73319
# anthropic    claude-sonnet-4-20250514                            4     0     4         0         0
# openai       gpt-4o                                              2     1     1        19        38
```

Notice that failed calls (errors) are recorded too — every attempt is audited regardless of outcome.

### Governance report

```bash
python -m src.main report
```

Displays a full governance report covering:
- **Provider health** — success rate, error count, last error per provider
- **Latency profile** — p50/p95/min/max across all successful calls
- **Token burn** — total input/output tokens with a GPT-4o cost estimate
- **Session activity** — top sessions by call volume, with user and time window
- **Anomalies** — calls with latency more than 2× the median flagged for review

### Run ServiceNow incident analysis (POC)

```bash
# Analyse 50 tickets from a ServiceNow JSON export via the local model
python scripts/run_incidents.py \
  --input "data/Incident - POS All Sites - 2026.03.22.json" \
  --limit 50 --max-tokens 300

# Dry-run (preview prompts without hitting the model)
python scripts/run_incidents.py --input data/my_export.json --dry-run --limit 5
```

Each ticket is sent through five AI analysis prompts — `summarize`, `root_cause`,
`close_code_suggestion`, `missing_info`, `pattern_flag` — and every response is
persisted to the audit log automatically. Supports JSON exports from ServiceNow
(both bare arrays and the `{"records": [...]}` wrapper format).

## Governance Dashboard (Synthetic Sentinel)

Two dashboard options are available. **Option A (recommended)** is a full-fidelity
FastAPI server with a pixel-accurate HTML/CSS/JS frontend matching the Synthetic Sentinel
design. **Option B** is the lightweight Streamlit version.

### Option A — FastAPI server (full design fidelity)

```bash
# Install server extras
pip install -e ".[server]"

# Start the server
uvicorn dashboard.server:app --reload --port 8000
# Open http://localhost:8000
```

Features: fixed top navigation bar, sidebar with nav items and active states, exact
3-column middle panel (Provider Health pips · Latency bars · Token burn donut),
side-by-side Session Activity and Incident Log, auto-refresh every 30 seconds.
No Node.js or build step required — single HTML file served by FastAPI.

### Option B — Streamlit (rapid prototyping)

A local Streamlit dashboard visualises the full audit log in a browser tab.

**What it shows:**
- KPI cards — total calls, success rate, total tokens, estimated cloud cost
- Provider health bar chart (success vs. error per provider)
- Latency profile (p50 / p95 / max horizontal bar chart)
- Token burn donut chart by provider
- Calls over time line chart
- Session activity table (sortable, all sessions)
- Incident / error log table
- Latency anomaly detection (calls > 2× median flagged)

**Setup:**

```bash
# Install dashboard extras (streamlit + plotly + pandas)
pip install -e ".[dashboard]"

# Launch
streamlit run dashboard/app.py
# Opens automatically at http://localhost:8501
```

The dashboard reads `data/audit.db` directly — no server or extra config needed.
Use the **Refresh data** button in the sidebar after running new incident batches.

## Environment Variables

See [`.env.example`](.env.example) for all required and optional variables with descriptions.

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes (if using Anthropic) | Anthropic API key |
| `ANTHROPIC_MODEL` | No | Default model (default: `claude-sonnet-4-20250514`) |
| `OPENAI_API_KEY` | Yes (if using OpenAI) | OpenAI API key |
| `OPENAI_MODEL` | No | Default model (default: `gpt-4o`) |
| `LLAMA_MODEL_PATH` | Yes (if using llama_cpp) | Path to local `.gguf` model file |
| `LLAMA_N_CTX` | No | Context window in tokens (default: 4096) |
| `LLAMA_N_GPU_LAYERS` | No | Layers on Metal GPU (-1 = all, 0 = CPU only) |
| `LLAMA_N_THREADS` | No | CPU threads for llama.cpp (default: 4) |
| `AUDIT_STORE_PATH` | No | SQLite DB path (default: `./data/audit.db`) |
| `ENVIRONMENT` | No | `local` \| `staging` \| `production` (default: `local`) |
| `LOG_LEVEL` | No | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` (default: `INFO`) |

## SQLite Schema

```sql
CREATE TABLE audit_log (
    id            TEXT PRIMARY KEY,   -- UUID4
    timestamp     TEXT NOT NULL,      -- ISO 8601 UTC
    session_id    TEXT NOT NULL,      -- groups multi-turn conversations
    user_id       TEXT NOT NULL,
    provider      TEXT NOT NULL,      -- anthropic | openai | llama_cpp
    model         TEXT NOT NULL,      -- exact model version / path
    prompt        TEXT NOT NULL,
    response      TEXT,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    latency_ms    INTEGER,
    status        TEXT NOT NULL,      -- success | error | flagged
    error_message TEXT
);
```

## Project Structure

```
src/
├── main.py              # CLI entrypoint (capture | query | export | summary | report)
├── config.py            # pydantic-settings BaseSettings
├── models/
│   └── log_entry.py     # LogEntry Pydantic model + LogStatus enum
├── db/
│   ├── schema.py        # DDL + ensure_schema()
│   ├── connection.py    # sqlite3 context manager
│   └── query.py         # 8 query functions incl. latency_stats, provider_health, session_activity
├── audit/
│   └── logger.py        # AuditLogger — pre/post hooks, writes every call
└── agent/
    └── agent.py         # Routes Anthropic / OpenAI / llama_cpp through AuditLogger

dashboard/
├── server.py            # FastAPI server — GET / (index.html) + GET /api/data
├── index.html           # Synthetic Sentinel frontend (Space Grotesk, Plotly.js, vanilla JS)
└── app.py               # Streamlit governance dashboard (streamlit run dashboard/app.py)

scripts/
├── run_incidents.py     # ServiceNow incident runner — 5 prompts/ticket, JSON/CSV input
└── sample_incidents.json  # 5 synthetic tickets for smoke testing

docs/
└── POC_PLAYBOOK.md      # Two-week POC guide (ServiceNow export → governance report)

tests/
├── conftest.py          # In-memory DB fixtures, mock provider responses
├── unit/                # 6 unit test modules (140 tests total)
└── integration/         # Agent end-to-end tests with mocked SDKs
```

## Governance Mode

This project runs in **PRODUCTION** mode. See `.cursor/rules/workflow.mdc`:
- Tests written before implementation (TDD)
- Coverage gate: ≥90% on all core modules
- All dependencies pinned to exact versions
- `mypy --strict` must pass cleanly
- `changelog.md` updated for every meaningful change

## Extending This

- **Flag a call:** set `status=flagged` manually after the call if a policy rule fires
- **Add a provider:** implement a `_chat_<provider>` method in `Agent` — inject a new client
- **Project 2 hook:** `session_id` + `user_id` is the RPAC (Role-Based AI Policy Control) foundation
- **Project 3 hook:** `status: flagged` is the persistence hook for the Policy-as-Code Guardrail Engine
