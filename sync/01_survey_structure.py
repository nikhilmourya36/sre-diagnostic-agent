"""
Step 2: survey heading structure across your real SOP pages.

Before writing the actual chunker, we need to know: do these pages
consistently use headings we can split on, or are some of them flat
text/tables with no structure? This script answers that with real data
instead of us guessing from one page.

Usage:
    (same env vars as 00_test_connection.py)
    python sync/01_survey_structure.py
"""
from __future__ import annotations

import os
import re
import sys

import requests

BASE_URL = os.environ.get("CONFLUENCE_BASE_URL", "").rstrip("/")
EMAIL = os.environ.get("CONFLUENCE_EMAIL", "")
API_TOKEN = os.environ.get("CONFLUENCE_API_TOKEN", "")
SPACE_KEY = os.environ.get("CONFLUENCE_SPACE_KEY", "")

# Confluence storage format uses plain <h1>-<h6> tags for headings.
HEADING_RE = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
TAG_STRIP_RE = re.compile(r"<[^>]+>")


def fetch_all_pages(auth) -> list[dict]:
    """Page through every page in the space (Confluence paginates at ~25/req)."""
    pages = []
    start = 0
    limit = 25
    while True:
        resp = requests.get(
            f"{BASE_URL}/rest/api/content",
            auth=auth,
            params={
                "spaceKey": SPACE_KEY,
                "limit": limit,
                "start": start,
                "expand": "body.storage,version",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        pages.extend(results)
        if len(results) < limit:
            break
        start += limit
        if start > 500:  # safety cap for a survey script
            print("Hit 500-page safety cap, stopping early.")
            break
    return pages


def count_headings(body_html: str) -> list[tuple[int, str]]:
    headings = []
    for match in HEADING_RE.finditer(body_html):
        level = int(match.group(1))
        text = TAG_STRIP_RE.sub("", match.group(2)).strip()
        headings.append((level, text))
    return headings


def main() -> None:
    missing = [
        name
        for name, val in [
            ("CONFLUENCE_BASE_URL", BASE_URL),
            ("CONFLUENCE_EMAIL", EMAIL),
            ("CONFLUENCE_API_TOKEN", API_TOKEN),
            ("CONFLUENCE_SPACE_KEY", SPACE_KEY),
        ]
        if not val
    ]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    auth = (EMAIL, API_TOKEN)

    print(f"Fetching all pages from space '{SPACE_KEY}' ...")
    pages = fetch_all_pages(auth)
    print(f"Found {len(pages)} pages.\n")

    no_headings = []
    well_structured = []
    body_lengths = []

    for page in pages:
        title = page.get("title", "(untitled)")
        body_html = page.get("body", {}).get("storage", {}).get("value", "")
        body_lengths.append(len(body_html))
        headings = count_headings(body_html)

        if not headings:
            no_headings.append(title)
        else:
            well_structured.append((title, len(headings)))

    print(f"Pages WITH headings: {len(well_structured)}/{len(pages)}")
    print(f"Pages with NO headings at all: {len(no_headings)}/{len(pages)}\n")

    if well_structured:
        print("Sample of structured pages (title -> heading count):")
        for title, count in well_structured[:8]:
            print(f"  - {title!r}: {count} headings")

    if no_headings:
        print("\nPages with NO headings (these need a fallback chunking strategy):")
        for title in no_headings[:8]:
            print(f"  - {title!r}")

    if body_lengths:
        avg_len = sum(body_lengths) / len(body_lengths)
        print(f"\nAverage page body length: {avg_len:.0f} chars")
        print(f"Shortest: {min(body_lengths)} chars, Longest: {max(body_lengths)} chars")

    print(
        "\n\nWhat this tells us:\n"
        "- If most pages have headings -> section-based chunking is the right\n"
        "  primary strategy.\n"
        "- If a meaningful chunk have NO headings -> we add a fallback: chunk\n"
        "  those by paragraph groups or a fixed token window instead.\n"
        "- Very short pages (a few hundred chars) probably don't need chunking\n"
        "  at all -> embed as a single chunk.\n"
    )


if __name__ == "__main__":
    main()
