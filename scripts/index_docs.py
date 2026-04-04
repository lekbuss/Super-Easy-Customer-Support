"""
index_docs.py — DocuWare knowledge base indexer CLI

Usage examples:

  # Index specific articles from a URL list file
  python scripts/index_docs.py --urls-file docs_urls.txt

  # Auto-discover and index all articles in specified categories
  python scripts/index_docs.py --categories CAT-02300,CAT-02302,CAT-02303

  # Combine both
  python scripts/index_docs.py --urls-file extra.txt --categories CAT-02300
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Make sure the project root is on sys.path when running as a script
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.indexer import DocuwareKBIndexer, _polite_sleep  # noqa: E402
from app.rag.vectorstore import VectorStore  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("index_docs")

_CATEGORY_BASE = "https://support.docuware.com/en-US/knowledgebase/category/?id="
_FAILED_LOG = Path("failed_urls.log")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_url_file(path: str) -> list[str]:
    urls = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def _append_failed(url: str) -> None:
    with _FAILED_LOG.open("a", encoding="utf-8") as f:
        f.write(url + "\n")


def _category_url(cat_id: str) -> str:
    cat_id = cat_id.strip()
    if cat_id.startswith("http"):
        return cat_id
    return _CATEGORY_BASE + cat_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index DocuWare knowledge base articles into ChromaDB"
    )
    parser.add_argument(
        "--urls-file",
        metavar="FILE",
        help="Path to a plain-text file with one article URL per line",
    )
    parser.add_argument(
        "--categories",
        metavar="CAT_IDS",
        help="Comma-separated category IDs (e.g. CAT-02300,CAT-02302)",
    )
    args = parser.parse_args()

    if not args.urls_file and not args.categories:
        parser.error("Provide at least one of --urls-file or --categories")

    store = VectorStore()
    indexer = DocuwareKBIndexer(vectorstore=store)

    total_urls = 0
    succeeded = 0
    failed = 0
    total_chunks = 0

    # --- Mode A: explicit URL list ---
    if args.urls_file:
        urls = _load_url_file(args.urls_file)
        logger.info("Loaded %d URLs from %s", len(urls), args.urls_file)
        total_urls += len(urls)

        for i, url in enumerate(urls, start=1):
            print(f"[{i}/{len(urls)}] {url}", flush=True)
            try:
                chunks = indexer.index_article(url)
                total_chunks += chunks
                succeeded += 1
            except Exception as exc:
                logger.warning("FAILED %s: %s", url, exc)
                failed += 1
                _append_failed(url)
            _polite_sleep()

    # --- Mode B: category auto-discovery ---
    if args.categories:
        cat_ids = [c.strip() for c in args.categories.split(",") if c.strip()]
        for cat_id in cat_ids:
            cat_url = _category_url(cat_id)
            logger.info("Processing category: %s → %s", cat_id, cat_url)
            print(f"\n=== Category: {cat_id} ===", flush=True)

            try:
                summary = indexer.index_category(cat_url)
            except Exception as exc:
                logger.error("Category %s failed entirely: %s", cat_id, exc)
                continue

            total_urls += summary["total"]
            succeeded += summary["succeeded"]
            failed += summary["failed"]
            total_chunks += summary["chunks"]

            for bad_url in summary["failed_urls"]:
                _append_failed(bad_url)

            print(
                f"  Category done — {summary['succeeded']}/{summary['total']} articles, "
                f"{summary['chunks']} chunks, {summary['failed']} failed",
                flush=True,
            )

    # --- Final report ---
    print("\n" + "=" * 50, flush=True)
    print(f"总计处理 URL：{total_urls}", flush=True)
    print(f"成功：{succeeded}", flush=True)
    print(f"失败：{failed}", flush=True)
    print(f"生成 chunks：{total_chunks}", flush=True)
    print(f"向量库现有文档数：{store.count()}", flush=True)
    if failed:
        print(f"失败 URL 已记录到：{_FAILED_LOG.resolve()}", flush=True)
    print("=" * 50, flush=True)


if __name__ == "__main__":
    main()
