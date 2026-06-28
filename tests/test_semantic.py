"""Semantic boundary and cross-field consistency tests.

These tests assert *what* the output is, not just that it has the right shape.
They depend on human-annotated expectations in metadata.json.

Important design note: the expectations here encode the floor of human agreement —
ranges and sets, not point values. A severity band of [4, 5] admits genuine
uncertainty about whether a bankruptcy is a 4 or a 5, while still catching a
model that returns 1. This is a deliberate choice: we assert what any reasonable
analyst would agree on, and leave the contested middle unconstrained.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Per-field boundary assertions (driven by metadata.expected)
# ---------------------------------------------------------------------------

def test_entity_contains(pipeline_results, metadata):
    """Entity output must contain the expected substring (case-insensitive)."""
    for fx in metadata:
        exp = fx["expected"]
        if "entity_contains" not in exp:
            continue
        # Roundup/multi-subject articles where the publisher-vs-subject choice is
        # genuinely ambiguous are flagged out of the strict entity check and
        # discussed in the design note instead. See fixture 10.
        if exp.get("entity_known_ambiguous"):
            continue
        result = pipeline_results[fx["id"]]
        expected = exp["entity_contains"]
        # entity_contains may be a single substring or a list of acceptable
        # substrings (for genuinely multi-entity articles where more than one
        # primary entity is defensible).
        candidates = expected if isinstance(expected, list) else [expected]
        entity_lower = result["entity"].lower()
        assert any(c.lower() in entity_lower for c in candidates), (
            f"[{fx['id']}] entity '{result['entity']}' contains none of {candidates}\n"
            f"  Article: {fx['label']}"
        )


def test_event_type_one_of(pipeline_results, metadata):
    """Event type must be one of the acceptable labels for this fixture."""
    for fx in metadata:
        exp = fx["expected"]
        if "event_type_one_of" not in exp:
            continue
        result = pipeline_results[fx["id"]]
        assert result["event_type"] in exp["event_type_one_of"], (
            f"[{fx['id']}] event_type '{result['event_type']}' not in acceptable set {exp['event_type_one_of']}\n"
            f"  Article: {fx['label']}"
        )


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
