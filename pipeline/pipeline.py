"""Article → structured risk signal pipeline.

Input:  raw article text (string)
Output: {"entity": str, "event_type": str, "severity": int (1-5), "confidence": float (0-1)}
"""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

SYSTEM_PROMPT = """You are a financial risk signal extractor for a logistics and supply chain intelligence platform.

Given a news article, extract a structured risk signal as a JSON object with exactly these four fields:

- entity: the primary organization, company, geographic entity, or actor the article is about (specific name, not a generic description)
- event_type: a snake_case label for the type of event — pick the most precise term that fits, for example:
    bankruptcy, chapter_11, earnings_miss, revenue_decline,
    labor_disruption, labor_resolution, port_strike,
    geopolitical_attack, geopolitical_disruption, geopolitical_resolution,
    infrastructure_disruption, shipping_disruption, supply_chain_disruption
- severity: integer 1–5
    1 = minimal — negligible financial or operational impact
    2 = minor — contained, short-lived disruption
    3 = moderate — regional or single-sector impact, recoverable
    4 = significant — multi-sector or sustained disruption, material financial impact
    5 = severe — systemic, catastrophic, or irreversible impact
- confidence: float 0.0–1.0 measuring the *article's information density*, not your own extraction ability.
    Ask: how clearly and specifically does this article signal the event's entity, type, and magnitude?
    Calibrate against this scale — do not cluster near 1.0:
      0.3–0.5 = vague or opinion-heavy; no named entities; language is heavily hedged ("could", "may", "experts suggest")
      0.5–0.65 = some specific facts but mixed with speculation, limited scope, or secondhand framing
      0.65–0.80 = clear reporting with named entities and some quantified impacts
      0.80–0.90 = specific facts, named entities, hard numbers, direct quotes from principals
      0.90–0.95 = near-perfect specificity — named company, exact date, precise figures, direct attribution
    Reserve values above 0.95 only when the article reads like a primary source (press release, court filing, earnings release).

Return only valid JSON. No explanation, no markdown, no extra keys."""

# Article text is truncated to this many characters to stay within context limits
# while retaining the substantive body of any real news article.
MAX_CHARS = 12_000


def run_pipeline(article_text: str, model: str = "gpt-5.4-mini") -> dict:
    """Run the extraction pipeline on a single article.

    Args:
        article_text: Raw article text (may include nav chrome, markdown links, etc.)
        model: OpenAI model to use.

    Returns:
        dict with keys: entity, event_type, severity (int), confidence (float)
    """
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": article_text[:MAX_CHARS]},
        ],
        temperature=0,
    )

    raw = json.loads(response.choices[0].message.content)

    # Normalize types defensively — some models return severity as a string
    return {
        "entity": str(raw["entity"]),
        "event_type": str(raw["event_type"]),
        "severity": int(raw["severity"]),
        "confidence": float(raw["confidence"]),
    }
