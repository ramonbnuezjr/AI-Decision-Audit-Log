# AI Decision Audit Log

[![Tests](https://img.shields.io/badge/tests-109%20passed-brightgreen)](https://github.com/ramonbnuezjr/AI-Decision-Audit-Log)
[![Coverage](https://img.shields.io/badge/coverage-98.35%25-brightgreen)](https://github.com/ramonbnuezjr/AI-Decision-Audit-Log)
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
# PROVIDER     MODEL                                        CALLS    OK   ERR   IN TOK  OUT TOK
# anthropic    claude-sonnet-4-20250514                         4     0     4        0        0
# openai       gpt-4o                                           2     1     1       19       38
# llama_cpp    ./models/llama-3.2-3b-instruct.Q4_K_M.gguf      1     1     0       13      270
```

Notice that failed calls (errors) are recorded too — every attempt is audited regardless of outcome.

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
├── main.py              # CLI entrypoint (capture | query | export | summary)
├── config.py            # pydantic-settings BaseSettings
├── models/
│   └── log_entry.py     # LogEntry Pydantic model + LogStatus enum
├── db/
│   ├── schema.py        # DDL + ensure_schema()
│   ├── connection.py    # sqlite3 context manager
│   └── query.py         # 5 query utility functions
├── audit/
│   └── logger.py        # AuditLogger — pre/post hooks, writes every call
└── agent/
    └── agent.py         # Routes Anthropic / OpenAI / llama_cpp through AuditLogger

tests/
├── conftest.py          # In-memory DB fixtures, mock provider responses
├── unit/                # 5 unit test modules
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
