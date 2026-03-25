# Roadmap

## v0.1 — MVP

- [x] Core directory structure and toolchain operational
- [x] Environment config loading via pydantic-settings (`src/config.py`)
- [x] `LogEntry` Pydantic model with all required fields (`src/models/log_entry.py`)
- [x] Anthropic SDK client wrapper with capture hook and error handling (`src/agent/agent.py`)
- [x] OpenAI SDK client wrapper with capture hook and error handling (`src/agent/agent.py`)
- [x] llama-cpp-python local model wrapper with lazy load + Metal GPU support (`src/agent/agent.py`)
- [x] AuditLogger pre/post hook middleware (`src/audit/logger.py`)
- [x] SQLite backend — schema, connection manager, INSERT (`src/db/`)
- [x] Query layer: `get_all_calls`, `get_by_session`, `get_by_user`, `get_errors`, `get_model_usage_summary`
- [x] CLI entrypoint: `capture`, `query`, `export`, `summary` commands (`src/main.py`)
- [x] Test suite — unit + integration, ≥90% coverage target

## v0.2 — Hardening

- [x] Coverage ≥90% verified clean — **98.35% (109 tests passed)**
- [x] README complete and accurate (badges, real repo URL, CLI examples)
- [x] Published to GitHub: https://github.com/ramonbnuezjr/AI-Decision-Audit-Log
- [x] Local model verified end-to-end: **Llama 3.2 3B Instruct Q4_K_M** on M2 Mini 8 GB
      via Metal GPU (`n_gpu_layers=-1`) — status=success, 1.9 GB model, ~3 GB free headroom
- [x] Provider incident log documented: Anthropic 401, OpenAI 429, Mistral 7B OOM — all
      captured in audit log and recorded in `changelog.md` / `activity_log.md`
- [x] POC incident analysis tooling complete (v0.2.0) — report command, incident runner, 140 tests, 97.37% coverage
- [x] First real-world batch run complete (v0.2.1) — 50 POS incidents × 5 prompts = 278 calls,
      100% success, zero errors, Llama 3.2 3B on M2 Mini Metal GPU; ServiceNow JSON wrapper
      and field name fixes applied; governance report verified against live data
- [x] Governance dashboard shipped (v0.3.0) — FastAPI + HTML Synthetic Sentinel frontend
      pixel-accurate to design mockup; Streamlit Option B retained; design system spec
      and mockup assets committed to `docs/`
- [ ] Pre-commit hooks passing cleanly (black, ruff, mypy, bandit)
- [ ] `mypy --strict` passing cleanly across all modules
- [ ] All secrets validated as present at startup; fail fast with clear error message
- [ ] Structured logging (structlog) wired throughout all layers
- [ ] JSONL export format support as alternative to JSON
- [ ] Date-range filter on `query` CLI command (`--since`, `--until`)
- [ ] `requirements.txt` generated from `pyproject.toml` for Docker/CI compatibility

## v1.0 — Production-Ready

- [ ] Cloud deployment configuration (Dockerfile or equivalent) — if/when needed
- [ ] CI pipeline (GitHub Actions) with lint + test + coverage gates
- [ ] Security audit passing (`bandit` + `pip-audit` clean)
- [ ] Full documentation in `docs/`
- [ ] CHANGELOG reflects all meaningful changes since bootstrap
- [ ] Package `AuditLogger` as a standalone pip library: `llm-audit-log`
- [ ] Performance: store write latency < 5ms p99 on local SQLite
- [ ] FastAPI query endpoint (v0.2 stretch goal → v1.0 target)

## Future / Product Seeds

- Streamlit governance dashboard on top of the SQLite DB
- Project 2: Policy-as-Code Guardrail Engine — uses this audit log as persistence layer for policy violations
- Project 3: RPAC (Role-Based AI Policy Control) — `session_id` + `user_id` pattern from this schema
