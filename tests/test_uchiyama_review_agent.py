"""Tests for the Uchiyama-modelled review agent and UchiyamaProfile."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy-key")

from app.agents.review_agent import (  # noqa: E402
    _build_review_user_message,
    _contains_escalation_keyword,
    _make_notes_json,
    _parse_llm_json,
    _rule_based_review,
    review_draft,
)
from app.agents.uchiyama_profile import UchiyamaProfile  # noqa: E402
from app.llm.client import LLMServiceError  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_llm_response(decision: str, comment: str, concerns: list[str], suggestions: str) -> str:
    return json.dumps(
        {
            "decision": decision,
            "review_comment": comment,
            "key_concerns": concerns,
            "suggestions": suggestions,
        },
        ensure_ascii=False,
    )


def _mock_client(return_value: str) -> MagicMock:
    client = MagicMock()
    client.chat_sync.return_value = return_value
    return client


# ---------------------------------------------------------------------------
# UchiyamaProfile tests
# ---------------------------------------------------------------------------

class TestUchiyamaProfile:
    def test_load_examples_from_real_file(self):
        profile = UchiyamaProfile()
        examples = profile.load_examples()
        assert len(examples) == 21

    def test_get_relevant_examples_keyword_match(self):
        profile = UchiyamaProfile()
        results = profile.get_relevant_examples("Desktop Apps インストール", top_k=3)
        assert len(results) <= 3
        # Desktop Apps examples should rank higher
        topics = [ex["ticket_topic"] for ex in results]
        assert any("Desktop Apps" in t for t in topics)

    def test_get_relevant_examples_fills_with_balanced_decisions(self):
        profile = UchiyamaProfile()
        # Use a topic unlikely to match anything
        results = profile.get_relevant_examples("全く関係ない話題xyzxyz", top_k=4)
        assert len(results) <= 4
        decisions = [ex.get("decision") for ex in results]
        # Should contain at least one approve and one revise
        assert "approve" in decisions
        assert "revise" in decisions

    def test_get_relevant_examples_empty_topic(self):
        profile = UchiyamaProfile()
        results = profile.get_relevant_examples("", top_k=3)
        assert isinstance(results, list)
        assert len(results) <= 3

    def test_format_few_shot_non_empty(self):
        profile = UchiyamaProfile()
        examples = profile.load_examples()[:2]
        shot = profile.format_few_shot(examples)
        assert "【過去のレビュー事例（参考）】" in shot
        assert "事例1:" in shot
        assert "事例2:" in shot

    def test_format_few_shot_empty_list(self):
        profile = UchiyamaProfile()
        assert profile.format_few_shot([]) == ""

    def test_load_from_missing_file_returns_empty(self):
        profile = UchiyamaProfile(examples_path="/nonexistent/path.json")
        assert profile.load_examples() == []

    def test_get_relevant_examples_missing_file_returns_empty(self):
        profile = UchiyamaProfile(examples_path="/nonexistent/path.json")
        results = profile.get_relevant_examples("Desktop Apps", top_k=3)
        assert results == []


# ---------------------------------------------------------------------------
# _rule_based_review tests
# ---------------------------------------------------------------------------

class TestRuleBasedReview:
    def test_escalate_on_legal_keyword(self):
        decision, notes_json = _rule_based_review("This involves legal action.", 0)
        assert decision == "escalate"
        data = json.loads(notes_json)
        assert data["decision"] == "escalate"

    def test_escalate_on_security_incident(self):
        decision, notes_json = _rule_based_review("security incident occurred", 0)
        assert decision == "escalate"

    def test_revise_on_iteration_zero(self):
        decision, notes_json = _rule_based_review("普通の回答ドラフトです。", 0)
        assert decision == "revise"
        data = json.loads(notes_json)
        assert data["decision"] == "revise"
        assert data["suggestions"]

    def test_approve_on_iteration_one_or_more(self):
        decision, notes_json = _rule_based_review("普通の回答ドラフトです。", 1)
        assert decision == "approve"
        data = json.loads(notes_json)
        assert data["decision"] == "approve"
        assert data["suggestions"] == ""


# ---------------------------------------------------------------------------
# review_draft — LLM approve path
# ---------------------------------------------------------------------------

class TestReviewDraftApprove:
    def test_approve_returns_correct_tuple(self):
        llm_response = _make_llm_response(
            "approve",
            "作成ありがとうございます。こちらで問題ないと思いました！",
            [],
            "",
        )
        with (
            patch("app.agents.review_agent.AnthropicClient", return_value=_mock_client(llm_response)),
            patch("app.agents.review_agent.UchiyamaProfile") as MockProfile,
        ):
            MockProfile.return_value.get_relevant_examples.return_value = []
            MockProfile.return_value.format_few_shot.return_value = ""
            decision, notes_json = review_draft("良い回答です。", iteration=1)

        assert decision == "approve"
        data = json.loads(notes_json)
        assert data["decision"] == "approve"
        assert "問題ない" in data["review_comment"]


# ---------------------------------------------------------------------------
# review_draft — LLM revise path
# ---------------------------------------------------------------------------

class TestReviewDraftRevise:
    def test_revise_returns_correct_tuple(self):
        llm_response = _make_llm_response(
            "revise",
            "作成ありがとうございます。\n手順の検証について確認させてください。",
            ["検証手順の正確性"],
            "発生日時とログを追記してください。",
        )
        with (
            patch("app.agents.review_agent.AnthropicClient", return_value=_mock_client(llm_response)),
            patch("app.agents.review_agent.UchiyamaProfile") as MockProfile,
        ):
            MockProfile.return_value.get_relevant_examples.return_value = []
            MockProfile.return_value.format_few_shot.return_value = ""
            decision, notes_json = review_draft("手順案内のドラフト", iteration=0, ticket_subject="Desktop Apps障害")

        assert decision == "revise"
        data = json.loads(notes_json)
        assert data["key_concerns"] == ["検証手順の正確性"]
        assert data["suggestions"]


# ---------------------------------------------------------------------------
# review_draft — LLM escalate path
# ---------------------------------------------------------------------------

class TestReviewDraftEscalate:
    def test_escalate_from_llm(self):
        llm_response = _make_llm_response(
            "escalate",
            "法的リスクが含まれているためエスカレーションが必要です。",
            ["法務リスク"],
            "",
        )
        with (
            patch("app.agents.review_agent.AnthropicClient", return_value=_mock_client(llm_response)),
            patch("app.agents.review_agent.UchiyamaProfile") as MockProfile,
        ):
            MockProfile.return_value.get_relevant_examples.return_value = []
            MockProfile.return_value.format_few_shot.return_value = ""
            decision, notes_json = review_draft("この問題はlegalの問題です。", iteration=1)

        assert decision == "escalate"


# ---------------------------------------------------------------------------
# review_draft — hard escalation override
# ---------------------------------------------------------------------------

class TestHardEscalationOverride:
    def test_hard_override_when_llm_approves_but_draft_contains_keyword(self):
        # LLM wrongly approves a draft containing "data breach"
        llm_response = _make_llm_response(
            "approve",
            "こちらで問題ないと思いました！",
            [],
            "",
        )
        with (
            patch("app.agents.review_agent.AnthropicClient", return_value=_mock_client(llm_response)),
            patch("app.agents.review_agent.UchiyamaProfile") as MockProfile,
        ):
            MockProfile.return_value.get_relevant_examples.return_value = []
            MockProfile.return_value.format_few_shot.return_value = ""
            decision, notes_json = review_draft(
                "data breach が発生した可能性があります。", iteration=1
            )

        assert decision == "escalate"
        data = json.loads(notes_json)
        assert data["decision"] == "escalate"

    def test_no_override_when_no_keyword(self):
        llm_response = _make_llm_response("approve", "問題ないと思いました！", [], "")
        with (
            patch("app.agents.review_agent.AnthropicClient", return_value=_mock_client(llm_response)),
            patch("app.agents.review_agent.UchiyamaProfile") as MockProfile,
        ):
            MockProfile.return_value.get_relevant_examples.return_value = []
            MockProfile.return_value.format_few_shot.return_value = ""
            decision, _ = review_draft("通常の技術サポート回答です。", iteration=1)

        assert decision == "approve"


# ---------------------------------------------------------------------------
# review_draft — JSON parse failure fallback
# ---------------------------------------------------------------------------

class TestJsonParseFallback:
    def test_falls_back_to_rule_based_on_json_error(self):
        # LLM returns invalid JSON both times → should fall back to rule-based
        client = MagicMock()
        client.chat_sync.return_value = "この文章はJSONではありません"

        with (
            patch("app.agents.review_agent.AnthropicClient", return_value=client),
            patch("app.agents.review_agent.UchiyamaProfile") as MockProfile,
        ):
            MockProfile.return_value.get_relevant_examples.return_value = []
            MockProfile.return_value.format_few_shot.return_value = ""
            decision, notes_json = review_draft("普通の回答ドラフト", iteration=1)

        # Should fall back to rule-based approve at iteration>=1
        assert decision == "approve"
        data = json.loads(notes_json)
        assert data["decision"] == "approve"

    def test_falls_back_to_rule_based_on_llm_error(self):
        client = MagicMock()
        client.chat_sync.side_effect = LLMServiceError("API timeout")

        with (
            patch("app.agents.review_agent.AnthropicClient", return_value=client),
            patch("app.agents.review_agent.UchiyamaProfile") as MockProfile,
        ):
            MockProfile.return_value.get_relevant_examples.return_value = []
            MockProfile.return_value.format_few_shot.return_value = ""
            decision, notes_json = review_draft("回答ドラフト", iteration=0)

        # Iteration 0 → rule-based revise
        assert decision == "revise"


# ---------------------------------------------------------------------------
# review_draft — empty draft raises ValueError
# ---------------------------------------------------------------------------

class TestEmptyDraft:
    def test_empty_draft_raises(self):
        with pytest.raises(ValueError, match="Draft is empty"):
            review_draft("   ", iteration=0)


# ---------------------------------------------------------------------------
# _parse_llm_json — strips markdown fences
# ---------------------------------------------------------------------------

class TestParseLlmJson:
    def test_parses_plain_json(self):
        raw = '{"decision": "approve", "review_comment": "OK", "key_concerns": [], "suggestions": ""}'
        result = _parse_llm_json(raw)
        assert result["decision"] == "approve"

    def test_strips_code_fence(self):
        raw = '```json\n{"decision": "revise", "review_comment": "test", "key_concerns": [], "suggestions": "fix it"}\n```'
        result = _parse_llm_json(raw)
        assert result["decision"] == "revise"

    def test_raises_on_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_llm_json("not json at all")
