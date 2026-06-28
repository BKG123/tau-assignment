"""Structural invariant tests.

These tests check schema correctness only — no knowledge of what the values
*should* be. They run on every fixture and are the first line of defence against
a pipeline change that breaks output format.

A pipeline that returns {"severity": "high"} instead of 4, or drops a field
entirely, is caught here before any semantic test runs.
"""
from __future__ import annotations

REQUIRED_KEYS = {"entity", "event_type", "severity", "confidence"}


def test_output_has_required_keys(pipeline_results, metadata):
    for fx in metadata:
        result = pipeline_results[fx["id"]]
        missing = REQUIRED_KEYS - set(result.keys())
        extra = set(result.keys()) - REQUIRED_KEYS
        assert not missing, f"[{fx['id']}] Missing keys: {missing}"
        assert not extra, f"[{fx['id']}] Unexpected extra keys: {extra}"


def test_entity_is_nonempty_string(pipeline_results, metadata):
    for fx in metadata:
        result = pipeline_results[fx["id"]]
        assert isinstance(result["entity"], str), \
            f"[{fx['id']}] entity is not a string: {result['entity']!r}"
        assert result["entity"].strip() != "", \
            f"[{fx['id']}] entity is empty"


def test_event_type_is_nonempty_string(pipeline_results, metadata):
    for fx in metadata:
        result = pipeline_results[fx["id"]]
        assert isinstance(result["event_type"], str), \
            f"[{fx['id']}] event_type is not a string: {result['event_type']!r}"
        assert result["event_type"].strip() != "", \
            f"[{fx['id']}] event_type is empty"


def test_severity_is_integer_in_range(pipeline_results, metadata):
    for fx in metadata:
        result = pipeline_results[fx["id"]]
        assert isinstance(result["severity"], int), \
            f"[{fx['id']}] severity is not an int: {result['severity']!r} ({type(result['severity']).__name__})"
        assert 1 <= result["severity"] <= 5, \
            f"[{fx['id']}] severity {result['severity']} is outside [1, 5]"


def test_confidence_is_float_in_range(pipeline_results, metadata):
    for fx in metadata:
        result = pipeline_results[fx["id"]]
        assert isinstance(result["confidence"], float), \
            f"[{fx['id']}] confidence is not a float: {result['confidence']!r} ({type(result['confidence']).__name__})"
        assert 0.0 <= result["confidence"] <= 1.0, \
            f"[{fx['id']}] confidence {result['confidence']} is outside [0.0, 1.0]"
