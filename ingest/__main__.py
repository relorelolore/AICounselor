# ingest/__main__.py
from __future__ import annotations
import argparse
import json
from .indexer import build_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Build RAG index from Documents/")
    parser.add_argument("--force", action="store_true", help="re-process every file")
    args = parser.parse_args()
    result = build_index(force=args.force)
    print(json.dumps({
        "added": result["added"],
        "skipped": result["skipped"],
        "failed": result["failed"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
