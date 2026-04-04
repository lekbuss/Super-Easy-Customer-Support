"""Draft generation agent.

Information priority:
  1. RAG (ChromaDB — DocuWare official KB)
  2. Web search (Anthropic built-in web_search tool) — when RAG is empty or low-quality
  3. LLM knowledge only — last resort
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.llm.client import AnthropicClient, LLMServiceError
from app.llm.prompts import DRAFT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Minimum cosine-similarity score to consider a RAG hit "useful"
_RAG_SCORE_THRESHOLD = 0.45


# ---------------------------------------------------------------------------
# RAG retrieval
# ---------------------------------------------------------------------------

def _retrieve_context(query: str) -> list[dict]:
    """Return relevant KB chunks, or [] on any error / empty store."""
    try:
        from app.rag.vectorstore import VectorStore  # lazy import

        store = VectorStore()
        if store.count() == 0:
            logger.debug("VectorStore is empty, skipping RAG retrieval")
            return []
        hits = store.search(query, top_k=settings.rag_top_k)
        useful = [h for h in hits if h.get("score", 0) >= _RAG_SCORE_THRESHOLD]
        if useful:
            logger.info("RAG: %d/%d chunks above threshold (%.2f)", len(useful), len(hits), _RAG_SCORE_THRESHOLD)
        else:
            logger.info("RAG: no chunks above threshold (best=%.3f)", max((h.get("score", 0) for h in hits), default=0))
        return useful
    except Exception as exc:
        logger.warning("RAG retrieval failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# User message builders
# ---------------------------------------------------------------------------

def _build_user_message_with_rag(
    ticket_subject: str,
    ticket_body: str,
    rag_hits: list[dict],
    previous_draft: str | None,
    review_notes: str | None,
) -> str:
    lines = [
        "【顧客からの問い合わせ】",
        f"件名: {ticket_subject}",
        f"内容: {ticket_body.strip()}",
        "",
        "【参考：DocuWare公式ドキュメント】",
    ]

    for i, hit in enumerate(rag_hits, start=1):
        meta = hit.get("metadata", {})
        source = meta.get("source_url", "")
        kba = meta.get("kba_id", "")
        title = meta.get("title", "")
        label = kba or title or source
        lines.append(f"--- ドキュメント{i} (出典: {label} / {source}) ---")
        lines.append(hit.get("text", "").strip())
        lines.append("")

    lines += [
        "上記のドキュメントを参考に、顧客の質問に対して具体的に回答してください。",
        "回答には必ず参考にしたドキュメントの出典（KBA番号またはURL）を記載してください。",
        "ドキュメントに該当する情報がない場合は、その旨を明記してください。",
        "回答は必ず日本語で作成してください。",
    ]

    if previous_draft and review_notes:
        lines += [
            "",
            "【前回のドラフトとレビューコメント】",
            f"前回のドラフト:\n{previous_draft.strip()}",
            f"レビューコメント:\n{review_notes.strip()}",
            "",
            "レビュー内容を反映した改訂版を作成してください。",
        ]

    return "\n".join(lines)


def _build_user_message_web_search(
    ticket_subject: str,
    ticket_body: str,
    previous_draft: str | None,
    review_notes: str | None,
) -> str:
    lines = [
        "【顧客からの問い合わせ】",
        f"件名: {ticket_subject}",
        f"内容: {ticket_body.strip()}",
        "",
        "DocuWare公式ドキュメントに関連情報が見つかりませんでした。",
        "Webで検索して、可能な限り正確な情報を基に回答してください。",
        "回答には参照した情報源のURLを必ず記載してください。",
        "推測で回答する場合は「推測ですが」と明記してください。",
        "回答は必ず日本語で作成してください。",
    ]

    if previous_draft and review_notes:
        lines += [
            "",
            "【前回のドラフトとレビューコメント】",
            f"前回のドラフト:\n{previous_draft.strip()}",
            f"レビューコメント:\n{review_notes.strip()}",
            "",
            "レビュー内容を反映した改訂版を作成してください。",
        ]

    return "\n".join(lines)


def _build_user_message_no_context(
    ticket_subject: str,
    ticket_body: str,
    previous_draft: str | None,
    review_notes: str | None,
) -> str:
    """Fallback when both RAG and web search are unavailable."""
    lines = [
        "【顧客からの問い合わせ】",
        f"件名: {ticket_subject}",
        f"内容: {ticket_body.strip()}",
        "",
        "参考ドキュメントは提供されていません。",
        "手持ちの知識で可能な範囲で回答し、不明な点は「DocuWare社に確認中です」と記載してください。",
        "回答は必ず日本語で作成してください。",
    ]

    if previous_draft and review_notes:
        lines += [
            "",
            "【前回のドラフトとレビューコメント】",
            f"前回のドラフト:\n{previous_draft.strip()}",
            f"レビューコメント:\n{review_notes.strip()}",
            "",
            "レビュー内容を反映した改訂版を作成してください。",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fallback (no LLM available at all)
# ---------------------------------------------------------------------------

def _fallback_draft(
    ticket_subject: str,
    ticket_body: str,
    previous_draft: str | None,
    review_notes: str | None,
) -> str:
    if previous_draft and review_notes:
        return (
            f"{ticket_subject} に関する改訂版のご案内です。\n\n"
            f"レビュー内容: {review_notes.strip()}\n\n"
            f"{previous_draft.strip()}\n\n"
            "DocuWare テクニカルサポート"
        )
    return (
        f"{ticket_subject} についてご連絡ありがとうございます。\n\n"
        f"お問い合わせ内容：{ticket_body.strip()[:200]}\n\n"
        "現在、DocuWare社の技術情報を確認しております。\n"
        "詳細が判明次第、改めてご連絡いたします。\n\n"
        "DocuWare テクニカルサポート"
    )


# ---------------------------------------------------------------------------
# Public API (signature unchanged)
# ---------------------------------------------------------------------------

class DraftResult:
    """Return value of generate_draft."""
    __slots__ = ("draft", "llm_fallback", "rag_sources")

    def __init__(self, draft: str, llm_fallback: bool, rag_sources: list[str]) -> None:
        self.draft = draft
        self.llm_fallback = llm_fallback
        self.rag_sources = rag_sources


def _prepend_rejection(message: str, reason: str | None) -> str:
    """Prepend rejection reason block to a user message if present."""
    if not reason:
        return message
    return f"【前回の差し戻し理由】\n{reason.strip()}\n\n{message}"


def generate_draft(
    ticket_subject: str,
    ticket_body: str,
    previous_draft: str | None = None,
    review_notes: str | None = None,
    rejection_reason: str | None = None,
) -> DraftResult:
    """Generate a customer reply draft.

    Flow:
      Step 1: RAG search (ChromaDB)
        → hits above threshold → use RAG context with chat_sync
        → no useful hits      → Step 2
      Step 2: Web search (Anthropic web_search tool)
        → success  → return web-search-augmented reply
        → failure  → Step 3
      Step 3: LLM only (no external context)
      Fallback: template if all LLM calls fail (llm_fallback=True)
    """
    query = f"{ticket_subject} {ticket_body}"

    # -----------------------------------------------------------------------
    # Step 1: RAG retrieval
    # -----------------------------------------------------------------------
    try:
        rag_hits = _retrieve_context(query)
    except Exception as exc:
        logger.warning("_retrieve_context raised unexpectedly: %s", exc)
        rag_hits = []

    client = AnthropicClient()

    # -----------------------------------------------------------------------
    # Step 2a: RAG context available → use it
    # -----------------------------------------------------------------------
    if rag_hits:
        user_message = _prepend_rejection(
            _build_user_message_with_rag(
                ticket_subject, ticket_body, rag_hits, previous_draft, review_notes
            ),
            rejection_reason,
        )
        rag_sources = [
            h.get("metadata", {}).get("source_url", "") for h in rag_hits
            if h.get("metadata", {}).get("source_url", "")
        ]
        logger.info("Draft strategy: RAG (%d docs) | sources: %s", len(rag_hits), rag_sources)

        try:
            # First try with web search as supplement (model can decide to search more)
            try:
                text, web_sources = client.chat_with_search_sync(DRAFT_SYSTEM_PROMPT, user_message)
                if text:
                    all_sources = list(dict.fromkeys(rag_sources + web_sources))
                    logger.info(
                        "Draft strategy: rag+web | rag_sources=%s web_sources=%s",
                        rag_sources, web_sources,
                    )
                    return DraftResult(draft=text, llm_fallback=False, rag_sources=all_sources)
            except LLMServiceError:
                # Web search not available for this model/tier — fall back to plain chat
                pass

            text = client.chat_sync(DRAFT_SYSTEM_PROMPT, user_message)
            logger.info("Draft strategy: rag | sources=%s", rag_sources)
            return DraftResult(draft=text, llm_fallback=False, rag_sources=rag_sources)

        except Exception as exc:
            logger.warning("LLM call with RAG context failed: %s", exc)
            # Fall through to web-only attempt

    # -----------------------------------------------------------------------
    # Step 2b: No RAG hits → try web search
    # -----------------------------------------------------------------------
    logger.info("Draft strategy: web search (no useful RAG hits)")
    user_message_web = _prepend_rejection(
        _build_user_message_web_search(
            ticket_subject, ticket_body, previous_draft, review_notes
        ),
        rejection_reason,
    )

    try:
        text, web_sources = client.chat_with_search_sync(DRAFT_SYSTEM_PROMPT, user_message_web)
        if text:
            logger.info("Draft strategy: web | sources=%s", web_sources)
            return DraftResult(draft=text, llm_fallback=False, rag_sources=web_sources)
        logger.warning("chat_with_search returned empty text, falling back")
    except LLMServiceError as exc:
        logger.warning("Web search failed: %s — trying LLM-only", exc)
    except Exception as exc:
        logger.warning("Unexpected web search error: %s — trying LLM-only", exc)

    # -----------------------------------------------------------------------
    # Step 3: LLM only (no external context)
    # -----------------------------------------------------------------------
    logger.info("Draft strategy: LLM-only (no external context)")
    user_message_plain = _prepend_rejection(
        _build_user_message_no_context(
            ticket_subject, ticket_body, previous_draft, review_notes
        ),
        rejection_reason,
    )

    try:
        text = client.chat_sync(DRAFT_SYSTEM_PROMPT, user_message_plain)
        return DraftResult(draft=text, llm_fallback=False, rag_sources=[])
    except Exception as exc:
        logger.warning("LLM-only draft also failed: %s — using template fallback", exc)
        fallback_text = _fallback_draft(ticket_subject, ticket_body, previous_draft, review_notes)
        return DraftResult(draft=fallback_text, llm_fallback=True, rag_sources=[])
