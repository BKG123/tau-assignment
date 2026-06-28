"""Metamorphic tests.

These tests do NOT assert what any individual output is. They assert how two
outputs *relate* to each other. This sidesteps the ground-truth problem
entirely: even without knowing the "correct" severity for any article, we
know that a ceasefire must score lower than a fatal attack, and that a full
escalation must score at least as high as a measured overview of the same event.

Relationships are encoded in metadata.json under the `pairs` field so the
runner discovers them programmatically — no hardcoded fixture IDs here.

Each pair declares an `assert` of the form "<field>_<op>", e.g.:
    severity_lt    severity_lte    severity_gte
    confidence_lt  confidence_lte

Active pairs:
    06 →(negation)→     02  : severity_lt    Houthis end attacks vs. kill crew
    09 →(negation)→     03  : severity_lte   Port strike resolved vs. active
    07 →(monotonicity)→ 08  : severity_lte   Red Sea modest vs. full escalation
    07 →(confidence)→   02  : confidence_lt  Hedged WEF framing vs. specific fatality report
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

METADATA = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "fixtures" / "metadata.json").read_text()
)

# Flatten all pairs into (source_fixture, pair) tuples for parametrization,
# so each relationship shows up as its own test line in verbose output.
_PAIRS = [(fx, pair) for fx in METADATA for pair in fx.get("pairs", [])]

_OPS = {
    "lt": (lambda a, b: a < b, "<"),
    "lte": (lambda a, b: a <= b, "<="),
    "gt": (lambda a, b: a > b, ">"),
    "gte": (lambda a, b: a >= b, ">="),
}


def _pair_id(item):
    fx, pair = item
    return f"{fx['id']}-{pair['assert']}-{pair['pair_id']}"


@pytest.mark.parametrize("pair_item", _PAIRS, ids=_pair_id)
def test_metamorphic_relationship(pair_item, pipeline_results, metadata):
    fx, pair = pair_item
    fx_by_id = {f["id"]: f for f in metadata}

    id_a = fx["id"]
    id_b = pair["pair_id"]
    assertion = pair["assert"]
    field, _, op_name = assertion.rpartition("_")

    assert field in {"severity", "confidence"}, f"Unknown pair field: '{field}'"
    assert op_name in _OPS, f"Unknown pair operator: '{op_name}'"

    val_a = pipeline_results[id_a][field]
    val_b = pipeline_results[id_b][field]
    op_fn, op_sym = _OPS[op_name]

    print(
        f"\n  [{pair['type']}] {id_a} {field}={val_a}  {op_sym}  {id_b} {field}={val_b}"
    )

    assert op_fn(val_a, val_b), (
        f"[{id_a} vs {id_b}] {pair['type']} pair failed on {field}:\n"
        f"  {id_a} ({fx['label']}) → {field} {val_a}\n"
        f"  {id_b} ({fx_by_id[id_b]['label']}) → {field} {val_b}\n"
        f"  Expected {field}({id_a}) {op_sym} {field}({id_b})"
    )
