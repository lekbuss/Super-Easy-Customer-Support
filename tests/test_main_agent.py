"""Tests for app.agents.main_agent.generate_draft."""
import os
from unittest.mock import MagicMock, patch

import pytest

# Provide a dummy key so Settings validation passes before any mock is applied.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy-key")

from app.agents.main_agent import (  # noqa: E402
    _build_user_message,
    _format_rag_block,
    _retrieve_context,
    generate_draft,
)
from app.llm.client import LLMServiceError  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_client(return_value: str = "LLM generated reply") -> MagicMock:
    client = MagicMock()
    client.chat_sync.return_value = return_value
    return client


def _make_hit(
    text: str,
    title: str = "Test Article",
    source_url: str = "https://example.com/KBA-001",
) -> dict:
    return {
        "text": text,
        "score": 0.92,
        "metadata": {
            "source_url": source_url,
            "title": title,
            "kba_id": "KBA-001",
            "category": "CAT-001",
        },
    }


def _mock_vectorstore(hits: list[dict], count: int = 10) -> MagicMock:
    store = MagicMock()
    store.count.return_value = count
    store.search.return_value = hits
    return store


# ---------------------------------------------------------------------------
# _format_rag_block
# ---------------------------------------------------------------------------

class TestFormatRagBlock:
    def test_empty_hits_returns_empty_string(self):
        assert _format_rag_block([]) == ""

    def test_block_contains_chunk_text(self):
        hits = [_make_hit("Step 1: Check the index settings.")]
        block = _format_rag_block(hits)
        assert "Step 1: Check the index settings." in block

    def test_block_contains_source_title(self):
        hits = [_make_hit("Some content", title="Indexing Guide")]
        block = _format_rag_block(hits)
        assert "Indexing Guide" in block

    def test_block_contains_separator_and_instruction(self):
        hits = [_make_hit("Content")]
        block = _format_rag_block(hits)
        assert "---" in block
        assert "DocuWare" in block

    def test_multiple_hits_all_included(self):
        hits = [_make_hit(f"chunk {i}", title=f"Doc {i}") for i in range(3)]
        block = _format_rag_block(hits)
        for i in range(3):
            assert f"chunk {i}" in block


# ---------------------------------------------------------------------------
# _build_user_message — with and without RAG
# ---------------------------------------------------------------------------

class TestBuildUserMessage:
    def test_initial_draft_contains_subject_and_body(self):
        msg = _build_user_message("Login error", "Cannot log in.", None, None)
        assert "Login error" in msg
        assert "Cannot log in." in msg

    def test_revision_includes_previous_draft_and_feedback(self):
        msg = _build_user_message(
            "Login error",
            "Cannot log in.",
            previous_draft="Here is a draft",
            review_notes="Add more steps",
        )
        assert "Here is a draft" in msg
        assert "Add more steps" in msg
        assert (
            "revision" in msg.lower()
            or "feedback" in msg.lower()
            or "improved" in msg.lower()
        )

    def test_no_revision_block_when_only_previous_draft(self):
        msg = _build_user_message("X", "Y", previous_draft="draft", review_notes=None)
        assert "Previous draft" not in msg

    def test_no_revision_block_when_only_review_notes(self):
        msg = _build_user_message("X", "Y", previous_draft=None, review_notes="notes")
        assert "Reviewer feedback" not in msg

    def test_rag_block_inserted_when_hits_provided(self):
        hits = [_make_hit("Relevant KB content")]
        msg = _build_user_message("Subject", "Body", None, None, rag_hits=hits)
        assert "Relevant KB content" in msg
        assert "DocuWare" in msg

    def test_no_rag_block_when_hits_empty(self):
        msg = _build_user_message("Subject", "Body", None, None, rag_hits=[])
        assert "文档片段" not in msg

    def test_rag_block_appears_before_revision_block(self):
        hits = [_make_hit("KB info")]
        msg = _build_user_message(
            "Subject", "Body",
            previous_draft="old draft",
            review_notes="fix it",
            rag_hits=hits,
        )
        assert msg.find("KB info") < msg.find("old draft")


# ---------------------------------------------------------------------------
# _retrieve_context — patch the class in its own module
# ---------------------------------------------------------------------------

# VectorStore is lazily imported inside _retrieve_context, so we patch
# the class at its definition location: app.rag.vectorstore.VectorStore

class TestRetrieveContext:
    def test_returns_hits_when_store_has_docs(self):
        hits = [_make_hit("Some doc")]
        mock_store = _mock_vectorstore(hits, count=5)
        with patch("app.rag.vectorstore.VectorStore", return_value=mock_store):
            result = _retrieve_context("indexing issue")
        assert result == hits
        mock_store.search.assert_called_once()

    def test_returns_empty_list_when_store_is_empty(self):
        mock_store = _mock_vectorstore([], count=0)
        with patch("app.rag.vectorstore.VectorStore", return_value=mock_store):
            result = _retrieve_context("any query")
        assert result == []
        mock_store.search.assert_not_called()

    def test_returns_empty_list_on_vectorstore_init_error(self):
        with patch("app.rag.vectorstore.VectorStore", side_effect=RuntimeError("DB unavailable")):
            result = _retrieve_context("any query")
        assert result == []

    def test_returns_empty_list_on_search_error(self):
        mock_store = _mock_vectorstore([], count=5)
        mock_store.search.side_effect = RuntimeError("search failed")
        with patch("app.rag.vectorstore.VectorStore", return_value=mock_store):
            result = _retrieve_context("query")
        assert result == []


# ---------------------------------------------------------------------------
# generate_draft — with RAG context
# Patch _retrieve_context directly to isolate LLM behaviour from RAG.
# ---------------------------------------------------------------------------

class TestGenerateDraftWithRAG:
    def test_rag_context_included_in_llm_call(self):
        hits = [_make_hit("Check the indexing pipeline.", title="Indexing Guide")]
        mock_client = _mock_client("LLM reply with RAG")

        with patch("app.agents.main_agent._retrieve_context", return_value=hits), \
             patch("app.agents.main_agent.AnthropicClient", return_value=mock_client):
            result = generate_draft("Indexing issue", "Docs not found")

        assert result == "LLM reply with RAG"
        user_msg = mock_client.chat_sync.call_args[0][1]
        assert "Check the indexing pipeline." in user_msg
        assert "Indexing Guide" in user_msg

    def test_rag_query_combines_subject_and_body(self):
        mock_client = _mock_client()
        captured = {}

        def fake_retrieve(query: str) -> list[dict]:
            captured["query"] = query
            return []

        with patch("app.agents.main_agent._retrieve_context", side_effect=fake_retrieve), \
             patch("app.agents.main_agent.AnthropicClient", return_value=mock_client):
            generate_draft("Login failure", "Password reset not working")

        assert "Login failure" in captured["query"]
        assert "Password reset not working" in captured["query"]


# ---------------------------------------------------------------------------
# generate_draft — without RAG (degraded path)
# ---------------------------------------------------------------------------

class TestGenerateDraftWithoutRAG:
    def test_proceeds_when_retrieve_returns_empty(self):
        mock_client = _mock_client("LLM reply no RAG")
        with patch("app.agents.main_agent._retrieve_context", return_value=[]), \
             patch("app.agents.main_agent.AnthropicClient", return_value=mock_client):
            result = generate_draft("Subject", "Body")
        assert result == "LLM reply no RAG"

    def test_no_rag_block_in_message_when_no_hits(self):
        mock_client = _mock_client()
        with patch("app.agents.main_agent._retrieve_context", return_value=[]), \
             patch("app.agents.main_agent.AnthropicClient", return_value=mock_client):
            generate_draft("Subject", "Body")
        user_msg = mock_client.chat_sync.call_args[0][1]
        assert "文档片段" not in user_msg

    def test_proceeds_when_retrieve_raises(self):
        mock_client = _mock_client("fallback LLM reply")
        with patch("app.agents.main_agent._retrieve_context", side_effect=RuntimeError("rag error")), \
             patch("app.agents.main_agent.AnthropicClient", return_value=mock_client):
            # _retrieve_context already swallows errors internally, but even if it
            # somehow propagates, generate_draft should still fall back gracefully.
            result = generate_draft("Subject", "Body")
        assert isinstance(result, str) and len(result) > 0


# ---------------------------------------------------------------------------
# generate_draft — LLM fallback (existing behaviour preserved)
# ---------------------------------------------------------------------------

class TestGenerateDraftLLMFallback:
    def test_fallback_on_llm_service_error(self):
        mock_client = MagicMock()
        mock_client.chat_sync.side_effect = LLMServiceError("API down")
        with patch("app.agents.main_agent._retrieve_context", return_value=[]), \
             patch("app.agents.main_agent.AnthropicClient", return_value=mock_client):
            result = generate_draft("Subject", "Body text")
        assert isinstance(result, str) and len(result) > 0
        assert "Subject" in result

    def test_fallback_on_unexpected_exception(self):
        mock_client = MagicMock()
        mock_client.chat_sync.side_effect = RuntimeError("unexpected")
        with patch("app.agents.main_agent._retrieve_context", return_value=[]), \
             patch("app.agents.main_agent.AnthropicClient", return_value=mock_client):
            result = generate_draft("Subject", "Body")
        assert isinstance(result, str) and len(result) > 0

    def test_fallback_revision_contains_review_notes(self):
        mock_client = MagicMock()
        mock_client.chat_sync.side_effect = LLMServiceError("fail")
        with patch("app.agents.main_agent._retrieve_context", return_value=[]), \
             patch("app.agents.main_agent.AnthropicClient", return_value=mock_client):
            result = generate_draft(
                "Subject", "Body",
                previous_draft="prev",
                review_notes="needs improvement",
            )
        assert "needs improvement" in result

    def test_returns_string(self):
        hits = [_make_hit("KB chunk")]
        mock_client = _mock_client("reply")
        with patch("app.agents.main_agent._retrieve_context", return_value=hits), \
             patch("app.agents.main_agent.AnthropicClient", return_value=mock_client):
            result = generate_draft("S", "B")
        assert isinstance(result, str)
