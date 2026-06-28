"""Semantic boundary and cross-field consistency tests.

These tests assert *what* the output is, not just that it has the right shape.

Design decision — what we deliberately do NOT assert here:
We intentionally do not assert entity or event_type correctness. Both would
require matching against ground truth that does not cleanly exist:
  - Entity: multi-actor articles have several defensible "primary" entities,
    and roundup articles confuse publisher with subject.
  - Event type: there is no canonical taxonomy, so matching against a
    hand-picked set asserts correctness against an ontology we invented.
Structural tests still guarantee both fields are non-empty strings, and the
cross-field consistency checks below verify event_type is coherent with
severity. That is as far as we go without inventing ground truth.

What we DO assert:
  - Severity and confidence fall within wide "floor of agreement" bands.
    These are ranges, not point values — a severity band of [4, 5] admits
    genuine uncertainty about whether a bankruptcy is a 4 or a 5 while still
    catching a model that returns 1.
  - Cross-field consistency: the model's own outputs must not contradict
    each other (these need no ground truth at all).
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Per-field boundary assertions (driven by metadata.expected)
# ---------------------------------------------------------------------------

def test_severity_within_bounds(pipeline_results, metadata):
    """Severity must fall within the [severity_min, severity_max] band."""
    for fx in metadata:
        exp = fx["expected"]
        result = pipeline_results[fx["id"]]
        if "severity_min" in exp:
            assert result["severity"] >= exp["severity_min"], (
                f"[{fx['id']}] severity {result['severity']} below floor {exp['severity_min']}\n"
                f"  Article: {fx['label']}"
            )
        if "severity_max" in exp:
            assert result["severity"] <= exp["severity_max"], (
                f"[{fx['id']}] severity {result['severity']} above ceiling {exp['severity_max']}\n"
                f"  Article: {fx['label']}"
            )


def test_confidence_within_bounds(pipeline_results, metadata):
    """Confidence must respect declared floor and/or ceiling."""
    for fx in metadata:
        exp = fx["expected"]
        result = pipeline_results[fx["id"]]
        if "confidence_min" in exp:
            assert result["confidence"] >= exp["confidence_min"], (
                f"[{fx['id']}] confidence {result['confidence']:.3f} below floor {exp['confidence_min']}\n"
                f"  Article: {fx['label']}"
            )
        if "confidence_max" in exp:
            assert result["confidence"] <= exp["confidence_max"], (
                f"[{fx['id']}] confidence {result['confidence']:.3f} above ceiling {exp['confidence_max']}\n"
                f"  Article: {fx['label']}"
            )


# ---------------------------------------------------------------------------
# Cross-field consistency checks
#
# These need no ground truth: they assert the model's own event_type does not
# contradict its own severity. To stay robust against an open taxonomy, family
# membership is decided by keyword/substring matching on the event_type the
# model emitted — not by exact-string sets. That way a synonym the test author
# never enumerated (e.g. "earnings_shortfall", "corporate_bankruptcy") still
# triggers the check instead of passing vacuously.
# ---------------------------------------------------------------------------

def _event_type_matches(event_type: str, any_of: tuple[str, ...], all_of: tuple[str, ...] = ()) -> bool:
    """True if `event_type` contains any of `any_of` and all of `all_of` (case-insensitive)."""
    et = event_type.lower()
    any_ok = any(kw in et for kw in any_of) if any_of else True
    all_ok = all(kw in et for kw in all_of) if all_of else True
    return any_ok and all_ok


def _is_earnings_family(event_type: str) -> bool:
    return _event_type_matches(
        event_type,
        any_of=("miss", "decline", "shortfall", "drop", "fall", "soft", "weak"),
        all_of=(),
    ) and _event_type_matches(event_type, any_of=("earning", "revenue", "profit", "sales"))


def _is_bankruptcy_family(event_type: str) -> bool:
    return _event_type_matches(
        event_type,
        any_of=("bankrupt", "chapter_11", "chapter11", "chapter_eleven",
                "insolven", "liquidation", "receivership", "distress"),
    )


def _is_resolution_family(event_type: str) -> bool:
    return _event_type_matches(
        event_type,
        any_of=("resolution", "ceasefire", "resumption", "settle", "agreement",
                "deescalation", "de_escalation"),
    )


def _is_active_negative_family(event_type: str) -> bool:
    """Active hostile/disruptive events — the opposite valence of a resolution."""
    return _event_type_matches(event_type, any_of=("attack", "assault", "strike"))


def test_earnings_severity_ceiling(pipeline_results, metadata):
    """If the model classifies an event as an earnings/revenue miss or decline,
    severity must stay low (<=3). An earnings miss scored 4-5 is a cross-field
    contradiction: the classification and the magnitude disagree.

    Ground-truth-free — fires on whichever fixtures the model itself labels as
    an earnings-family event, matched by keyword rather than a fixed string set.
    """
    for fx in metadata:
        result = pipeline_results[fx["id"]]
        if _is_earnings_family(result["event_type"]):
            assert result["severity"] <= 3, (
                f"[{fx['id']}] '{result['event_type']}' classified as severity {result['severity']} — "
                f"earnings/revenue misses should not exceed severity 3\n"
                f"  Article: {fx['label']}"
            )


def test_bankruptcy_severity_floor(pipeline_results, metadata):
    """If the model classifies an event as bankruptcy/insolvency, severity must
    be at least 3. A Chapter 11 filing at severity 1-2 means the model read the
    event type but not its magnitude.
    """
    for fx in metadata:
        result = pipeline_results[fx["id"]]
        if _is_bankruptcy_family(result["event_type"]):
            assert result["severity"] >= 3, (
                f"[{fx['id']}] '{result['event_type']}' classified as severity {result['severity']} — "
                f"bankruptcy events should not be below severity 3\n"
                f"  Article: {fx['label']}"
            )


def test_resolution_event_type_not_active_negative(pipeline_results, metadata):
    """Fixtures whose *expected* event_type is a resolution must not be classified
    as an active attack/strike. This catches the model ignoring valence
    (e.g. reading "Houthis end attacks" as an attack).

    Discovery is metadata-driven: a fixture is in scope when its declared
    event_type_one_of contains a resolution-family label. Fixtures flagged
    `event_type_known_ambiguous` (e.g. 09, whose source is framed as impact
    analysis rather than a clean resolution) are excluded in data, not via a
    hardcoded fixture id.
    """
    for fx in metadata:
        if fx["expected"].get("event_type_known_ambiguous"):
            continue
        expected_types = fx["expected"].get("event_type_one_of", [])
        if not any(_is_resolution_family(t) for t in expected_types):
            continue
        result = pipeline_results[fx["id"]]
        assert not _is_active_negative_family(result["event_type"]), (
            f"[{fx['id']}] Resolution article classified as active-negative "
            f"type '{result['event_type']}'\n"
            f"  Article: {fx['label']}"
        )
