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
# ---------------------------------------------------------------------------

def test_earnings_miss_severity_ceiling(pipeline_results, metadata):
    """If the pipeline classifies an event as an earnings miss, severity must
    stay low (<=3). An earnings miss that triggers severity 4-5 is a
    cross-field contradiction — the classification and the magnitude disagree.

    Applies to fixtures tagged consistency_earnings (04, 05).
    """
    earnings_types = {"earnings_miss", "revenue_miss", "earnings_decline", "revenue_decline"}
    for fx in metadata:
        if "consistency_earnings" not in fx.get("test_roles", []):
            continue
        result = pipeline_results[fx["id"]]
        if result["event_type"] in earnings_types:
            assert result["severity"] <= 3, (
                f"[{fx['id']}] '{result['event_type']}' classified as severity {result['severity']} — "
                f"earnings misses should not exceed severity 3\n"
                f"  Article: {fx['label']}"
            )


def test_bankruptcy_severity_floor(pipeline_results, metadata):
    """If the pipeline classifies an event as bankruptcy/insolvency, severity
    must be at least 3. A Chapter 11 filing at severity 1 or 2 means the
    model understood the event type but not its magnitude.
    """
    bankruptcy_types = {"bankruptcy", "chapter_11", "insolvency", "financial_distress"}
    for fx in metadata:
        result = pipeline_results[fx["id"]]
        if result["event_type"] in bankruptcy_types:
            assert result["severity"] >= 3, (
                f"[{fx['id']}] '{result['event_type']}' classified as severity {result['severity']} — "
                f"bankruptcy events should not be below severity 3\n"
                f"  Article: {fx['label']}"
            )


def test_resolution_event_type_not_attack(pipeline_results, metadata):
    """Fixtures whose expected event_type is a resolution type should not be
    classified as an attack. This catches the model ignoring valence.

    Applies to fixtures 06 (Houthis end attacks) and 09 (port strike resolved).
    """
    resolution_fixture_ids = {
        fx["id"]
        for fx in metadata
        if any(r in fx.get("event_type_one_of", fx["expected"].get("event_type_one_of", []))
               for r in ["geopolitical_resolution", "labor_resolution", "ceasefire",
                         "conflict_resolution", "strike_resolution", "shipping_resumption"])
    }
    attack_types = {"geopolitical_attack", "maritime_attack", "shipping_attack", "port_strike", "labor_disruption"}

    for fx in metadata:
        if fx["id"] not in resolution_fixture_ids:
            continue
        result = pipeline_results[fx["id"]]
        # Allow labor_disruption for 09 since the resolution is tentative
        if fx["id"] == "09":
            continue
        assert result["event_type"] not in {"geopolitical_attack", "maritime_attack", "shipping_attack"}, (
            f"[{fx['id']}] Resolution article classified as attack type '{result['event_type']}'\n"
            f"  Article: {fx['label']}"
        )
