"""Metamorphic tests.

These tests do NOT assert what any individual output is. They assert how two
outputs *relate* to each other. This sidesteps the ground-truth problem
entirely: even without knowing the "correct" severity for any article, we
know that a ceasefire must score lower than a fatal attack, and that a full
escalation must score at least as high as a measured overview of the same event.

Relationships are encoded in metadata.json under the `pairs` field so the
runner discovers them programmatically — no hardcoded fixture IDs here.

Pair types:
    negation     — same entity, opposite valence.  assert: severity_lt
    monotonicity — same topic, different intensity. assert: severity_lte / severity_gte

Active pairs:
    06 →(negation)→    02  : Houthis end attacks vs. Houthis kill crew
    09 →(negation)→    03  : Port strike resolved vs. port strike active
    07 →(monotonicity)→ 08  : Red Sea modest framing vs. Red Sea full escalation
"""
from __future__ import annotations


def test_metamorphic_pairs(pipeline_results, metadata):
    fx_by_id = {fx["id"]: fx for fx in metadata}

    for fx in metadata:
        for pair in fx.get("pairs", []):
            id_a = fx["id"]
            id_b = pair["pair_id"]
            sev_a = pipeline_results[id_a]["severity"]
            sev_b = pipeline_results[id_b]["severity"]
            label_a = fx["label"]
            label_b = fx_by_id[id_b]["label"]
            assertion = pair["assert"]

            if assertion == "severity_lt":
                assert sev_a < sev_b, (
                    f"[{id_a} vs {id_b}] Negation pair failed:\n"
                    f"  {id_a} ({label_a}) → severity {sev_a}\n"
                    f"  {id_b} ({label_b}) → severity {sev_b}\n"
                    f"  Expected severity({id_a}) < severity({id_b})"
                )
            elif assertion == "severity_lte":
                assert sev_a <= sev_b, (
                    f"[{id_a} vs {id_b}] Monotonicity pair failed:\n"
                    f"  {id_a} ({label_a}) → severity {sev_a}\n"
                    f"  {id_b} ({label_b}) → severity {sev_b}\n"
                    f"  Expected severity({id_a}) <= severity({id_b})"
                )
            elif assertion == "severity_gte":
                assert sev_a >= sev_b, (
                    f"[{id_a} vs {id_b}] Monotonicity pair failed:\n"
                    f"  {id_a} ({label_a}) → severity {sev_a}\n"
                    f"  {id_b} ({label_b}) → severity {sev_b}\n"
                    f"  Expected severity({id_a}) >= severity({id_b})"
                )
            else:
                raise ValueError(f"Unknown pair assertion type: '{assertion}'")
