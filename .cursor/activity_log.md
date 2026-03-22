# Activity Log

## Entries

### 2026-03-22 — Project initialized via Cursor Bootstrap v2.0

- **Mode:** PRODUCTION
- **Runtime target:** Local (no cloud target yet)
- **Domain:** AI Decision Audit Log — structured tracing/logging of AI model decisions
- **Integrations pre-wired:** Anthropic SDK, OpenAI SDK, MCP stub (TBD)
- **Hardware:** GPIO disabled (`HARDWARE_ENABLED=false`)
- **Toolchain:** Black `24.4.2`, Ruff `0.5.0`, mypy strict `1.10.0`, Bandit `1.7.9`, pre-commit `3.7.1`, pytest-cov `5.0.0`
- **Scaffold created:**
  - Layer 1 — Cursor rules: `standards.mdc`, `security.mdc`, `workflow.mdc`, `agent.mdc`
  - Layer 2 — Toolchain: `pyproject.toml`, `.pre-commit-config.yaml`, `.env.example`, `.cursorignore`
  - Layer 3 — Docs: `instructions.md`, `architecture.md`, `roadmap.md`, `activity_log.md`, `changelog.md`
  - Root: `PRD.md`, `README.md`
  - Directories: `src/`, `tests/`, `scripts/`, `docs/`
- **Next session:** begin v0.1 roadmap items — `src/config.py`, `src/models/log_entry.py`

### 2026-03-22 — Full v0.1 implementation completed

- **Mode:** PRODUCTION
- **Change:** Swapped Ollama for `llama-cpp-python==0.3.16` — better fit for Apple Mini M2 (8 GB)
  with Metal GPU via `CMAKE_ARGS="-DLLAMA_METAL=on"`. No server process required.
- **Source modules created:**
  - `src/__init__.py`, `src/config.py` — pydantic-settings BaseSettings
  - `src/models/log_entry.py` — `LogEntry` + `LogStatus` with SQLite serialisation
  - `src/db/schema.py` — DDL + 5 indexes + `INSERT_SQL`
  - `src/db/connection.py` — `get_connection()` context manager
  - `src/db/query.py` — 5 query functions
  - `src/audit/logger.py` — `AuditLogger` with pre/post hooks, structlog, error re-raise
  - `src/agent/agent.py` — `Agent` routing Anthropic / OpenAI / llama_cpp via closures
  - `src/main.py` — argparse CLI: `capture`, `query`, `export`, `summary`
- **Tests created:**
  - `tests/conftest.py` — shared fixtures (in-memory DB, mock providers)
  - `tests/unit/test_log_entry.py` — 15 tests
  - `tests/unit/test_schema.py` — 8 tests
  - `tests/unit/test_connection.py` — 6 tests
  - `tests/unit/test_query.py` — 18 tests
  - `tests/unit/test_audit_logger.py` — 13 tests
  - `tests/integration/test_agent.py` — 14 tests
- **Docs updated:** `architecture.md`, `roadmap.md`, `changelog.md`, `README.md`
- **Next session:** install deps, run `pytest`, achieve ≥90% coverage, run `mypy --strict`

### 2026-03-22 — Dependency hardening, test verification, GitHub release

- **Mode:** PRODUCTION
- **Dependency resolution:** Upgraded all pinned versions in `pyproject.toml` to resolve
  `ResolutionImpossible` conflicts from `mcp==1.2.1` requiring `pydantic>=2.8.0` and
  `anyio>=4.6`. Also synchronised `rev` versions in `.pre-commit-config.yaml`.
- **Test fix:** Corrected `test_main.py` mock targets — inline imports require patching
  `anthropic.Anthropic` / `openai.OpenAI` directly, not the `src.main.*` namespace.
- **Test results confirmed:** 109 passed, 0 failed — 98.35% coverage (gate: ≥90%)
- **New files:**
  - `.env` — populated from `.env.example` for local development
  - `.gitignore` — excludes secrets, venv, generated data, model files
- **Docs updated:** `README.md` (badges, real repo URL), `changelog.md` (v0.1.1 entry)
- **Published:** initial commit pushed to https://github.com/ramonbnuezjr/AI-Decision-Audit-Log
