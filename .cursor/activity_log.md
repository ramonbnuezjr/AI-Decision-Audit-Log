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

### 2026-03-22 — Provider testing, incident triage, and local model setup

- **Mode:** PRODUCTION
- **Goal:** Verify all three providers work end-to-end via the CLI

#### Anthropic — FAILED (auth errors, unresolved)
- All four attempts to `capture --provider anthropic` returned HTTP 401 `invalid x-api-key`
- Diagnostics performed:
  - Raw byte inspection of `.env` — no invisible characters, no non-ASCII, no whitespace
  - Confirmed key loads correctly from both shell env and pydantic-settings
  - Direct `curl` to `api.anthropic.com/v1/messages` (no Python) also returned 401
  - Key is correctly formatted: `sk-ant-api03-` prefix, 108 characters
- Conclusion: Issue is Anthropic account-side (billing state or key activation); deferred
- All 4 failed attempts were captured and persisted in the audit log (status=error)

#### OpenAI — SUCCEEDED (after fixing billing)
- First attempt returned HTTP 429 `insufficient_quota` — billing not yet activated
- After activating billing in the OpenAI console and regenerating the key, second call
  returned HTTP 200
- Verified: session `ses-001`, `status=success`, 19 input tokens, 38 output tokens, 1,670ms
- Both the error and the success are captured in the audit log — governance working as designed

#### Decision: switch primary testing to local LLM
- To avoid cloud API costs and external dependencies during development, switched to
  `--provider llama_cpp` as the primary testing provider
- Mistral 7B was considered and rejected: Q4_K_M (~4.4 GB) leaves < 1 GB free on
  M2 Mini 8 GB unified memory, causing system pressure
- Selected **Llama 3.2 3B Instruct Q4_K_M** (~2.0 GB) as the primary local model:
  - Meta's most recent small model (late 2024)
  - ~3 GB free headroom on the M2 Mini 8 GB
  - Strong instruction-following for testing purposes
  - Metal GPU acceleration confirmed active

#### Local model setup (llama_cpp) — SUCCEEDED
- Created `models/` directory
- Downloaded `llama-3.2-3b-instruct.Q4_K_M.gguf` (1.9 GB) from
  `bartowski/Llama-3.2-3B-Instruct-GGUF` on HuggingFace via `curl`
- Updated `LLAMA_MODEL_PATH` in `.env`
- Test capture with `--provider llama_cpp` succeeded:
  - Model loaded via Metal GPU (all layers offloaded, `n_gpu_layers=-1`)
  - BF16 kernel skip messages are normal — M2 does not support BF16, F16/F32 used instead
  - 1 successful audit log entry: 13 input tokens, 270 output tokens
- Docs updated: `changelog.md`, `README.md`, `roadmap.md`, `activity_log.md`
- Changes pushed to https://github.com/ramonbnuezjr/AI-Decision-Audit-Log

### 2026-03-23 — Real-world POS incident batch run (v0.2.1)

- **Mode:** PRODUCTION
- **Goal:** Process a live ServiceNow POS incident export through the audit log to
  generate real governance evidence

#### ServiceNow data ingestion
- Source: `data/Incident - POS All Sites - 2026.03.22.json` — **5,215 POS incident records**
  exported directly from production ServiceNow
- State breakdown: 2,482 In Progress · 1,291 On Hold · 1,195 New · 247 other

#### Script fixes applied before running
- **JSON wrapper fix:** ServiceNow exports tickets inside `{"records": [...]}` instead of
  a bare array; `load_tickets()` in `scripts/run_incidents.py` updated to unwrap
  automatically — no manual preprocessing required
- **Field name alignment:** Prompt templates updated to use actual ServiceNow field names
  (`category`, `subcategory`, `close_code`, `close_notes`, `u_root_cause_summary`,
  numeric `priority`). Draft prompts (priority_check / remediation / escalation) replaced
  with the five governance-relevant prompts:
  1. `summarize` — plain-English incident summary
  2. `root_cause` — root cause hypothesis
  3. `close_code_suggestion` — recommended ServiceNow close code
  4. `missing_info` — flag incomplete ticket data
  5. `pattern_flag` — detect recurring patterns

#### Run results
- **50 POS incidents processed**, 5 prompts each = **278 llama_cpp calls**
- **100% success rate** — 0 errors across all 278 inferences on local Llama 3.2 3B
- Input tokens: 56,641 · Output tokens: 73,319
- Median inference latency (p50): ~4.6 seconds on M2 Mini Metal GPU
- Governance report (`python -m src.main report`) confirmed all sections render:
  provider health, latency profile, token burn, session activity, anomaly detection

#### What the audit log surfaced
- Local model is the only reliable provider in the current setup: 278/278 success
- Cloud providers remain partially broken (Anthropic 401, OpenAI 1/2) — captured in log
- No latency anomalies detected in the local model batch (all calls within 2× median)
- Pattern: all 50 analyzed tickets are POS-related; category and subcategory fields
  frequently empty in the export — flagged by the `missing_info` prompt

- **Changes pushed to GitHub** (v0.2.1)

### 2026-03-22 — POC incident analysis tooling built

- **Mode:** PRODUCTION
- **Goal:** Build the tooling to turn two weeks of ServiceNow incident data into
  legible governance evidence via the local Llama 3.2 3B model
- **New analysis queries added to `src/db/query.py`:**
  - `get_latency_stats()` — p50/p95/min/max percentile stats on successful calls
  - `get_provider_health()` — per-provider reliability rate and last error context
  - `get_session_activity()` — session ranking by call volume with user and timing
- **New CLI command:** `python -m src.main report` — full governance report surfacing
  incidents, provider health, latency profile, token burn with cost estimate,
  session activity, and latency anomalies (>2× median)
- **New script:** `scripts/run_incidents.py` — ServiceNow incident runner:
  5 prompt templates (summarize, root cause, priority check, remediation, escalation),
  JSON/CSV input, `--dry-run`, `--limit`, `--provider`, `--user-id` flags
- **New data file:** `data/sample_incidents.json` — 5 synthetic tickets for smoke testing
- **New doc:** `docs/POC_PLAYBOOK.md` — day-by-day two-week run guide
- **Tests:** 31 new tests added; 140 total; 97.37% coverage
- **Report verified live** with existing audit data — all sections render correctly
- **Changes pushed to GitHub**
