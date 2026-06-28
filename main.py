#!/usr/bin/env python3
"""Run the risk signal pipeline on a news article file.

Usage:
    uv run python main.py data/fixtures/articles/01_stg_logistics_bankruptcy.txt
    uv run python main.py path/to/article.txt --model gpt-5.4-mini
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline.pipeline import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract a structured risk signal from a news article."
    )
    parser.add_argument(
        "article",
        type=Path,
        help="Path to a text file containing the article body",
    )
    parser.add_argument(
        "--model",
        default="gpt-5.4-mini",
        help="OpenAI model to use (default: gpt-5.4-mini)",
    )
    args = parser.parse_args()

    if not args.article.is_file():
        print(f"ERROR: file not found: {args.article}", file=sys.stderr)
        return 1

    article_text = args.article.read_text(encoding="utf-8")
    if not article_text.strip():
        print(f"ERROR: file is empty: {args.article}", file=sys.stderr)
        return 1

    try:
        result = run_pipeline(article_text, model=args.model)
    except KeyError:
        print(
            "ERROR: OPENAI_API_KEY not set. Export it or add it to .env",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(f"ERROR: pipeline failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
