#!/usr/bin/env python3
"""Fetch fixture articles with Firecrawl and populate data/fixtures/articles/.

Reads the fixture registry at data/fixtures/metadata.json, scrapes each
`source_url` to clean markdown via Firecrawl, and writes the result to the
`file` named in the registry.

Usage:
    export FIRECRAWL_API_KEY=fc-...
    python scripts/fetch_fixtures.py            # fetch all missing/empty files
    python scripts/fetch_fixtures.py --force    # re-fetch everything
    python scripts/fetch_fixtures.py --ids 02 06 # only specific fixture ids

The key may also live in a .env file at the project root as
FIRECRAWL_API_KEY=fc-...
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ROOT / "data" / "fixtures"
ARTICLES_DIR = FIXTURES_DIR / "articles"
METADATA = FIXTURES_DIR / "metadata.json"
FIRECRAWL_ENDPOINT = "https://api.firecrawl.dev/v1/scrape"


def load_api_key() -> str:
    key = os.environ.get("FIRECRAWL_API_KEY")
    if key:
        return key.strip()
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("FIRECRAWL_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit(
        "ERROR: FIRECRAWL_API_KEY not found. Set it via:\n"
        "  export FIRECRAWL_API_KEY=fc-...\n"
        "or add a line to .env: FIRECRAWL_API_KEY=fc-..."
    )


def scrape(url: str, api_key: str, timeout: int = 90) -> str:
    """Return clean markdown for a URL using Firecrawl's /scrape endpoint."""
    payload = json.dumps(
        {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        FIRECRAWL_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if not body.get("success"):
        raise RuntimeError(f"Firecrawl returned success=false: {body}")
    data = body.get("data", {})
    markdown = data.get("markdown") or ""
    if not markdown.strip():
        raise RuntimeError("Firecrawl returned empty markdown")
    return markdown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-fetch even if file already has content")
    parser.add_argument("--ids", nargs="*", help="only fetch these fixture ids")
    args = parser.parse_args()

    api_key = load_api_key()
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    fixtures = json.loads(METADATA.read_text())

    selected = set(args.ids) if args.ids else None
    failures: list[tuple[str, str]] = []

    for fx in fixtures:
        fid = fx["id"]
        if selected and fid not in selected:
            continue
        out_path = ARTICLES_DIR / fx["file"]
        url = fx["source_url"]
        if not url or url == "...":
            print(f"[{fid}] SKIP - no source_url set")
            continue
        if out_path.exists() and out_path.stat().st_size > 0 and not args.force:
            print(f"[{fid}] SKIP - already populated ({out_path.name})")
            continue

        print(f"[{fid}] fetching {url}")
        try:
            markdown = scrape(url, api_key)
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError) as exc:
            detail = exc
            if isinstance(exc, urllib.error.HTTPError):
                try:
                    detail = exc.read().decode("utf-8")
                except Exception:
                    detail = str(exc)
            print(f"[{fid}] FAILED: {detail}")
            failures.append((fid, str(detail)))
            continue

        header = f"<!-- fixture_id: {fid} | source: {url} -->\n\n"
        out_path.write_text(header + markdown, encoding="utf-8")
        print(f"[{fid}] wrote {len(markdown)} chars -> {out_path.name}")
        time.sleep(1)  # be polite to the API

    print("\nDone.")
    if failures:
        print(f"{len(failures)} failure(s):")
        for fid, err in failures:
            print(f"  [{fid}] {err[:200]}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
