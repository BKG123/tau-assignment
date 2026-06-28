# TauAssignment — Risk Signal Pipeline & Eval Suite

A pipeline that reads unstructured news articles and outputs structured risk signals `{entity, event_type, severity, confidence}`, alongside an eval suite that tests it without clean ground truth.

---

## Project Structure

```
project/
├── data/fixtures/
│   ├── articles/           ← 10 raw scraped news articles
│   └── metadata.json       ← fixture registry with expected values, test roles, and metamorphic pairs
├── pipeline/
│   └── pipeline.py         ← article → {entity, event_type, severity, confidence}
├── tests/
│   ├── conftest.py         ← session-scoped pipeline runner, file cache, and Markdown results reporter
│   ├── test_structural.py  ← schema invariants (keys, types, value ranges)
│   ├── test_semantic.py    ← boundary + cross-field consistency assertions
│   ├── test_metamorphic.py ← relational assertions across fixture pairs
│   └── test_regression.py  ← distribution shift detection vs. baseline snapshot
├── snapshots/
│   └── baseline.json       ← committed pipeline outputs (generated once, then diffed)
├── test-results/
│   └── results.md          ← Markdown test report written after every pytest run
├── scripts/
│   ├── fetch_fixtures.py   ← scrape articles via Firecrawl
│   └── generate_baseline.py ← run pipeline on all fixtures and commit the output
└── main.py                 ← CLI to run the pipeline on any article file
```

---

## Setup

```bash
# Install dependencies
uv sync

# Set your OpenAI key (or add to .env — see .env.example)
export OPENAI_API_KEY=sk-...
```

The pipeline defaults to `gpt-5.4-mini`. Override it with `--model` on the CLI or `model=` when calling `run_pipeline()` directly.

---

## Running the Pipeline

Run the extractor on any article text file:

```bash
uv run python main.py data/fixtures/articles/01_stg_logistics_bankruptcy.txt
```

Example output:

```json
{
  "entity": "STG Logistics, Inc.",
  "event_type": "chapter_11",
  "severity": 4,
  "confidence": 0.97
}
```

Use a different model:

```bash
uv run python main.py path/to/article.txt --model gpt-5.4-mini
```

The file should contain raw article text (plain text or scraped markdown). For fetching articles from URLs, use `scripts/fetch_fixtures.py` first, then point `main.py` at the saved file.

---

## Running the Tests

```bash
# Run the full suite
uv run pytest

# Run a specific layer
uv run pytest tests/test_structural.py
uv run pytest tests/test_semantic.py
uv run pytest tests/test_metamorphic.py
uv run pytest tests/test_regression.py   # requires baseline.json (see below)

# Force a fresh pipeline run (bypass cache)
FLUSH_CACHE=1 uv run pytest
```

### Test Caching

The pipeline makes LLM calls, which are slow and cost money. Results are cached to `.cache/pipeline_results.json` after the first run. Subsequent runs load from cache — no LLM calls made.

**Cache is invalidated by:**
- `FLUSH_CACHE=1 uv run pytest` — forces re-run
- Running `generate_baseline.py` — deletes cache so next test run is fresh
- `rm .cache/pipeline_results.json` — manual delete

> If you change an article or the pipeline prompt, always use `FLUSH_CACHE=1` to get fresh results.

### Test Report

After every pytest run, `conftest.py` writes a full Markdown report to `test-results/results.md` with pass/fail counts, per-test duration, and failure details.

It also prints a `PIPELINE OUTPUTS` table at the end of the terminal session showing each fixture's actual `entity`, `event_type`, `severity`, and `confidence` alongside its expected bounds — useful for a quick sanity check after a fresh run.

---

## Generating / Updating the Baseline

`test_regression.py` diffs fresh output against a committed baseline snapshot. Generate it once when you're satisfied with the pipeline's behavior:

```bash
uv run python scripts/generate_baseline.py
```

This runs the pipeline on all 10 fixtures, prints each output, writes `snapshots/baseline.json`, and flushes the session cache. Commit `baseline.json` — it becomes the reference point for all future regression checks.

When you intentionally update the pipeline, regenerate the baseline explicitly:

```bash
uv run python scripts/generate_baseline.py
# review the diff in snapshots/baseline.json
git add snapshots/baseline.json && git commit -m "update baseline after pipeline change"
```

This makes distribution drift a **visible, deliberate decision** rather than silent accumulation.

---

## The Four Test Layers

### 1. Structural (`test_structural.py`)
Schema-only checks. Runs on all 10 fixtures. No knowledge of expected values.
- Output has exactly the four required keys
- `entity` and `event_type` are non-empty strings
- `severity` is an integer in `[1, 5]`
- `confidence` is a float in `[0.0, 1.0]`

### 2. Semantic (`test_semantic.py`)
Checks *what* the output is against human-annotated expectations in `metadata.json`.

**Deliberately NOT checked here:** `entity` and `event_type` correctness. Multi-actor articles have several defensible primary entities, and there is no canonical event-type taxonomy — so asserting either field against a hand-picked set would be asserting correctness against an ontology we invented. Structural tests still guarantee both are non-empty strings; the cross-field checks below verify `event_type` is internally coherent with `severity`.

**What IS checked:**
- `severity` falls within the `[severity_min, severity_max]` band declared in `metadata.json`
- `confidence` respects declared floor/ceiling
- Cross-field: if the model labels an event as an earnings/revenue miss or decline, `severity <= 3`
- Cross-field: if the model labels an event as bankruptcy/insolvency, `severity >= 3`
- Cross-field: fixtures whose expected type is a resolution family must not be classified as an active attack

Keyword matching (not exact strings) is used for cross-field checks so synonyms the test author never enumerated still trigger the assertion.

### 3. Metamorphic (`test_metamorphic.py`)
Checks *how* outputs relate to each other, without asserting absolute values. Pairs are declared in `metadata.json` and discovered programmatically — no hardcoded fixture IDs in the test runner.

| Pair | Type | Assertion |
|---|---|---|
| 06 (Houthis end attacks) ↔ 02 (Houthis kill crew) | Negation | `severity(06) < severity(02)` |
| 09 (port strike resolved) ↔ 03 (port strike active) | Negation | `severity(09) <= severity(03)` |
| 07 (Red Sea modest framing) ↔ 08 (Red Sea full escalation) | Monotonicity | `severity(07) <= severity(08)` |
| 07 (Red Sea hedged WEF overview) ↔ 02 (Houthi fatal attack) | Confidence | `confidence(07) < confidence(02)` |

These tests are model-agnostic — they don't care what the actual numbers are, only that the ordering is sensible.

### 4. Regression (`test_regression.py`)
Compares fresh output distribution against `snapshots/baseline.json`.
- Mean severity hasn't shifted by more than 0.5 points
- Proportion of high-severity outputs (≥ 4) hasn't shifted by more than 15%
- Confidence variance hasn't collapsed — uniform scores signal the field lost meaning
- No individual fixture has jumped more than 2 severity points vs. baseline

---

## Fetching Articles (if re-scraping)

```bash
export FIRECRAWL_API_KEY=fc-...
uv run python scripts/fetch_fixtures.py            # fetch all missing/empty files
uv run python scripts/fetch_fixtures.py --force    # re-fetch everything
uv run python scripts/fetch_fixtures.py --ids 02 06 # specific fixtures only
```
