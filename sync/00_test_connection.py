"""
Step 1: prove we can talk to Confluence at all.

Run this before writing any chunking/embedding logic. It does nothing
except confirm auth works and show you the shape of a real page's content,
so we know what we're actually parsing in the next step.

Usage:
    Fill in .env at the project root (copy from .env.example), then:
    python sync/00_test_connection.py
"""
from __future__ import annotations

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()  # loads .env from the current or parent directory automatically

BASE_URL = os.environ.get("CONFLUENCE_BASE_URL", "").rstrip("/")
EMAIL = os.environ.get("CONFLUENCE_EMAIL", "")
API_TOKEN = os.environ.get("CONFLUENCE_API_TOKEN", "")
SPACE_KEY = os.environ.get("CONFLUENCE_SPACE_KEY", "")


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

    # Step A: can we authenticate at all?
    print(f"Checking auth against {BASE_URL} ...")
    resp = requests.get(f"{BASE_URL}/rest/api/space/{SPACE_KEY}", auth=auth, timeout=10)
    if resp.status_code == 401:
        print("Auth failed (401). Check your email + API token.")
        sys.exit(1)
    if resp.status_code == 404:
        print(f"Space '{SPACE_KEY}' not found (404). Check the space key.")
        sys.exit(1)
    resp.raise_for_status()
    space = resp.json()
    print(f"Connected. Space name: {space.get('name')!r}")

    # Step B: pull a handful of real pages from that space and show their shape.
    print(f"\nFetching up to 5 pages from space '{SPACE_KEY}' ...")
    resp = requests.get(
        f"{BASE_URL}/rest/api/content",
        auth=auth,
        params={
            "spaceKey": SPACE_KEY,
            "limit": 5,
            "expand": "body.storage,version,history.lastUpdated",
        },
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])

    if not results:
        print("No pages found in this space. Double check the space key.")
        return

    for page in results:
        title = page.get("title")
        page_id = page.get("id")
        version = page.get("version", {}).get("number")
        last_updated = page.get("version", {}).get("when")
        body_html = page.get("body", {}).get("storage", {}).get("value", "")

        print(f"\n--- {title} (id={page_id}, v{version}, updated={last_updated}) ---")
        print(f"Body length: {len(body_html)} chars")
        print("First 300 chars of raw storage-format body:")
        print(body_html[:300])

    print(
        "\n\nIf this looks right, next step is writing the real fetch-and-chunk "
        "script against this same API, using the body.storage HTML you see above "
        "to split on headings."
    )


if __name__ == "__main__":
    main()
