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
│   ├── conftest.py         ← session-scoped pipeline runner with file cache
│   ├── test_structural.py  ← schema invariants (keys, types, value ranges)
│   ├── test_semantic.py    ← boundary + cross-field consistency assertions
│   ├── test_metamorphic.py ← relational assertions across fixture pairs
│   └── test_regression.py  ← distribution shift detection vs. baseline snapshot
├── snapshots/
│   └── baseline.json       ← committed pipeline outputs (generated once, then diffed)
└── scripts/
    ├── fetch_fixtures.py   ← scrape articles via Firecrawl
    └── generate_baseline.py ← run pipeline on all fixtures and commit the output
```

---

## Setup

```bash
# Install dependencies
uv sync

# Set your OpenAI key (or add to .env)
export OPENAI_API_KEY=sk-...
```

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
- `entity` contains the expected substring (case-insensitive)
- `event_type` is in the acceptable set for this fixture
- `severity` falls within the `[severity_min, severity_max]` band
- `confidence` respects declared floor/ceiling
- Cross-field: `earnings_miss` events must have `severity <= 3`
- Cross-field: `bankruptcy` events must have `severity >= 3`
- Cross-field: resolution articles must not be classified as attacks

### 3. Metamorphic (`test_metamorphic.py`)
Checks *how* outputs relate to each other, without asserting absolute values.

| Pair | Type | Assertion |
|---|---|---|
| 06 (Houthis end attacks) ↔ 02 (Houthis kill crew) | Negation | `severity(06) < severity(02)` |
| 09 (port strike resolved) ↔ 03 (port strike active) | Negation | `severity(09) < severity(03)` |
| 07 (Red Sea modest framing) ↔ 08 (Red Sea full escalation) | Monotonicity | `severity(07) <= severity(08)` |

These tests are model-agnostic — they don't care what the actual severity numbers are, only that the ordering is sensible.

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
