#!/usr/bin/env python3
"""Generate snapshots/baseline.json by running the pipeline on all fixtures.

Run this once when you're satisfied with the pipeline's output. Commit the
result. From then on, test_regression.py will diff every fresh run against
this file, making distribution drift a visible, explicit decision rather
than silent accumulation.

To regenerate after an intentional pipeline change:
    uv run python scripts/generate_baseline.py

This also flushes the session cache (.cache/pipeline_results.json) so the
next test run picks up fresh results.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.pipeline import run_pipeline  # noqa: E402

FIXTURES_DIR = ROOT / "data" / "fixtures"
ARTICLES_DIR = FIXTURES_DIR / "articles"
METADATA_FILE = FIXTURES_DIR / "metadata.json"
SNAPSHOTS_DIR = ROOT / "snapshots"
CACHE_FILE = ROOT / ".cache" / "pipeline_results.json"


def main() -> int:
    metadata = json.loads(METADATA_FILE.read_text())
    SNAPSHOTS_DIR.mkdir(exist_ok=True)

    results: dict[str, dict] = {}
    failures: list[str] = []

    for fx in metadata:
        path = ARTICLES_DIR / fx["file"]
        if not path.exists():
            print(f"[{fx['id']}] SKIP — file not found: {fx['file']}")
            continue

        print(f"[{fx['id']}] {fx['label']}")
        try:
            output = run_pipeline(path.read_text())
            results[fx["id"]] = output
            print(f"       entity={output['entity']!r}  event_type={output['event_type']!r}"
                  f"  severity={output['severity']}  confidence={output['confidence']:.2f}")
        except Exception as exc:
            print(f"       ERROR: {exc}")
            failures.append(fx["id"])

    if failures:
        print(f"\n{len(failures)} fixture(s) failed: {failures}")
        return 1

    out = SNAPSHOTS_DIR / "baseline.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nBaseline written → {out}")

    # Flush the session cache so tests immediately pick up these new results
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
        print(f"Session cache cleared → {CACHE_FILE}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
