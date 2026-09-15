"""
Step 4: prove retrieval actually works before wiring it into the agent.

Run this after 02_chunk_and_embed.py has populated the Chroma DB. Tests
a handful of realistic incident-style queries and shows what comes back
— confirms chunk quality and relevance before this becomes a tool the
agent depends on.

Usage:
    python sync/03_test_retrieval.py
    python sync/03_test_retrieval.py "your own query here"
"""
from __future__ import annotations

import sys

import chromadb
from chromadb.utils import embedding_functions

CHROMA_DB_PATH = "./chroma_db"
COLLECTION_NAME = "sops"

# Realistic incident-shaped queries, not just SOP titles — this is closer
# to what the agent will actually pass in (an alert description), so it's
# a fairer test of retrieval quality than searching for exact titles.
DEFAULT_TEST_QUERIES = [
    "5xx errors spiking on the homepage",
    "pod keeps restarting crash loop",
    "site is slow but not returning errors",
    "database connections timing out",
    "need to roll back a bad deploy",
]


def main() -> None:
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

    try:
        collection = client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            ),
        )
    except Exception as exc:
        print(f"Couldn't open collection '{COLLECTION_NAME}': {exc}")
        print("Did you run sync/02_chunk_and_embed.py first?")
        sys.exit(1)

    count = collection.count()
    print(f"Collection has {count} chunks embedded.\n")
    if count == 0:
        print("Nothing embedded yet — run sync/02_chunk_and_embed.py first.")
        sys.exit(1)

    queries = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_TEST_QUERIES

    for query in queries:
        print(f"{'=' * 70}")
        print(f"QUERY: {query!r}")
        print(f"{'=' * 70}")

        results = collection.query(query_texts=[query], n_results=3)

        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0]

        for i, (doc, meta, dist) in enumerate(zip(docs, metas, distances)):
            print(f"\n  [{i + 1}] {meta['page_title']} > {meta['section_heading']}")
            print(f"      (distance: {dist:.3f} — lower is more relevant)")
            print(f"      {meta['page_url']}")
            preview = doc[:200] + ("..." if len(doc) > 200 else "")
            print(f"      {preview}")
        print()

    print(
        "What to check: does the TOP result for each query actually match\n"
        "the right SOP? e.g. '5xx errors spiking' should surface the\n"
        "5xx-homepage-spike SOP first, not something unrelated. If results\n"
        "look off, the chunking or the query phrasing may need adjusting —\n"
        "better to catch that here than after it's wired into the agent."
    )


if __name__ == "__main__":
    main()
