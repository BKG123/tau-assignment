"""Shared pytest fixtures.

The most important fixture is `pipeline_results` — a session-scoped dict
{fixture_id: pipeline_output} that runs the pipeline on all 10 articles exactly
once per test session and caches results to .cache/pipeline_results.json.

To force a fresh run (e.g. after changing the pipeline):
    FLUSH_CACHE=1 uv run pytest
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ROOT / "data" / "fixtures"
ARTICLES_DIR = FIXTURES_DIR / "articles"
METADATA_FILE = FIXTURES_DIR / "metadata.json"
CACHE_FILE = ROOT / ".cache" / "pipeline_results.json"


def _load_metadata() -> list[dict]:
    return json.loads(METADATA_FILE.read_text())


def _load_article(filename: str) -> str:
    return (ARTICLES_DIR / filename).read_text()


@pytest.fixture(scope="session")
def metadata() -> list[dict]:
    return _load_metadata()


@pytest.fixture(scope="session")
def pipeline_results() -> dict[str, dict]:
    """Run the pipeline on all fixtures, using a file cache between runs.

    Cache is invalidated by setting the FLUSH_CACHE env var:
        FLUSH_CACHE=1 uv run pytest
    """
    if CACHE_FILE.exists() and not os.environ.get("FLUSH_CACHE"):
        return json.loads(CACHE_FILE.read_text())

    # Lazy import so tests that don't need the LLM can still import cleanly
    from pipeline.pipeline import run_pipeline

    fixtures = _load_metadata()
    results: dict[str, dict] = {}

    for fx in fixtures:
        text = _load_article(fx["file"])
        print(f"\n  [pipeline] running fixture {fx['id']} — {fx['label']}")
        results[fx["id"]] = run_pipeline(text)

    CACHE_FILE.parent.mkdir(exist_ok=True)
    CACHE_FILE.write_text(json.dumps(results, indent=2))
    return results
