# Design Pointers / Notes

## Intro

- Considerably simple extraction pipeline.
- A single LLM call with constrained output (temperature 0) → `{entity, event_type, severity, confidence}`.
- **Main focus — Evaluation.**
- Issue: no ground truths present.
  - Example: can't have an objective exact severity for a bankruptcy news article.

---

## What I did NOT test

- **No exact assertion of `event_type` or `entity`.**
  - No universally accepted event taxonomy / genuine confusion about the "correct" entity.
  - Multi-actor articles have several possible primary entities; publisher-owned blogs blur publisher vs. subject. Asserting one correct value would just encode my own judgment.
- **No absolute confidence levels or severity values.**
  - Can't objectively pinpoint the value of severity.
  - Same with the confidence levels of LLM outputs
    - the model clusters high and won't push an article as low as a human would, so absolute thresholds would be brittle.
- **My eval suite detects pipeline drift, not data / world drift.**
  - Can catch changes caused by prompt edits, model updates, or implementation changes, because
  it evaluates a fixed fixture set.
  - Won't catch changes introduced by the news itself becoming systematically different over time. The eval corpus would need to be refreshed in that case
    - an eval *maintenance*
    problem, not a property of the tests.

---

## What I DID test

- **Structural correctness**
  - Whether valid types and ranges are satisfied (fields are non-empty and within range).
  - Needs no ground truth; catches malformed output before any semantic reasoning runs.
- **Cross-field consistency** (strongest layer — needs no human annotation)
  - Bankruptcy: severity ≥ moderate.
  - Earnings miss: severity should remain relatively low.
  - Resolution events should not simultaneously describe active attacks.
  - These test whether the model contradicts *itself*, not whether it matches an external truth.
- **Metamorphic relations**
  - Relationships *between* outputs are tested here. Examples:
    - Ceasefire scores lower than attack.
    - Framing also affects severity (a measured overview ≤ a full escalation of the same event).
  - The exact numbers don't matter, the ordering does.
  - Relationships live in `metadata.json`, not in test code, so the suite extends without
  touching the runner.
- **Regression testing**
  - Commit a baseline of distribution-level properties: mean severity, high-severity event
  proportion, confidence variance, large per-fixture change.
  - Objective is to detect behavioural drift in model output, not to reproduce identical outputs.
  - The baseline is a *reference point*, not the "correct answer." Updating it is an explicit,
  reviewable decision.

**Separation of concerns:** model calibration and regression are kept separate.

- Calibration tests ask *"is today's behaviour reasonable?"*
- Regression tests ask *"has today's behaviour changed from before?"*

---

## Limitations

### A small, manually curated fixture set rather than production-scale coverage

- Metrics are coarse (10 fixtures → sensitive aggregate metrics; one fixture moving can breach a gate).
- Coverage bias: unknown unknowns are invisible to the suite, it only tests failure modes I already thought of.
- Prompt overfitting risk: the prompt and the fixtures evolved together.
- **Why?** Assignment is about eval *design*, not scale.
- **At scale:** sample from production traffic, stratify by event type / severity, and make that
part of the eval corpus.

### Primarily English-language logistics and geopolitical news

- LLMs are not as strong in other languages as in English, but input may come from other
languages, and this suite can't measure that inconsistency.
- Hidden risk: the keyword-family matching in the consistency tests is English-only, so a
non-English `event_type` would not *fail*, it would silently fail to match and pass **vacuously**. A test that goes green for the wrong reason is worse than a missing test.
- **Why?** Picked one field for a comparable severity frame (you can compare two Red Sea
articles on one severity axis; you can't compare a Red Sea attack to a Japanese earnings miss).

### Limited coverage of highly ambiguous middle-severity events

- Mostly covers highly likely / unlikely events, severity clusters at the ends.
- Clear 4–5 events (bankruptcy, fatal attack, port strike) and clear 1–2 events (small misses)
are well covered.
- The middle (severity ~3) is not as well adhered to, it's the harder, more decision-relevant region, and wide bands there trade sensitivity for defensibility.
- **How to solve:** introduce more fixtures as metamorphic *chains* (a < b < c < d) around the middle band, so the middle is pinned by ordering rather than by absolute values

### No evaluation of latency, cost, or token efficiency

- The suite tests *what* is output, never *how expensively*. A prompt change that improves
accuracy but triples tokens/latency is an operational regression this suite is blind to.
- **Why?** The interesting problem here is output quality without ground truth. Latency/cost have objective ground truth (just measure ms/tokens), so they're a deliberate scope cut

### No verification of factual correctness without human labels

- The deepest one: a model could be *confidently, consistently wrong* and every test would still pass. Structure, consistency, ordering, and stability are all about coherence, not truth.
- **Why?** Factual verification requires ground truth (human labels / a reference DB), which is
exactly what the task says doesn't cleanly exist. This is the boundary the problem is defined by,
not a gap I failed to close.
- **Partial fix:** a small, periodically refreshed human-labelled gold set, run as a *separate*
lower-frequency eval, kept distinct from the no-ground-truth suite.

