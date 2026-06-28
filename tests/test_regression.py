"""Regression / distribution-shift tests.

These tests compare a fresh pipeline run against a committed baseline snapshot
(snapshots/baseline.json). They detect model-side drift: silent API upgrades,
prompt changes, or dependency bumps that shift the pipeline's output behaviour
on the same fixed inputs.

What is NOT asserted here:
- That individual outputs match the baseline exactly (too brittle for LLM output)
- That the pipeline is "correct" in any absolute sense

What IS asserted:
- That the *distribution* of outputs hasn't shifted meaningfully
- That the confidence field is still discriminating (not uniformly high)
- That no single article's severity has spiked by more than 2 points

Design note: this catches model-side drift only. Input-side drift — the world's
news changing character over time — requires rotating the fixture set, which is
an eval maintenance problem beyond the scope of this suite.

To generate a baseline:
    uv run python scripts/generate_baseline.py

To run fresh (bypassing the pipeline cache):
    FLUSH_CACHE=1 uv run pytest tests/test_regression.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

BASELINE_FILE = Path(__file__).resolve().parents[1] / "snapshots" / "baseline.json"

MEAN_SEVERITY_TOLERANCE = 0.5       # baseline mean ± 0.5 severity points
HIGH_SEVERITY_RATE_TOLERANCE = 0.15 # baseline high-severity rate ± 15 percentage points
# Confidence scores must actually vary. The floor is intentionally low: 10
# clearly-written news articles legitimately cluster in a fairly narrow band
# (observed ~0.78–0.97). We only want to catch outright collapse to a single
# uniform value (variance → 0), not penalise a model that is well-calibrated
# on a deliberately clear fixture set.
CONFIDENCE_VARIANCE_FLOOR = 0.002
MAX_SINGLE_FIXTURE_DRIFT = 2        # no article should jump more than 2 severity points


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _severities(results: dict) -> list[float]:
    return [r["severity"] for r in results.values()]


def _confidences(results: dict) -> list[float]:
    return [r["confidence"] for r in results.values()]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return sum((v - m) ** 2 for v in values) / len(values)


def _high_severity_rate(results: dict) -> float:
    sevs = _severities(results)
    return sum(1 for s in sevs if s >= 4) / len(sevs)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def baseline() -> dict:
    if not BASELINE_FILE.exists():
        pytest.skip(
            "No baseline found. Run `uv run python scripts/generate_baseline.py` first."
        )
    return json.loads(BASELINE_FILE.read_text())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_mean_severity_stable(pipeline_results, baseline):
    current = _mean(_severities(pipeline_results))
    base = _mean(_severities(baseline))
    assert abs(current - base) < MEAN_SEVERITY_TOLERANCE, (
        f"Mean severity drifted beyond tolerance:\n"
        f"  baseline mean = {base:.2f}\n"
        f"  current mean  = {current:.2f}\n"
        f"  delta = {abs(current - base):.2f} (tolerance = {MEAN_SEVERITY_TOLERANCE})"
    )


def test_high_severity_rate_stable(pipeline_results, baseline):
    current = _high_severity_rate(pipeline_results)
    base = _high_severity_rate(baseline)
    assert abs(current - base) < HIGH_SEVERITY_RATE_TOLERANCE, (
        f"High-severity rate drifted:\n"
        f"  baseline = {base:.1%}\n"
        f"  current  = {current:.1%}\n"
        f"  delta = {abs(current - base):.1%} (tolerance = {HIGH_SEVERITY_RATE_TOLERANCE:.0%})"
    )


def test_confidence_variance_meaningful(pipeline_results):
    """Confidence must actually vary across fixtures.

    If variance drops near zero, the pipeline is returning a uniform score
    (e.g. 0.95 everywhere), which means the field has become meaningless
    as a signal. This test would catch a model change that removes
    discriminative behaviour even if individual outputs look plausible.
    """
    confs = _confidences(pipeline_results)
    var = _variance(confs)
    assert var > CONFIDENCE_VARIANCE_FLOOR, (
        f"Confidence variance collapsed to {var:.4f} — scores are too uniform: {confs}\n"
        f"This suggests confidence is no longer a meaningful signal."
    )


def test_no_large_per_fixture_severity_drift(pipeline_results, baseline):
    """No individual fixture should jump more than 2 severity points vs baseline.

    A 3-point swing (e.g. from 2 to 5) on a fixed article is a strong signal
    that something material changed in the pipeline, not just random variation.
    """
    for fid, current in pipeline_results.items():
        if fid not in baseline:
            continue
        delta = abs(current["severity"] - baseline[fid]["severity"])
        assert delta <= MAX_SINGLE_FIXTURE_DRIFT, (
            f"[{fid}] Severity drifted by {delta} points:\n"
            f"  baseline = {baseline[fid]['severity']}\n"
            f"  current  = {current['severity']}"
        )
