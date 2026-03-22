# Project Instructions

## Project Overview
`ai-decision-audit-log` intercepts and persists AI model decisions — including the full request
payload, response, model metadata, timestamps, and caller context — into a queryable local audit
store. It provides a CLI for browsing, filtering, and exporting audit entries, giving engineers
full observability into every instrumented AI call.

## Project Mode
**Current Mode: PRODUCTION**
> To switch modes, update this line and add a note in activity_log.md.

## Supported Features
- Wrap Anthropic and OpenAI SDK calls to capture full decision context
- Persist log entries to a local SQLite database (or JSONL flat file)
- Query entries by model, date range, caller tag, and status
- Export filtered entries to JSON or CSV
- Structured logging of all internal operations via structlog

## Non-Goals
- Real-time streaming dashboards or live monitoring UI
- Cloud-hosted audit storage or remote sync
- Model fine-tuning or training data pipelines
- Replay/re-execution of captured decisions
- Multi-tenant or multi-user access control

## Key Dependencies
- Python 3.11+
- Anthropic SDK (`anthropic==0.28.0`)
- OpenAI SDK (`openai==1.35.0`)
- MCP stub (`mcp==1.0.0`) — TBD, not yet active
- Pydantic v2 (`pydantic==2.7.4`) for all data validation and log entry models
- pydantic-settings (`pydantic-settings==2.3.4`) for environment config
- structlog (`structlog==24.2.0`) for structured logging
- Raspberry Pi GPIO (conditionally enabled via `HARDWARE_ENABLED=false`)

## How Cursor Should Behave
- Read this file, `architecture.md`, and `roadmap.md` before any structural change.
- Reference all `rules/*.mdc` files on every generation.
- Flag ambiguity before acting, not after.
- Never generate incomplete placeholder code in `src/`.
- Tests live in `tests/` mirroring `src/` structure exactly.
- All secrets via environment variables — see `.env.example`.
- The audit store path and format are runtime-configurable via env vars; never hardcode paths.
