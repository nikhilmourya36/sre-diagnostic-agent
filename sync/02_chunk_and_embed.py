"""
Step 3: chunk Confluence SOP pages by heading and embed into Chroma.

Builds on 00_test_connection.py (proved auth works) and
01_survey_structure.py (confirmed most pages use real headings). This
script does the actual work: fetch every page, split each into
heading-based chunks, embed them with a local sentence-transformers
model, and store them in a local Chroma collection.

This is a SYNC job — meant to be re-run periodically (see CLAUDE.md's
"Sync loop" section), not run once and forgotten. Re-running it re-embeds
only pages whose Confluence version changed since the last sync, tracked
via a local state file.

Usage:
    (.env at project root, same as 00_test_connection.py)
    pip install chromadb sentence-transformers requests python-dotenv --break-system-packages
    python sync/02_chunk_and_embed.py

Output:
    A local Chroma DB at ./chroma_db/ (gitignored — see .gitignore) with
    one collection called "sops", where each entry is one section-level
    chunk with metadata: page title, page URL, section heading, and the
    Confluence version it was embedded from.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import chromadb
import requests
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("CONFLUENCE_BASE_URL", "").rstrip("/")
EMAIL = os.environ.get("CONFLUENCE_EMAIL", "")
API_TOKEN = os.environ.get("CONFLUENCE_API_TOKEN", "")
SPACE_KEY = os.environ.get("CONFLUENCE_SPACE_KEY", "")

CHROMA_DB_PATH = "./chroma_db"
COLLECTION_NAME = "sops"
SYNC_STATE_PATH = "./sync_state.json"

# Confluence storage format uses plain <h1>-<h6> tags for headings.
HEADING_RE = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
TAG_STRIP_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


def clean_text(html: str) -> str:
    """Strip HTML tags and collapse whitespace. Good enough for embedding
    purposes — we're not trying to preserve formatting, just meaning."""
    text = TAG_STRIP_RE.sub(" ", html)
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def chunk_by_heading(title: str, body_html: str) -> list[dict]:
    """
    Split a page's body into one chunk per top-level section, using
    headings as boundaries. Falls back to a single whole-page chunk if
    no headings are found — matches what 01_survey_structure.py told us
    to expect for any unheaded pages.

    Each chunk includes its own heading as a prefix, so retrieval
    results are self-contained and readable without needing the parent
    page's title repeated externally.
    """
    matches = list(HEADING_RE.finditer(body_html))

    if not matches:
        # Fallback: no headings at all, embed the whole page as one chunk.
        text = clean_text(body_html)
        if not text:
            return []
        return [{"heading": title, "text": text}]

    chunks = []
    for i, match in enumerate(matches):
        heading_text = TAG_STRIP_RE.sub("", match.group(2)).strip()
        section_start = match.end()
        section_end = matches[i + 1].start() if i + 1 < len(matches) else len(body_html)
        section_html = body_html[section_start:section_end]
        section_text = clean_text(section_html)

        if not section_text:
            continue  # skip empty sections (e.g. a heading with no body before the next one)

        chunks.append({"heading": heading_text, "text": f"{heading_text}: {section_text}"})

    return chunks


def fetch_all_pages(auth) -> list[dict]:
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
        if start > 500:
            print("Hit 500-page safety cap, stopping early.")
            break
    return pages


def load_sync_state() -> dict:
    path = Path(SYNC_STATE_PATH)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_sync_state(state: dict) -> None:
    Path(SYNC_STATE_PATH).write_text(json.dumps(state, indent=2))


def page_url(page_id: str) -> str:
    return f"{BASE_URL}/pages/viewpage.action?pageId={page_id}"


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

    print("Loading local embedding model (sentence-transformers/all-MiniLM-L6-v2)...")
    print("First run downloads the model (~80MB) — subsequent runs use the local cache.")
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )

    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
    )

    sync_state = load_sync_state()

    print(f"Fetching all pages from space '{SPACE_KEY}' ...")
    pages = fetch_all_pages(auth)
    print(f"Found {len(pages)} pages.\n")

    updated_count = 0
    skipped_count = 0
    total_chunks = 0

    for page in pages:
        page_id = page.get("id")
        title = page.get("title", "(untitled)")
        version = page.get("version", {}).get("number")
        body_html = page.get("body", {}).get("storage", {}).get("value", "")

        # Skip re-embedding pages whose Confluence version hasn't changed
        # since the last sync — keeps re-syncs cheap.
        if sync_state.get(page_id) == version:
            skipped_count += 1
            continue

        # Remove any existing chunks for this page before re-adding —
        # handles both first-time embedding and re-embedding after an edit.
        existing = collection.get(where={"page_id": page_id})
        if existing["ids"]:
            collection.delete(ids=existing["ids"])

        chunks = chunk_by_heading(title, body_html)
        if not chunks:
            print(f"  (skipping {title!r} — no extractable text)")
            sync_state[page_id] = version
            continue

        ids = [f"{page_id}-{i}" for i in range(len(chunks))]
        documents = [c["text"] for c in chunks]
        metadatas = [
            {
                "page_id": page_id,
                "page_title": title,
                "page_url": page_url(page_id),
                "section_heading": c["heading"],
                "confluence_version": version,
            }
            for c in chunks
        ]

        collection.add(ids=ids, documents=documents, metadatas=metadatas)

        print(f"  Embedded {title!r}: {len(chunks)} chunks (v{version})")
        sync_state[page_id] = version
        updated_count += 1
        total_chunks += len(chunks)

    save_sync_state(sync_state)

    print(
        f"\nDone. {updated_count} pages updated ({total_chunks} chunks), "
        f"{skipped_count} pages unchanged and skipped."
    )
    print(f"Chroma DB stored at {CHROMA_DB_PATH}/")
    print(f"Sync state stored at {SYNC_STATE_PATH}")


if __name__ == "__main__":
    main()
