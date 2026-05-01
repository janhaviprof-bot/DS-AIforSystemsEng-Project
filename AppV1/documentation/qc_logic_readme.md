# QC Logic README

This document explains how Quality Control (QC) works in Signal Studio, including:

- what is scored,
- where scoring happens in the workflow,
- how each score is calculated,
- how values appear in UI and PDF output.

---

## 1) QC Components at a Glance

The system has three QC layers:

1. **Schema QC** (deterministic structural validation)  
   Implemented in `AppV1/agents/output_qc.py`.

2. **Marquee QC** (deterministic text-quality scoring for Global Insight output)  
   Implemented in `AppV1/modules/marquee_qc.py`.

3. **Composite Evidence Score** (weighted blended score)  
   Implemented in `AppV1/agents/output_qc.py` via `compute_composite_evidence_score(...)`.

All QC computations are deterministic Python logic (no extra LLM pass for QC scoring).

---

## 2) End-to-End Workflow

### Pipeline location

Main orchestration is in `AppV1/agents/workflow.py` inside:

- `run_multi_agent_workflow(section_packets, api_key)`

### Sequence

1. Run agent chain:
   - `agent1 = analyze_cross_section_links(...)`
   - `agent2 = evaluate_world_sentiment(...)`
   - `agent3 = validate_with_markets(...)`
2. Build workflow dict with:
   - `generated_at`
   - `agent1`, `agent2`, `agent3`
   - `market_snapshot`
   - `marquee_text`
   - `provenance`
3. Build output surface text:
   - `output_text = marquee_surface_text(workflow)` from `AppV1/modules/marquee_surface.py`
4. Compute marquee quality:
   - `workflow["marquee_qc"] = evaluate_marquee_quality(output_text, workflow, section_packets)`
5. Compute schema quality:
   - `qc_report = validate_workflow_outputs(...)`
   - `workflow["qc_report"] = qc_report.to_dict()`
6. Compute final blended confidence:
   - `workflow["composite_evidence_score"] = compute_composite_evidence_score(...)`

---

## 3) Marquee QC Logic (Global Insight text)

Implemented in `AppV1/modules/marquee_qc.py`.

### Inputs

- `output_text`: flattened Global Insight text surface
- `workflow`: agent outputs for mood/agreement context
- `section_packets`: structured source packets (briefs/headlines/summaries/sentiment)

### Metric pillars (1–5 each)

`_score_bundle(...)` computes:

1. **Semantic**
   - Token overlap between output text and source corpus.
   - Corpus built from section packet:
     - `brief` (trimmed),
     - first 3 headlines,
     - first 3 article summaries (trimmed).
   - Overlap thresholds:
     - `>= 0.40 -> 5`
     - `>= 0.30 -> 4`
     - `>= 0.20 -> 3`
     - `>= 0.10 -> 2`
     - else `1`

2. **Sentiment**
   - Compare normalized article net sentiment vs `agent2.world_mood_score / 100`.
   - If no sentiment totals, default `3`.
   - Absolute diff thresholds:
     - `<= 0.15 -> 5`
     - `<= 0.30 -> 4`
     - `<= 0.45 -> 3`
     - `<= 0.60 -> 2`
     - else `1`

3. **Grounding**
   - Extract capitalized entities from output via regex.
   - Score match ratio of those entities in source corpus.
   - If no entities found, default `3`.
   - Ratio thresholds:
     - `>= 0.80 -> 5`
     - `>= 0.60 -> 4`
     - `>= 0.40 -> 3`
     - `>= 0.20 -> 2`
     - else `1`

4. **Consistency**
   - `check_a`: market agreement vs mood magnitude heuristic.
   - `check_b`: lexical overlap between `agent1.cross_section_summary` and `agent3.final_insight`.
   - Final consistency = rounded average of `check_a` and `check_b`.

5. **Specificity**
   - Penalizes vague phrase hits (`VAGUE_PHRASES` list).
   - Rewards named entities and longer tokens.
   - Produces 1–5 based on rule buckets.

### Composite marquee score

- `score = round(sum(metrics.values()) / 25 * 100)` (0–100)
- Bands:
  - `>= 80`: `high` / "High confidence"
  - `>= 60`: `moderate` / "Moderate"
  - else: `low` / "Low confidence"

### Per-section scores

`evaluate_marquee_quality(...)` also computes section-specific scores:

- iterates section packets excluding `ALL`,
- re-scores each section with only that section packet as corpus,
- uses `fixed_consistency_score` from global consistency so section scores are comparable and do not double-penalize consistency drift.

Result shape:

- `marquee_qc.metrics`
- `marquee_qc.score`
- `marquee_qc.band`
- `marquee_qc.label`
- `marquee_qc.sections[section_name]`

---

## 4) Schema QC Logic (Workflow structure validation)

Implemented in `AppV1/agents/output_qc.py`.

### Output object

`validate_workflow_outputs(...)` returns `QCReport` with:

- `checks`: detailed pass/fail rows
- `schema_score_0_100`
- `warnings`
- `failed_required_count`

### What is validated

1. **Agent 1**
   - `agent1` is dict
   - `cross_section_summary` exists/min length
   - `connections` is list
   - optional connection item shape checks (`theme`, `sections`, `why_it_matters`, `trigger`)

2. **Agent 2**
   - `agent2` is dict
   - `world_mood_label` exists
   - `world_mood_score` in `[-100, 100]`
   - `market_stance` in allowed enum (`bullish`, `bearish`, `cautious`, `constructive`)
   - `description` exists/min length
   - optional `reasoning` non-empty if present

3. **Agent 3**
   - `agent3` is dict
   - `market_agreement` in enum (`aligned`, `mixed`, `divergent`, `unverified`, `partial alignment`)
   - `final_insight` exists/min length
   - optional `truth_checks` expectation if provenance says `agent3 == llm`

4. **Cross-consistency warnings**
   - warns when market bias unavailable/unexpected,
   - warns on tension between market bias and stance,
   - warns on suspicious agreement/stance combinations.

### Schema score formula

- Required checks only contribute to score.
- `schema_score_0_100 = round(100 * passed_required / total_required)`
- `failed_required_count` is count of required checks that failed.

---

## 5) Composite Evidence Score

Implemented in `compute_composite_evidence_score(...)` in `AppV1/agents/output_qc.py`.

Inputs:

- Schema score (0–100)
- Marquee score (0–100)
- Heuristic confidence (`workflow_confidence_heuristic(...)`)

Formula:

- `score = round(schema * 0.42 + marquee * 0.33 + confidence * 0.25)`

Then:

- clamp to `[0, 100]`,
- if any agent provenance is `fallback`, cap score at `70`.

---

## 6) Quick vs Full Pipeline Comparison

Implemented in `compare_quick_and_full(...)` in `AppV1/agents/output_qc.py`.

Used for reporting deltas from fast snapshot to full workflow:

- `world_mood_score`
- `connections_count`
- `market_agreement_changed`

This is attached to state as `compare_quick_full`.

---

## 7) App State Wiring

In `AppV1/app.py`, QC fields are held in `agent_workflow_state`:

- `marquee_qc`
- `qc_report`
- `compare_quick_full`
- `composite_evidence_score`

These are:

- initialized to `None`,
- preserved between refresh states when appropriate,
- filled once full pipeline finishes,
- cached in `agent_pipeline_cache` along with workflow and briefs.

---

## 8) UI Rendering

In `AppV1/ui/agent_views.py`:

- Global Insight header uses `marquee_qc_badge(...)`:
  - confidence `X/100`,
  - average metric rating `Y.Y/5`,
  - PDF download link.
- Section pills under ticker use `marquee_section_qc_row(...)`.

---

## 9) PDF Reporting

Download endpoint in `AppV1/app.py`:

- `@render.download(filename=lambda: qc_report_filename())`
- handler calls `generate_qc_report_pdf(...)`.

PDF generator in `AppV1/reporting/qc_pdf_report.py` renders:

- run metadata (report time, workflow time, refresh time),
- score summary badges,
- marquee metric pillars,
- per-section scores,
- schema QC summary/warnings,
- provenance,
- quick-vs-full deltas,
- metric definitions.

---

## 10) Deterministic vs LLM Responsibilities

- **Deterministic QC logic:** `marquee_qc.py`, `output_qc.py` (this document)
- **LLM content generation:** agent stages (`agent1/2/3`, section briefs) when available
- **Fallback mode:** agent provenance marks `fallback`; composite score is capped.

QC evaluates outputs from either LLM or fallback paths using the same deterministic rules.

---

## 11) Troubleshooting

1. **Marquee QC missing (`None`)**
   - likely quick snapshot path only; wait for full run completion.

2. **Schema QC low**
   - inspect `qc_report.checks` for failed required checks first.

3. **Section scores differ from global**
   - expected: per-section uses narrower corpus than combined global corpus.

4. **Composite score capped unexpectedly**
   - check `workflow.provenance` for any `fallback` values.

