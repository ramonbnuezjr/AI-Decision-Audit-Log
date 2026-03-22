# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## v0.1.1 — Dependency Hardening & GitHub Release — 2026-03-22

### Fixed
- Resolved `ResolutionImpossible` pip conflicts caused by `mcp==1.0.0` requiring
  `pydantic>=2.8.0` and `anyio>=4.6` while bootstrap had pinned older versions.
  Updated all core dependencies to latest stable and compatible versions:
  `anthropic==0.49.0`, `openai==1.68.2`, `pydantic==2.11.10`,
  `pydantic-settings==2.9.1`, `mcp==1.2.1`, `httpx==0.28.1`, `anyio==4.7.0`,
  `structlog==24.4.0` and all dev tools.
- Fixed `AttributeError` in `test_main.py`: test patches for Anthropic/OpenAI now
  target `anthropic.Anthropic` and `openai.OpenAI` directly instead of
  `src.main.anthropic` (imports are inline inside the handler function).

### Added
- `.gitignore` — excludes `.env`, `.venv/`, `data/`, `models/`, caches, build artifacts
- GitHub repository published at https://github.com/ramonbnuezjr/AI-Decision-Audit-Log

### Test Results
- **109 tests passed**, 0 failed — `pytest --tb=short`
- **98.35% coverage** — exceeds the 90% PRODUCTION mode gate

## v0.1.0 — Full Implementation — 2026-03-22

### Added
- **`src/config.py`** — `Settings` (pydantic-settings BaseSettings) with validators for
  `log_level` and `environment`; `get_settings()` factory
- **`src/models/log_entry.py`** — `LogEntry` Pydantic model (13 fields), `LogStatus` enum,
  `to_sqlite_row()` / `from_sqlite_row()` serialisation round-trip
- **`src/db/schema.py`** — `audit_log` DDL with 5 indexes, `ensure_schema()`, `INSERT_SQL`
- **`src/db/connection.py`** — `get_connection(db_path)` context manager; auto-creates parent dir
- **`src/db/query.py`** — `get_all_calls`, `get_by_session`, `get_by_user`, `get_errors`,
  `get_model_usage_summary`
- **`src/audit/logger.py`** — `AuditLogger` with `log_call()` pre/post hook pattern;
  structlog DEBUG logging; error record + re-raise
- **`src/agent/agent.py`** — `Agent` routing Anthropic / OpenAI / llama_cpp via injected
  clients; provider-specific closure pattern avoids duplicate kwargs; lazy llama model load
- **`src/main.py`** — argparse CLI: `capture`, `query`, `export`, `summary` subcommands
- **Full test suite** — `tests/conftest.py` + 5 unit modules + 1 integration module;
  in-memory SQLite fixtures, mocked provider clients

### Changed
- Replaced `ollama==0.4.9` with `llama-cpp-python==0.3.16` — no server process required;
  Metal GPU support on Apple Silicon; lazy model loading to avoid startup overhead
- Updated `.env.example` — `OLLAMA_*` vars replaced with `LLAMA_MODEL_PATH`, `LLAMA_N_CTX`,
  `LLAMA_N_GPU_LAYERS`, `LLAMA_N_THREADS`
- Updated `architecture.md` — component map reflects actual `src/agent/`, `src/audit/`,
  `src/db/` structure and data flow
- Updated `roadmap.md` — v0.1 items checked off; v0.2 and v1.0 targets refined

## v0.0.1 — Bootstrap — 2026-03-22

### Added
- Initialized project scaffold via Cursor Bootstrap v2.0
- **Layer 1 — Cursor Rules**
  - `.cursor/rules/standards.mdc` — Python coding standards (PEP 8, type hints, docstrings, Black/Ruff)
  - `.cursor/rules/security.mdc` — Security rules (secrets, input validation, error handling, deps)
  - `.cursor/rules/workflow.mdc` — Mode-aware workflow rules (PRODUCTION/LEARNING, TDD, coverage gates)
  - `.cursor/rules/agent.mdc` — Agent behavior rules (file ops, code gen, MCP tool use)
- **Layer 2 — Toolchain Enforcement**
  - `pyproject.toml` with all dependencies pinned to exact versions
  - `.pre-commit-config.yaml` with Black, Ruff, mypy, Bandit, and pre-commit-hooks
  - `.env.example` documenting all environment variables
  - `.cursorignore` excluding caches, build artifacts, and secrets
- **Layer 3 — Workflow Documents**
  - `.cursor/instructions.md` — domain-specific project instructions
  - `.cursor/architecture.md` — component map with Mermaid diagram
  - `.cursor/roadmap.md` — v0.1 / v0.2 / v1.0 milestones
  - `.cursor/activity_log.md` — session activity log
  - `PRD.md` — Product Requirements Document
  - `README.md` — setup and usage guide
- Source directories: `src/`, `tests/`, `scripts/`, `docs/`
