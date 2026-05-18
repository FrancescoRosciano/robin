"""
scripts/setup_moss_statutes.py

One-off script: creates (or verifies) the Moss index for the three pre-verified
Robin cancellation statutes. Run once before the demo.

Usage:
    docker compose run --rm robin python scripts/setup_moss_statutes.py

Idempotent: safe to run twice; skips creation if index already exists.
Reads MOSS_PROJECT_ID, MOSS_PROJECT_KEY, MOSS_INDEX_NAME from env (.env loaded
via python-dotenv if available, else raw env).
"""
import asyncio
import os
import sys


def _load_env() -> None:
    """Load .env if python-dotenv is available; no-op otherwise."""
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
    except ImportError:
        pass


def _build_client():
    """Returns a real MossClient. Injectable for tests."""
    from moss import MossClient  # type: ignore
    project_id = os.environ.get("MOSS_PROJECT_ID", "")
    project_key = os.environ.get("MOSS_PROJECT_KEY", "")
    if not project_id or not project_key:
        raise RuntimeError(
            "MOSS_PROJECT_ID and MOSS_PROJECT_KEY must be set in the environment."
        )
    return MossClient(project_id, project_key)


def _build_corpus() -> list:
    """
    Returns exactly three DocumentInfo objects — verbatim text from
    robin.integrations.moss_search._build_corpus(). Imports from moss_search
    to share the single source of truth for the corpus.
    """
    from robin.integrations.moss_search import _build_corpus as _shared_corpus
    return _shared_corpus()


async def main() -> None:
    index_name = os.environ.get("MOSS_INDEX_NAME", "robin-statutes")
    print("[W3] Checking Moss index …")
    client = _build_client()
    try:
        existing = await client.list_indexes()
        if index_name in existing:
            print(f"[W3] Index '{index_name}' already exists — skipping.")
            return
        docs = _build_corpus()
        await client.create_index(index_name, docs)
        print(f"[W3] Index '{index_name}' created with {len(docs)} documents — done.")
    except Exception as exc:
        print(f"[W3] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _load_env()
    asyncio.run(main())
