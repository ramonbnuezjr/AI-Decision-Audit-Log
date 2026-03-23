# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## v0.2.1 — Real-World POS Incident Batch Run — 2026-03-23

### Added
- **First real-world data run** — processed 50 POS incident tickets from a live ServiceNow
  export (`Incident - POS All Sites - 2026.03.22.json`, 5,215 total records):
  - 5 AI analysis prompts per ticket (summarize, root_cause, close_code_suggestion,
    missing_info, pattern_flag)
  - **278 total llama_cpp calls across 52 sessions — 100% success rate, 0 errors**
  - 56,641 input tokens / 73,319 output tokens consumed
  - Median latency (p50) ~4.6 seconds per inference on M2 Mini 8 GB Metal GPU

### Fixed
- **`scripts/run_incidents.py` — ServiceNow JSON wrapper compatibility**
  - ServiceNow JSON exports wrap the record array in `{"records": [...]}` rather than
    being a bare array; `load_tickets()` now unwraps this automatically
  - Both bare-array JSON and `records`-wrapped JSON are now supported
- **`scripts/run_incidents.py` — Prompt template field name alignment**
  - Updated `_OPTIONAL_FIELDS` and `PROMPT_TEMPLATES` to use actual ServiceNow export
    field names: `category`, `subcategory`, `priority` (numeric code), `close_code`,
    `close_notes`, `u_root_cause_summary`
  - Replaced draft prompts (priority_check, remediation, escalation) with the five
    governance-relevant prompts: **summarize, root_cause, close_code_suggestion,
    missing_info, pattern_flag**

### Live Audit Log State (post-session)
```
PROVIDER     MODEL                                            CALLS    OK   ERR
llama_cpp    ./models/llama-3.2-3b-instruct.Q4_K_M.gguf       278   278     0
anthropic    claude-sonnet-4-20250514                            4     0     4  ← auth (unresolved)
openai       gpt-4o                                              2     1     1  ← 1 quota, 1 success
```

## v0.1.2 — Local Model Integration & Provider Incident Log — 2026-03-22

### Added
- Downloaded **Llama 3.2 3B Instruct Q4_K_M** GGUF (1.9 GB) from
  [bartowski/Llama-3.2-3B-Instruct-GGUF](https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF)
  on HuggingFace into `models/` directory
- `models/` directory created; `.gitignore` already excludes GGUF files (multi-GB)
- First successful end-to-end `llama_cpp` capture verified:
  - 1 call, `status=success`, latency ~100s (initial model load), 13 input / 270 output tokens
  - Metal GPU acceleration active (`n_gpu_layers=-1`, all layers on M2 Metal)
  - `ggml_metal_init: skipping kernel_*_bf16` messages are expected — M2 does not support BF16
    kernels; llama.cpp silently falls back to F16/F32 with no impact on correctness

### Changed
- `LLAMA_MODEL_PATH` in `.env` updated from placeholder `./models/llama3.gguf` to
  `./models/llama-3.2-3b-instruct.Q4_K_M.gguf`
- README Local Model Setup section updated with specific Llama 3.2 3B curl download command
  and M2 8 GB memory profile

### Fixed / Lessons Learned

#### Anthropic API — persistent 401 authentication errors
- Encountered `invalid x-api-key` (HTTP 401) on all Anthropic calls despite:
  - Correct key format (`sk-ant-api03-`, 108 chars, no invisible characters)
  - No whitespace or encoding issues (verified via raw byte inspection)
  - Key loading correctly from `.env` (pydantic-settings confirmed)
  - Direct `curl` bypassing all Python/SDK also returned 401
- Root cause: Unresolved on the Anthropic account side (billing or key activation state)
- Decision: Defer Anthropic until account is confirmed active; use OpenAI and llama_cpp for now

#### OpenAI API — 429 quota error on first attempt
- First OpenAI call returned `insufficient_quota` (HTTP 429) — billing was not yet activated
  on the initial API key
- Fix: Activated billing in the OpenAI console, regenerated key; second call succeeded
- Audit log correctly captured both the error and the success in session `ses-001`

#### Mistral 7B — too large for M2 Mini with 8 GB unified memory
- Mistral 7B Instruct Q4_K_M (~4.4 GB) leaves insufficient headroom on an 8 GB M2 Mini:
  macOS baseline ~2.5 GB + model ~4.4 GB + Python process ~0.5 GB = ~7.4 GB, causing
  system thrashing and poor performance
- Decision: Use **Llama 3.2 3B Instruct Q4_K_M (~2.0 GB)** — Meta's latest small model,
  leaves ~3 GB free headroom, strong instruction-following capability for testing

### Live Audit Log State (post-session)
```
PROVIDER     MODEL                                       CALLS   OK  ERR
anthropic    claude-sonnet-4-20250514                        4    0    4  ← all auth failures
openai       gpt-4o                                          2    1    1  ← 1 quota error, 1 success
llama_cpp    ./models/llama-3.2-3b-instruct.Q4_K_M.gguf     1    1    0  ← fully operational
```

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

## v0.2.0 — POC Incident Analysis Tooling — 2026-03-22

### Added
- **`src/db/query.py`** — 3 new analysis query functions:
  - `get_latency_stats()` — p50, p95, min, max latency across successful calls
  - `get_provider_health()` — per-provider success rate, error count, last error message
  - `get_session_activity()` — sessions ranked by call volume with timestamps
- **`src/main.py`** — `report` subcommand (`python -m src.main report`): structured
  governance output covering incident log, provider health, latency profile, token burn
  (with GPT-4o cost estimate), session activity, and latency anomalies
- **`scripts/run_incidents.py`** — ServiceNow incident runner; accepts JSON or CSV export;
  runs 5 AI analysis prompts per ticket (summarize, root cause, priority check,
  remediation, escalation); supports `--dry-run`, `--limit`, `--provider`, `--user-id`
- **`data/sample_incidents.json`** — 5 synthetic ServiceNow incident tickets for testing
  (API gateway 503, ML inference latency spike, ITSM OAuth failure, compliance data
  duplication, LLM prompt injection attempt)
- **`docs/POC_PLAYBOOK.md`** — two-week POC guide covering ServiceNow export steps,
  day-by-day run schedule, governance report interpretation, and feature backlog template

### Tests
- 31 new tests (140 total, up from 109) — `TestGetLatencyStats` (7),
  `TestGetProviderHealth` (8), `TestGetSessionActivity` (7), `TestCmdReport` (9)
- Coverage: 97.37% (gate: ≥90%)
