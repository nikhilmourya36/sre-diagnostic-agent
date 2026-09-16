"""
retrieve_sop tool — queries the local Chroma DB built by
sync/02_chunk_and_embed.py, NOT Confluence directly.

This is deliberate: an incident is the wrong moment to add a dependency
on a third-party API (Confluence) being fast and available. The sync job
runs on its own schedule (see CLAUDE.md's "Sync loop"), and this tool
only ever reads from the local vector store it produces.

Returns TOP 3 matches, not just the single best one — retrieval testing
(see sync/03_test_retrieval.py) showed that some incidents genuinely
match more than one SOP (e.g. a "5xx on homepage" query can legitimately
match both the 5xx-specific SOP AND the Downstream Dependency Outage SOP,
since either could explain the same symptom). Rather than force a single
"best" answer, this tool surfaces the real candidates and lets the
agent's own reasoning — which has the FULL incident context (pod status,
recent releases, live metrics), not just the bare query text — decide
which fits. This matches CLAUDE.md's correlated-reasoning principle: the
agent should weigh evidence, not just accept the top embedding match as
gospel.
"""
from __future__ import annotations

import os
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

# Resolve relative to this file's location, not the caller's cwd — so
# this tool works correctly regardless of which directory the agent
# process is actually run from.
_SYNC_DIR = Path(__file__).resolve().parent.parent.parent / "sync"
CHROMA_DB_PATH = os.environ.get("SOP_CHROMA_DB_PATH", str(_SYNC_DIR / "chroma_db"))
COLLECTION_NAME = "sops"

_collection = None  # lazy-loaded singleton — the embedding model is
# expensive to load, don't reload it on every tool call


def _get_collection():
    global _collection
    if _collection is not None:
        return _collection

    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    _collection = client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        ),
    )
    return _collection


def retrieve_sop(query: str, n_results: int = 3) -> dict:
    """
    Search the SOP knowledge base for content relevant to an incident
    description. Returns up to n_results matching sections, each with
    its source page title, URL, section heading, and how relevant it is
    (lower distance = more relevant).

    Args:
        query: A description of the incident/symptoms — e.g. "5xx errors
            spiking on the homepage" or "pod keeps restarting". Works
            best with natural incident-style phrasing, not just a
            keyword.
        n_results: How many candidate sections to return. Default 3 —
            deliberately more than 1, since incidents sometimes
            genuinely match multiple SOPs; let the caller's own
            reasoning weigh them rather than silently picking one.

    Returns:
        dict with:
            found: bool — whether anything was retrieved at all
            results: list of dicts, each with:
                page_title, page_url, section_heading, text, relevance_distance
            error: str | None — set if the vector DB couldn't be reached
                (e.g. sync/02_chunk_and_embed.py was never run)
    """
    try:
        collection = _get_collection()
    except Exception as exc:
        return {
            "found": False,
            "results": [],
            "error": (
                f"Could not open the SOP knowledge base: {exc}. "
                f"Has sync/02_chunk_and_embed.py been run yet?"
            ),
        }

    if collection.count() == 0:
        return {
            "found": False,
            "results": [],
            "error": "SOP knowledge base is empty — run sync/02_chunk_and_embed.py first.",
        }

    raw = collection.query(query_texts=[query], n_results=n_results)

    results = []
    for doc, meta, dist in zip(raw["documents"][0], raw["metadatas"][0], raw["distances"][0]):
        results.append(
            {
                "page_title": meta["page_title"],
                "page_url": meta["page_url"],
                "section_heading": meta["section_heading"],
                "text": doc,
                "relevance_distance": round(dist, 3),
            }
        )

    return {"found": len(results) > 0, "results": results, "error": None}


if __name__ == "__main__":
    # Quick manual test — same spirit as sync/03_test_retrieval.py, but
    # exercising the actual function this tool exposes to the agent.
    import json

    test_query = "5xx errors spiking on the homepage"
    print(f"Testing retrieve_sop with query: {test_query!r}\n")
    result = retrieve_sop(test_query)
    print(json.dumps(result, indent=2))
