"""
index_docs.py -- DocuWare knowledge base indexer CLI

Usage examples:

  # Clear all indexed data
  python scripts/index_docs.py --clear

  # Index a single URL for testing
  python scripts/index_docs.py --test-url https://support.docuware.com/en-us/knowledgebase/article/KBA-36204

  # Index specific articles from a URL list file
  python scripts/index_docs.py --urls-file docs_urls.txt

  # Auto-discover and index articles in specified categories
  python scripts/index_docs.py --categories CAT-02304,CAT-02302,CAT-02309

  # Index all known categories
  python scripts/index_docs.py --all-categories

  # Resume interrupted indexing (skip already-indexed URLs)
  python scripts/index_docs.py --all-categories --resume
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.indexer import DocuwareKBIndexer  # noqa: E402
from app.rag.vectorstore import VectorStore  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("index_docs")

_CATEGORY_BASE = "https://support.docuware.com/en-US/knowledgebase/category/?id="
_FAILED_LOG = Path(__file__).parent / "failed_urls.log"

_ALL_CATEGORIES: dict[str, str] = {
    "CAT-02300": "Administration",
    "CAT-02301": "Clients",
    "CAT-02302": "Cloud",
    "CAT-02303": "Configurations",
    "CAT-02304": "Desktop Apps",
    "CAT-02305": "External Components",
    "CAT-03987": "Fortis",
    "CAT-03988": "FortisBlue",
    "CAT-04036": "Hotfixes & Downloads",
    "CAT-02309": "Installation",
    "CAT-02310": "Intelligent Indexing",
    "CAT-02311": "Modules",
    "CAT-02312": "SDK",
    "CAT-02313": "Server",
    "CAT-02314": "Website docuware.com",
    "CAT-02315": "WTI Capture Connectors",
}


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


def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def _index_url_list(
    urls: list[str],
    indexer: DocuwareKBIndexer,
    store: VectorStore,
    resume: bool,
    category: str = "",
) -> tuple[int, int, int, int]:
    """Index a list of URLs. Returns (succeeded, failed, skipped, chunks)."""
    succeeded = failed = skipped = chunks = 0
    total = len(urls)
    for i, url in enumerate(urls, start=1):
        print(f"  [{i}/{total}] {url}", flush=True)
        if resume and store.has_url(url):
            print("    -> SKIP (already indexed)", flush=True)
            skipped += 1
            continue
        try:
            n = indexer.index_article(url, category=category)
            chunks += n
            succeeded += 1
            print(f"    -> {n} chunks | DB total: {store.count()}", flush=True)
        except Exception as exc:
            logger.warning("FAILED %s: %s", url, exc)
            failed += 1
            _append_failed(url)
        time.sleep(2)
    return succeeded, failed, skipped, chunks


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index DocuWare knowledge base articles into ChromaDB"
    )
    parser.add_argument(
        "--urls-file", metavar="FILE",
        help="Path to a plain-text file with one article URL per line",
    )
    parser.add_argument(
        "--categories", metavar="CAT_IDS",
        help="Comma-separated category IDs (e.g. CAT-02300,CAT-02302)",
    )
    parser.add_argument(
        "--all-categories", action="store_true",
        help="Index all known DocuWare KB categories",
    )
    parser.add_argument(
        "--test-url", metavar="URL",
        help="Index a single article URL and run a test search (for debugging)",
    )
    parser.add_argument(
        "--clear", action="store_true",
        help="Clear all documents from ChromaDB (can be combined with other flags)",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Skip URLs already indexed in ChromaDB",
    )
    args = parser.parse_args()

    has_work = any([args.urls_file, args.categories, args.all_categories, args.test_url])
    if not args.clear and not has_work:
        parser.error(
            "Provide at least one of: --clear, --urls-file, --categories, "
            "--all-categories, --test-url"
        )

    store = VectorStore()
    indexer = DocuwareKBIndexer(vectorstore=store)

    # --- Clear ---
    if args.clear:
        store.clear()
        print(f"ChromaDB cleared. 0 documents remaining.", flush=True)
        if not has_work:
            return

    start_time = time.time()
    total_urls = 0
    succeeded = 0
    failed = 0
    skipped = 0
    total_chunks = 0

    # --- Mode A: explicit URL list ---
    if args.urls_file:
        urls = _load_url_file(args.urls_file)
        logger.info("Loaded %d URLs from %s", len(urls), args.urls_file)
        total_urls += len(urls)
        print(f"\n=== URL file: {args.urls_file} ({len(urls)} articles) ===", flush=True)
        ok, fail, skip, chunks = _index_url_list(urls, indexer, store, args.resume)
        succeeded += ok
        failed += fail
        skipped += skip
        total_chunks += chunks

    # --- Mode B: specified categories ---
    if args.categories:
        cat_ids = [c.strip() for c in args.categories.split(",") if c.strip()]
        for cat_idx, cat_id in enumerate(cat_ids, start=1):
            cat_url = _category_url(cat_id)
            cat_name = _ALL_CATEGORIES.get(cat_id, cat_id)
            print(f"\n[{cat_idx}/{len(cat_ids)}] === {cat_name} ({cat_id}) ===", flush=True)

            try:
                article_urls = indexer.discover_articles(cat_url)
            except Exception as exc:
                logger.error("Category %s discover failed: %s", cat_id, exc)
                continue

            print(f"  Found {len(article_urls)} articles", flush=True)
            total_urls += len(article_urls)

            ok, fail, skip, chunks = _index_url_list(
                article_urls, indexer, store, args.resume, category=cat_id
            )
            succeeded += ok
            failed += fail
            skipped += skip
            total_chunks += chunks
            print(
                f"  Done ok:{ok} fail:{fail} skip:{skip} chunks:{chunks}",
                flush=True,
            )
            if cat_idx < len(cat_ids):
                print("  Sleeping 5s...", flush=True)
                time.sleep(5)

    # --- Mode C: all categories ---
    if args.all_categories:
        cat_items = list(_ALL_CATEGORIES.items())
        print(f"\nIndexing all {len(cat_items)} categories...", flush=True)

        for cat_idx, (cat_id, cat_name) in enumerate(cat_items, start=1):
            cat_url = _category_url(cat_id)
            print(
                f"\n[{cat_idx}/{len(cat_items)}] === {cat_name} ({cat_id}) ===",
                flush=True,
            )

            try:
                article_urls = indexer.discover_articles(cat_url)
            except Exception as exc:
                logger.error("Category %s discover failed: %s", cat_id, exc)
                continue

            print(f"  Found {len(article_urls)} articles", flush=True)
            total_urls += len(article_urls)

            ok, fail, skip, chunks = _index_url_list(
                article_urls, indexer, store, args.resume, category=cat_id
            )
            succeeded += ok
            failed += fail
            skipped += skip
            total_chunks += chunks
            print(
                f"  Done — ok:{ok} fail:{fail} skip:{skip} chunks:{chunks} "
                f"| DB total: {store.count()}",
                flush=True,
            )
            if cat_idx < len(cat_items):
                print("  Sleeping 5s before next category...", flush=True)
                time.sleep(5)

    # --- Mode D: single URL test ---
    if args.test_url:
        from app.rag.indexer import (  # noqa: E402
            _extract_article_text,
            _extract_kba_id,
            _extract_title,
            _fetch,
        )

        url = args.test_url
        print(f"\n=== Test URL: {url} ===", flush=True)
        soup = _fetch(url, indexer._session)
        if soup is None:
            print("ERROR: Could not fetch URL", flush=True)
        else:
            title = _extract_title(soup, url)
            kba_id = _extract_kba_id(url)
            body = _extract_article_text(soup)
            print(f"  Title       : {title}", flush=True)
            print(f"  KBA ID      : {kba_id}", flush=True)
            print(f"  Body chars  : {len(body)}", flush=True)

            n = indexer.index_article(url)
            total_chunks += n
            succeeded += 1
            total_urls += 1
            print(f"  Chunks      : {n}", flush=True)
            print(f"  ChromaDB    : {store.count()} docs", flush=True)

            print("\n--- Test search: 'DocuWare version download' ---", flush=True)
            hits = store.search("DocuWare version download", top_k=3)
            if not hits:
                print("  (no results)", flush=True)
            for i, hit in enumerate(hits, 1):
                meta = hit.get("metadata", {})
                print(
                    f"  [{i}] score={hit['score']:.4f} | "
                    f"{meta.get('kba_id', '')} | {meta.get('title', '')[:60]}",
                    flush=True,
                )
                print(f"       {hit['text'][:120]}...", flush=True)

    # --- Final report ---
    elapsed = time.time() - start_time
    print("\n" + "=" * 50, flush=True)
    print(f"Total URLs     : {total_urls}", flush=True)
    print(f"Succeeded      : {succeeded}", flush=True)
    print(f"Skipped        : {skipped}", flush=True)
    print(f"Failed         : {failed}", flush=True)
    print(f"Total chunks   : {total_chunks}", flush=True)
    print(f"ChromaDB docs  : {store.count()}", flush=True)
    print(f"Elapsed        : {_fmt_time(elapsed)}", flush=True)
    if failed:
        print(f"Failed URLs    : {_FAILED_LOG.resolve()}", flush=True)
    print("=" * 50, flush=True)


if __name__ == "__main__":
    main()
