import logging
import re
import time
from random import uniform
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.core.config import settings
from app.rag.vectorstore import VectorStore

logger = logging.getLogger(__name__)

_BASE_URL = "https://support.docuware.com"
_HEADERS = {
    "User-Agent": (
        "DocuwareKBIndexer/1.0 (internal knowledge-base tool; "
        "contact: support-team@company.com)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}
_KBA_RE = re.compile(r"KBA-\d+", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------

def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into chunks, preferring paragraph boundaries.

    Paragraphs that exceed chunk_size are hard-split with overlap.
    """
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        # Hard-split over-long paragraphs first
        if len(para) > chunk_size:
            for sub in _hard_split(para, chunk_size, overlap):
                if current:
                    chunks.append(current.strip())
                    current = ""
                chunks.append(sub)
            continue

        if len(current) + len(para) + 1 <= chunk_size:
            current = (current + "\n\n" + para).strip() if current else para
        else:
            if current:
                chunks.append(current.strip())
            # Carry-over overlap from previous chunk
            current = _overlap_prefix(current, overlap) + para if current else para

    if current.strip():
        chunks.append(current.strip())

    return [c for c in chunks if c]


def _hard_split(text: str, chunk_size: int, overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def _overlap_prefix(text: str, overlap: int) -> str:
    if not text or overlap <= 0:
        return ""
    return text[-overlap:].strip() + " "


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _fetch(url: str, session: requests.Session) -> BeautifulSoup | None:
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return None


def _polite_sleep() -> None:
    time.sleep(uniform(1.0, 2.0))


# ---------------------------------------------------------------------------
# HTML content extraction
# ---------------------------------------------------------------------------

_NOISE_SELECTORS = [
    "nav", "header", "footer", "aside",
    ".navigation", ".sidebar", ".breadcrumb",
    ".nav", ".menu", ".footer", ".header",
    "#navigation", "#sidebar", "#footer", "#header",
    "script", "style", "noscript",
]


def _extract_article_text(soup: BeautifulSoup) -> str:
    """Extract clean article body text from a KBA page."""
    # Remove known noise elements in-place
    for sel in _NOISE_SELECTORS:
        for tag in soup.select(sel):
            tag.decompose()

    # Try common article content containers
    for candidate in [
        "article",
        "[class*='article-body']",
        "[class*='kb-article']",
        "[class*='content-body']",
        "[class*='entry-content']",
        "main",
        "[role='main']",
        "#content",
        ".content",
    ]:
        node = soup.select_one(candidate)
        if node:
            return node.get_text(separator="\n", strip=True)

    # Fallback: entire body
    body = soup.find("body")
    return body.get_text(separator="\n", strip=True) if body else ""


def _extract_title(soup: BeautifulSoup, url: str) -> str:
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    title_tag = soup.find("title")
    if title_tag:
        return title_tag.get_text(strip=True)
    return url


def _extract_kba_id(url: str) -> str:
    match = _KBA_RE.search(url)
    return match.group(0).upper() if match else ""


def _normalise_url(href: str, base: str) -> str | None:
    if not href:
        return None
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        parsed = urlparse(base)
        return f"{parsed.scheme}://{parsed.netloc}{href}"
    return urljoin(base, href)


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------

class DocuwareKBIndexer:
    """Crawl and index DocuWare knowledge base articles into ChromaDB."""

    def __init__(
        self,
        vectorstore: VectorStore | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> None:
        self._store = vectorstore or VectorStore()
        self._chunk_size = chunk_size or settings.rag_chunk_size
        self._chunk_overlap = chunk_overlap or settings.rag_chunk_overlap
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def discover_articles(self, category_url: str) -> list[str]:
        """Return all article URLs found under a category page (handles paging)."""
        article_urls: list[str] = []
        next_url: str | None = category_url

        while next_url:
            logger.info("Discovering articles from: %s", next_url)
            soup = _fetch(next_url, self._session)
            if soup is None:
                break

            article_urls.extend(self._parse_article_links(soup, next_url))
            next_url = self._find_next_page(soup, next_url)
            if next_url:
                _polite_sleep()

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for url in article_urls:
            if url not in seen:
                seen.add(url)
                unique.append(url)

        logger.info("Discovered %d articles under %s", len(unique), category_url)
        return unique

    def index_article(self, article_url: str, category: str = "") -> int:
        """Fetch, chunk, and store a single article. Returns chunk count."""
        logger.debug("Indexing article: %s", article_url)
        soup = _fetch(article_url, self._session)
        if soup is None:
            raise RuntimeError(f"Could not fetch {article_url}")

        title = _extract_title(soup, article_url)
        kba_id = _extract_kba_id(article_url)
        body = _extract_article_text(soup)

        if not body.strip():
            logger.warning("Empty body for %s — skipping", article_url)
            return 0

        chunks = _chunk_text(body, self._chunk_size, self._chunk_overlap)
        docs = [
            {
                "text": chunk,
                "metadata": {
                    "source_url": article_url,
                    "title": title,
                    "kba_id": kba_id,
                    "category": category,
                },
            }
            for chunk in chunks
        ]
        self._store.add_documents(docs)
        logger.info("Indexed %d chunks from %s (%s)", len(docs), kba_id or article_url, title)
        return len(docs)

    def index_category(self, category_url: str) -> dict:
        """Discover and index all articles in a category.

        Returns a summary dict: total, succeeded, failed, chunks.
        """
        category_id = self._extract_category_id(category_url)
        article_urls = self.discover_articles(category_url)

        total = len(article_urls)
        succeeded = 0
        failed = 0
        total_chunks = 0
        failed_urls: list[str] = []

        for i, url in enumerate(article_urls, start=1):
            print(f"  [{i}/{total}] {url}", flush=True)
            try:
                chunks = self.index_article(url, category=category_id)
                total_chunks += chunks
                succeeded += 1
            except Exception as exc:
                logger.warning("Failed to index %s: %s", url, exc)
                failed += 1
                failed_urls.append(url)
            _polite_sleep()

        return {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "chunks": total_chunks,
            "failed_urls": failed_urls,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_article_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        links: list[str] = []
        for a in soup.find_all("a", href=True):
            href: str = a["href"]
            if "knowledgebase/article" in href or _KBA_RE.search(href):
                full = _normalise_url(href, base_url)
                if full:
                    links.append(full)
        return links

    def _find_next_page(self, soup: BeautifulSoup, current_url: str) -> str | None:
        # Look for a "next page" link — common patterns on paginated list pages
        for candidate in [
            "a[rel='next']",
            "a.next",
            "a[aria-label='Next']",
            ".pagination a:last-child",
        ]:
            node = soup.select_one(candidate)
            if node and node.get("href"):
                return _normalise_url(node["href"], current_url)
        return None

    @staticmethod
    def _extract_category_id(url: str) -> str:
        match = re.search(r"id=(CAT-\d+)", url, re.IGNORECASE)
        return match.group(1) if match else url
