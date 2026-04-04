import logging

from app.core.config import settings
from app.llm.client import AnthropicClient, LLMServiceError
from app.llm.prompts import DRAFT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RAG retrieval (optional - degrades gracefully if unavailable)
# ---------------------------------------------------------------------------

def _retrieve_context(query: str) -> list[dict]:
    """Return relevant KB chunks for the query, or [] on any error."""
    try:
        from app.rag.vectorstore import VectorStore  # lazy import

        store = VectorStore()
        if store.count() == 0:
            logger.debug("VectorStore is empty, skipping RAG retrieval")
            return []
        return store.search(query, top_k=settings.rag_top_k)
    except Exception as exc:
        logger.warning("RAG retrieval failed, continuing without context: %s", exc)
        return []



def _format_rag_block(hits: list[dict]) -> str:
    """Format retrieved chunks into a labelled block for the user message."""
    if not hits:
        return ""

    lines = ["以下はチケットに関連する DocuWare 公式ナレッジベースの抜粋です。", "---"]
    for i, hit in enumerate(hits, start=1):
        source = hit.get("metadata", {}).get("source_url", "unknown")
        title = hit.get("metadata", {}).get("title", "")
        label = f"[資料 {i} / 出典: {title or source}]"
        lines.append(label)
        lines.append(hit.get("text", "").strip())
        lines.append("")

    lines += [
        "---",
        "まず上記の資料を優先して参照し、実行可能な案内を作成してください。"
        "情報が不足する場合でも、先に試せる手順を示し、最後に必要な確認事項だけを補ってください。",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# User message construction
# ---------------------------------------------------------------------------

def _build_user_message(
    ticket_subject: str,
    ticket_body: str,
    previous_draft: str | None,
    review_notes: str | None,
    rag_hits: list[dict] | None = None,
) -> str:
    lines = [
        f"件名: {ticket_subject}",
        f"顧客からの問い合わせ:\n{ticket_body.strip()}",
        "",
        "重要: 顧客への返信文は必ず自然な日本語で作成してください。"
        "原文が中国語や英語であっても、出力は日本語のみにしてください。",
    ]

    rag_block = _format_rag_block(rag_hits or [])
    if rag_block:
        lines += ["", rag_block]

    if previous_draft and review_notes:
        lines += [
            "",
            "以下のレビューコメントにもとづき、既存の下書きを改善してください。",
            f"前回の下書き:\n{previous_draft.strip()}",
            f"レビューコメント:\n{review_notes.strip()}",
            "",
            "レビュー内容を反映した改訂版の返信文を日本語で作成してください。",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fallback (no LLM)
# ---------------------------------------------------------------------------

def _fallback_draft(
    ticket_subject: str,
    ticket_body: str,
    previous_draft: str | None,
    review_notes: str | None,
) -> str:
    context = ticket_body.strip()
    if previous_draft and review_notes:
        return (
            f"{ticket_subject} に関する改訂版のご案内です。\n\n"
            f"レビュー内容: {review_notes.strip()}\n\n"
            f"{previous_draft.strip()}\n\n"
            "DocuWare テクニカルサポート"
        )
    return (
        f"{ticket_subject} についてご連絡ありがとうございます。\n\n"
        "現在確認できている内容にもとづき、まずお試しいただきたい初期対応手順をご案内します。\n\n"
        f"お問い合わせ内容:\n{context[:300]}\n\n"
        "DocuWare テクニカルサポート"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_draft(
    ticket_subject: str,
    ticket_body: str,
    previous_draft: str | None = None,
    review_notes: str | None = None,
) -> str:
    # 1. RAG retrieval (non-blocking - double-guarded)
    query = f"{ticket_subject} {ticket_body}"
    try:
        rag_hits = _retrieve_context(query)
    except Exception as exc:
        logger.warning("_retrieve_context raised unexpectedly: %s", exc)
        rag_hits = []

    if rag_hits:
        logger.info("RAG retrieved %d chunks for query", len(rag_hits))
    else:
        logger.debug("No RAG context available, proceeding with LLM only")

    # 2. Build user message (with or without RAG context)
    user_message = _build_user_message(
        ticket_subject, ticket_body, previous_draft, review_notes, rag_hits
    )

    # 3. LLM call with fallback
    try:
        client = AnthropicClient()
        return client.chat_sync(DRAFT_SYSTEM_PROMPT, user_message)
    except LLMServiceError as exc:
        logger.warning("LLM draft generation failed, using fallback template: %s", exc)
        return _fallback_draft(ticket_subject, ticket_body, previous_draft, review_notes)
    except Exception as exc:
        logger.warning(
            "Unexpected error during LLM draft generation, using fallback template: %s",
            exc,
        )
        return _fallback_draft(ticket_subject, ticket_body, previous_draft, review_notes)
