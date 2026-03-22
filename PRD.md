# Product Requirements Document — ai-decision-audit-log

## Problem Statement

AI model calls are opaque by default. When an application calls Anthropic or OpenAI,
there is no built-in, structured, queryable record of what prompt was sent, what was
returned, which model was used, how long it took, or which part of the system triggered
the call. This makes debugging, auditing, and governance of AI-powered systems
unnecessarily difficult. `ai-decision-audit-log` solves this by providing a lightweight,
drop-in capture layer that intercepts every instrumented AI call and persists a full
decision record to a local, queryable audit store — without changing the caller's code.

## Core User Flow

1. Developer instruments their AI call by routing it through the capture-layer client
   (e.g., `AuditedAnthropicClient` instead of raw `anthropic.Anthropic()`).
2. The capture layer transparently forwards the call to the AI provider and records
   the full context: prompt, response, model, token counts, latency, timestamp, and
   caller-supplied tags.
3. The `LogEntry` Pydantic model is validated and written to the local audit store
   (SQLite by default).
4. The developer queries the audit store via CLI:
   - `python -m src.main query --model claude-sonnet --since 2026-01-01`
   - `python -m src.main export --format json --output ./audit_export.json`
5. Entries are returned in structured format, filterable by model, date range, caller tag,
   and completion status.

## Non-Goals

- Real-time streaming dashboards or live web UI
- Cloud-hosted audit storage or remote sync
- Model fine-tuning or training data pipelines from captured entries
- Replay or re-execution of captured decisions
- Multi-tenant or multi-user access control
- Automatic PII redaction (callers are responsible for sanitizing prompts before capture)

## Success Criteria

- [ ] Audit log captures 100% of calls made through instrumented clients (zero silent drops)
- [ ] Every `LogEntry` is queryable by model name, date range, and caller tag
- [ ] Audit store survives process restart; no entries lost on shutdown
- [ ] Store write adds < 5ms overhead p99 to any instrumented call (local SQLite)
- [ ] CLI `query` and `export` commands return results within 1s for stores up to 100k entries
- [ ] `mypy --strict` passes cleanly; coverage ≥90% on all core modules

---
*Engineering rules live in `.cursor/rules/`. This document is scope-only.*
