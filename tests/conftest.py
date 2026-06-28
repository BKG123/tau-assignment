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
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ROOT / "data" / "fixtures"
ARTICLES_DIR = FIXTURES_DIR / "articles"
METADATA_FILE = FIXTURES_DIR / "metadata.json"
CACHE_FILE = ROOT / ".cache" / "pipeline_results.json"
RESULTS_DIR = ROOT / "test-results"
RESULTS_FILE = RESULTS_DIR / "results.md"

_LAYER_KEYS = [
    ("test_structural", "Structural"),
    ("test_semantic", "Semantic"),
    ("test_metamorphic", "Metamorphic"),
    ("test_regression", "Regression"),
]
_LAYER_ORDER = [label for _, label in _LAYER_KEYS] + ["Other"]


def _get_layer(nodeid: str) -> str:
    for key, label in _LAYER_KEYS:
        if key in nodeid:
            return label
    return "Other"


@dataclass
class _TestRecord:
    nodeid: str
    outcome: str
    duration: float = 0.0
    failure: str | None = None


@dataclass
class _SessionResults:
    started_at: datetime | None = None
    records: dict[str, _TestRecord] = field(default_factory=dict)


_session_results = _SessionResults()
_session_start: float | None = None


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


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" and not (report.failed and report.when == "setup"):
        return

    record = _session_results.records.setdefault(
        item.nodeid,
        _TestRecord(nodeid=item.nodeid, outcome="passed"),
    )
    record.duration += report.duration

    if report.failed:
        record.outcome = "failed"
        record.failure = str(report.longrepr)
    elif report.skipped:
        record.outcome = "skipped"
    elif record.outcome != "failed":
        record.outcome = report.outcome


def _format_duration(seconds: float) -> str:
    if seconds >= 1:
        return f"{seconds:.3f}s"
    return f"{seconds * 1000:.0f}ms"


def _status_icon(outcome: str) -> str:
    return {
        "passed": "passed",
        "failed": "failed",
        "skipped": "skipped",
        "error": "error",
    }.get(outcome, outcome)


def _metamorphic_annotation(test_name: str, pipeline_data: dict) -> str:
    """Parse a metamorphic test node id and return an actual-values annotation.

    E.g. 'test_metamorphic_relationship[06-severity_lt-02]'
      → '(06 severity=4 < 02 severity=5)'
    """
    m = re.match(r"test_metamorphic_relationship\[(\w+)-(\w+)_(\w+)-(\w+)\]", test_name)
    if not m:
        return ""
    id_a, field_name, op, id_b = m.group(1), m.group(2), m.group(3), m.group(4)
    val_a = pipeline_data.get(id_a, {}).get(field_name)
    val_b = pipeline_data.get(id_b, {}).get(field_name)
    if val_a is None or val_b is None:
        return ""
    op_sym = {"lt": "<", "lte": "≤", "gt": ">", "gte": "≥"}.get(op, op)
    fmt = ".2f" if field_name == "confidence" else ""
    return f"({id_a} {field_name}={val_a:{fmt}} {op_sym} {id_b} {field_name}={val_b:{fmt}})"


def _write_markdown_results(exitstatus: int, session_duration: float) -> None:
    records = sorted(_session_results.records.values(), key=lambda r: r.nodeid)
    counts: dict[str, int] = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    for record in records:
        counts[record.outcome] = counts.get(record.outcome, 0) + 1

    total = len(records)
    total_duration = session_duration or sum(r.duration for r in records)
    finished = datetime.now(timezone.utc)
    started = _session_results.started_at or finished
    started_local = started.astimezone()
    finished_local = finished.astimezone()
    overall = "passed" if exitstatus == 0 else "failed"

    # Load pipeline outputs for the inline table and metamorphic annotations
    pipeline_data: dict | None = None
    fixtures: list | None = None
    try:
        if CACHE_FILE.exists():
            pipeline_data = json.loads(CACHE_FILE.read_text())
            fixtures = _load_metadata()
    except Exception:
        pass

    # Group records by layer
    layer_records: dict[str, list[_TestRecord]] = {l: [] for l in _LAYER_ORDER}
    for record in records:
        layer_records[_get_layer(record.nodeid)].append(record)

    # ------------------------------------------------------------------ header
    lines = [
        f"# Test Results — {finished_local:%Y-%m-%d %H:%M:%S %Z}",
        "",
        f"- **Started:** {started_local.isoformat(timespec='seconds')}",
        f"- **Finished:** {finished_local.isoformat(timespec='seconds')}",
        f"- **Duration:** {_format_duration(total_duration)}",
        f"- **Status:** {overall} ({counts['passed']} passed, "
        f"{counts['failed']} failed, {counts['skipped']} skipped, "
        f"{counts['error']} errors)",
        "",
    ]

    # ---------------------------------------------------------- layer summary
    lines += [
        "## Summary",
        "",
        "| Layer | Tests | Passed | Failed |",
        "| --- | ---: | ---: | ---: |",
    ]
    for layer in _LAYER_ORDER:
        recs = layer_records[layer]
        if not recs:
            continue
        p = sum(1 for r in recs if r.outcome == "passed")
        f = sum(1 for r in recs if r.outcome == "failed")
        lines.append(f"| {layer} | {len(recs)} | {p} | {f} |")
    lines.append(
        f"| **Total** | **{total}** | **{counts['passed']}** | **{counts['failed']}** |"
    )

    # --------------------------------------------------- pipeline outputs table
    if pipeline_data and fixtures:
        lines += [
            "",
            "## Pipeline Outputs",
            "",
            "| id | label | entity | event\_type | sev | conf | sev band | conf floor |",
            "| --- | --- | --- | --- | ---: | ---: | :---: | :--- |",
        ]
        for fx in fixtures:
            r = pipeline_data.get(fx["id"])
            if not r:
                continue
            exp = fx["expected"]
            sev_min = exp.get("severity_min", "—")
            sev_max = exp.get("severity_max", "—")
            sev_band = f"[{sev_min}–{sev_max}]"
            conf_parts = []
            if "confidence_min" in exp:
                conf_parts.append(f"≥{exp['confidence_min']}")
            if "confidence_max" in exp:
                conf_parts.append(f"≤{exp['confidence_max']}")
            conf_floor = ", ".join(conf_parts) if conf_parts else "—"
            entity = r["entity"][:30]
            etype = r["event_type"][:24]
            label = fx["label"][:42]
            lines.append(
                f"| {fx['id']} | {label} | {entity} | {etype} "
                f"| {r['severity']} | {r['confidence']:.2f} | {sev_band} | {conf_floor} |"
            )

    # ---------------------------------------------------------- tests by layer
    lines += ["", "## Tests", ""]
    for layer in _LAYER_ORDER:
        recs = layer_records[layer]
        if not recs:
            continue
        lines += [
            f"### {layer}",
            "",
            "| Test | Status | Duration |",
            "| --- | --- | ---: |",
        ]
        for record in recs:
            test_name = record.nodeid.split("::", 1)[-1]
            annotation = ""
            if layer == "Metamorphic" and pipeline_data:
                annotation = _metamorphic_annotation(test_name, pipeline_data)
            cell = f"`{test_name}`"
            if annotation:
                cell += f" {annotation}"
            lines.append(
                f"| {cell} | {_status_icon(record.outcome)} | "
                f"{_format_duration(record.duration)} |"
            )
        lines.append("")

    # --------------------------------------------------------------- failures
    failures = [r for r in records if r.failure]
    lines += ["## Failures", ""]
    if failures:
        for record in failures:
            test_name = record.nodeid.split("::", 1)[-1]
            lines += [
                f"### `{test_name}`",
                "",
                "```",
                record.failure or "",
                "```",
                "",
            ]
    else:
        lines.append("_None_")

    content = "\n".join(lines) + "\n"
    RESULTS_DIR.mkdir(exist_ok=True)
    RESULTS_FILE.write_text(content)

    # Also write a timestamped copy so history is preserved
    timestamp = finished_local.strftime("%Y%m%d_%H%M%S")
    (RESULTS_DIR / f"results_{timestamp}.md").write_text(content)


def pytest_sessionstart(session):
    global _session_start
    _session_start = time.perf_counter()
    _session_results.started_at = datetime.now(timezone.utc)


def pytest_sessionfinish(session, exitstatus):
    duration = time.perf_counter() - _session_start if _session_start else 0.0
    _write_markdown_results(exitstatus, duration)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Print a table of every fixture's pipeline output vs. its expected bounds.

    Gives a single at-a-glance view of what the pipeline produced this run,
    rendered after the test results.
    """
    if not CACHE_FILE.exists():
        return
    try:
        results = json.loads(CACHE_FILE.read_text())
        fixtures = _load_metadata()
    except Exception:
        return

    tr = terminalreporter
    tr.write_sep("=", "PIPELINE OUTPUTS")
    header = f"{'id':<3} {'entity':<26} {'event_type':<22} {'sev':>3} {'conf':>5}  expected"
    tr.write_line(header)
    tr.write_line("-" * len(header))

    for fx in fixtures:
        r = results.get(fx["id"])
        if not r:
            continue
        exp = fx["expected"]
        sev_band = f"sev[{exp.get('severity_min', '-')}-{exp.get('severity_max', '-')}]"
        conf_band = ""
        if "confidence_min" in exp:
            conf_band += f" conf>={exp['confidence_min']}"
        if "confidence_max" in exp:
            conf_band += f" conf<={exp['confidence_max']}"
        entity = (r["entity"][:25]) if len(r["entity"]) > 25 else r["entity"]
        etype = (r["event_type"][:21]) if len(r["event_type"]) > 21 else r["event_type"]
        tr.write_line(
            f"{fx['id']:<3} {entity:<26} {etype:<22} {r['severity']:>3} "
            f"{r['confidence']:>5.2f}  {sev_band}{conf_band}"
        )
