# POC Playbook — Two-Week ServiceNow Incident Analysis

## What you are doing and why

You are routing real incident ticket data through a local LLM (Llama 3.2 3B)
and capturing every prompt, response, latency, and token count in a structured
audit log. After two weeks you will have enough data to answer:

- Does the model give useful answers for each of the 5 analysis types?
- Which incident categories produce the most reliable responses?
- Where does the local model fail (context overflow, low-quality output)?
- What would this cost if run on GPT-4o instead?
- What features does the application still need (dashboard, truncation, scoring)?

---

## Prerequisites

```bash
cd /path/to/AI-Decision-Audit-Log
source .venv/bin/activate
```

Verify the model is loaded:

```bash
python -m src.main capture \
  --prompt "Reply with: ready" \
  --provider llama_cpp \
  --session-id ses-verify \
  --user-id poc-runner
```

---

## How to export incident tickets from ServiceNow

1. Log into your ServiceNow instance
2. Navigate to **Incident > All**
3. Apply any filters you want (date range, priority, state, category)
4. Right-click any column header → **Export** → **JSON** or **CSV**
5. Save the file to `data/incidents.json` (or `data/incidents.csv`)

**Recommended filters for Week 1:**
- Opened in the last 30 days
- State: Resolved or Closed (so you can compare AI analysis to actual resolution)
- Limit: 10–15 tickets to start

**Fields ServiceNow exports that this tool uses:**

| ServiceNow field | Used for |
|---|---|
| `number` | Session ID in the audit log |
| `short_description` | All 5 prompts |
| `description` | All 5 prompts |
| `priority` | Priority-check prompt |
| `assignment_group` | Escalation prompt |

---

## Week 1 — Baseline (Days 1–7)

**Goal:** Establish a clean baseline of model performance across different incident categories.

### Day 1 — Smoke test with sample data

```bash
# Dry-run first — verify prompts look right
python scripts/run_incidents.py --input scripts/sample_incidents.json --dry-run

# Run for real (5 tickets × 5 prompts = 25 captures, ~10 min on M2 Mini)
python scripts/run_incidents.py --input scripts/sample_incidents.json

# Check what was logged
python -m src.main report
```

### Days 2–7 — Real ServiceNow data (5–10 tickets/day)

```bash
# Export from ServiceNow, save to data/incidents.json, then:
python scripts/run_incidents.py --input data/incidents.json

# End-of-day check
python -m src.main report
python -m src.main query --errors-only
```

**What to note each day:**
- Are the summaries accurate and concise?
- Are root causes plausible?
- Are priority assessments consistent with how your team triages?
- Are remediation steps specific or generic?

---

## Week 2 — Stress Test (Days 8–14)

**Goal:** Surface failure modes, test cloud comparison, and identify missing features.

### Day 8 — Long ticket test (context pressure)

Export 3–5 tickets with very long description fields (major incidents, post-mortems).
These will reveal context-length failures on the 3B model.

```bash
python scripts/run_incidents.py --input data/long_incidents.json
python -m src.main query --errors-only  # look for context overflow errors
```

### Day 10 — Cloud comparison (OpenAI)

Run the same set of tickets through GPT-4o on one day to compare quality and cost.

```bash
python scripts/run_incidents.py --input data/incidents.json --provider openai
python -m src.main report  # TOKEN BURN section will show estimated cost
```

### Day 12 — Different user IDs (simulate a team)

```bash
python scripts/run_incidents.py --input data/incidents.json --user-id analyst-team
python scripts/run_incidents.py --input data/incidents.json --user-id sre-team
python -m src.main query --user-id analyst-team
```

### Day 14 — Final report and export

```bash
# Full governance report
python -m src.main report

# Export everything to JSON for offline analysis
python -m src.main export --format json --output data/poc_final_export.json

# Session breakdown
python -m src.main query
```

---

## What to look for in the governance report

### INCIDENT LOG section
- Any errors? What caused them?
- Context overflow errors → **feature needed: automatic ticket truncation**
- Rate limit errors (if using cloud) → **feature needed: retry with backoff**

### PROVIDER HEALTH section
- Is `llama_cpp` at 100%? If not, which tickets caused failures?
- Cloud provider below 90%? Investigate the error pattern.

### LATENCY PROFILE section
- p50 above 5,000ms → the model may be too slow for interactive use
- p95 / max much higher than p50 → long tickets are the problem
- **Feature needed if p95 > 10,000ms:** async batch processing, progress bar

### TOKEN BURN section
- Check the GPT-4o cost estimate after a full week of tickets
- This tells you whether local-only is worth the quality tradeoff
- **Typical finding:** local model costs $0.00 but GPT-4o at this volume costs $2–8/month

### SESSION ACTIVITY section
- Sessions with errors → those tickets need manual review
- Busiest sessions → which ticket categories generate the most AI work?

### ANOMALIES section
- Calls > 2× median latency → those ticket descriptions are too long
- **Action:** manually review those tickets and note the description length

---

## What features to add based on findings

Document your observations here during the POC. Typical findings:

| Observation | Feature to add |
|---|---|
| Long tickets cause context errors | Automatic description truncation to 1,500 chars |
| Model responses are generic for some categories | Per-category prompt templates |
| Hard to see full response in query output | `query --full` flag to show complete responses |
| Want to score model quality | Response rating field (`rating: 1-5`) on LogEntry |
| Want to visualize trends | Streamlit dashboard on top of SQLite |
| 25 prompts per run takes 15 min | Async/parallel execution for local model |

---

## Quick reference commands

```bash
# Run all sample tickets (dry-run)
python scripts/run_incidents.py --input scripts/sample_incidents.json --dry-run

# Run first 3 real tickets
python scripts/run_incidents.py --input data/incidents.json --limit 3

# Run everything
python scripts/run_incidents.py --input data/incidents.json

# Check errors
python -m src.main query --errors-only

# Session breakdown
python -m src.main query --session-id ses-INC0001001

# Full governance report
python -m src.main report

# Export to JSON
python -m src.main export --format json --output data/export.json
```
