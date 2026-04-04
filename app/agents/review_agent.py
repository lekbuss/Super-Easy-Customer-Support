"""Review agent modelled after Uchiyama Seizo's review style.

The agent calls Claude with few-shot examples from UchiyamaProfile and returns
a structured JSON review result. Rule-based logic is used as fallback when the
LLM is unavailable.

review_notes are stored as JSON strings so callers can parse structured fields
(review_comment, key_concerns, suggestions). Callers that display notes as
plain text should extract the "review_comment" field.
"""
from __future__ import annotations

import json
import logging
from typing import Literal

from app.agents.uchiyama_profile import UchiyamaProfile
from app.llm.client import AnthropicClient, LLMServiceError
from app.llm.prompts import UCHIYAMA_REVIEW_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

Decision = Literal["approve", "revise", "escalate"]

_HARD_ESCALATE_KEYWORDS = [
    "legal",
    "security incident",
    "data breach",
    "個人情報漏洩",
    "データ侵害",
    "情報漏洩",
    "訴訟",
    "コンプライアンス違反",
]


def _contains_escalation_keyword(text: str) -> bool:
    lower = text.lower()
    for kw in _HARD_ESCALATE_KEYWORDS:
        if kw in lower or kw in text:
            return True
    return False


def _make_notes_json(
    decision: str,
    review_comment: str,
    key_concerns: list[str],
    suggestions: str,
) -> str:
    return json.dumps(
        {
            "decision": decision,
            "review_comment": review_comment,
            "key_concerns": key_concerns,
            "suggestions": suggestions,
        },
        ensure_ascii=False,
    )


def _rule_based_review(draft: str, iteration: int) -> tuple[Decision, str]:
    """Fallback rule-based review used when LLM is unavailable."""
    if _contains_escalation_keyword(draft):
        return "escalate", _make_notes_json(
            "escalate",
            "法務またはセキュリティの専門担当による確認が必要です。",
            ["法務・セキュリティリスク"],
            "",
        )
    if iteration < 1:
        return "revise", _make_notes_json(
            "revise",
            "顧客ごとの具体的な対処手順と期待される結果を、もう少し明確にしてください。",
            ["具体的手順の明確化"],
            "具体的な手順と期待される結果を追記してください。",
        )
    return "approve", _make_notes_json(
        "approve",
        "案内内容は基準を満たしており、そのまま送付可能です。",
        [],
        "",
    )


def _parse_llm_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    return json.loads(text.strip())


def _build_review_user_message(
    ticket_subject: str,
    ticket_body: str,
    draft: str,
    iteration: int,
    few_shot: str,
) -> str:
    lines: list[str] = []

    if few_shot:
        lines.append(few_shot)
        lines.append("")

    lines.append("【今回の審査タスク】")
    lines.append("")
    if ticket_subject:
        lines.append(f"案件タイトル: {ticket_subject}")
    if ticket_body:
        preview = ticket_body.strip()[:400]
        lines.append(f"問い合わせ内容（抜粋）:\n{preview}")
    lines.append(f"現在の反復回数: {iteration}")
    lines.append("")
    lines.append("レビュー対象ドラフト:")
    lines.append(draft.strip())
    lines.append("")
    lines.append(
        "上記ドラフトを内山靖三としてレビューし、指定のJSON形式で返答してください。"
    )

    return "\n".join(lines)


def review_draft(
    draft: str,
    iteration: int,
    ticket_subject: str = "",
    ticket_body: str = "",
) -> tuple[Decision, str]:
    """Review a draft and return (decision, notes_json).

    notes_json is a JSON string with keys:
        decision, review_comment, key_concerns, suggestions
    """
    if not draft.strip():
        raise ValueError("Draft is empty")

    try:
        profile = UchiyamaProfile()
        examples = profile.get_relevant_examples(
            ticket_subject or draft[:120], top_k=3
        )
        few_shot = profile.format_few_shot(examples)

        user_message = _build_review_user_message(
            ticket_subject=ticket_subject,
            ticket_body=ticket_body,
            draft=draft,
            iteration=iteration,
            few_shot=few_shot,
        )

        client = AnthropicClient()
        result: dict | None = None

        for attempt in range(2):
            raw = client.chat_sync(UCHIYAMA_REVIEW_SYSTEM_PROMPT, user_message)
            try:
                result = _parse_llm_json(raw)
                break
            except json.JSONDecodeError:
                if attempt == 0:
                    logger.warning(
                        "Uchiyama review: JSON parse failed on attempt 1, retrying. Raw: %.200s",
                        raw,
                    )
                else:
                    raise LLMServiceError(
                        "Uchiyama review LLM did not return valid JSON after 2 attempts"
                    )

        if result is None:
            raise LLMServiceError("No result from LLM")

        decision: str = result.get("decision", "revise")
        if decision not in ("approve", "revise", "escalate"):
            logger.warning(
                "Uchiyama review: unexpected decision '%s', defaulting to revise", decision
            )
            decision = "revise"

        # Hard escalation override: if draft contains high-risk keywords, always escalate
        if decision == "approve" and _contains_escalation_keyword(draft):
            logger.info("Uchiyama review: hard escalation override triggered")
            decision = "escalate"
            result["review_comment"] = (
                "法務・セキュリティ・個人情報に関わる内容が含まれているため、"
                "専門担当へのエスカレーションが必要です。"
            )

        result["decision"] = decision
        notes_json = json.dumps(result, ensure_ascii=False)
        return decision, notes_json  # type: ignore[return-value]

    except (LLMServiceError, Exception) as exc:
        logger.warning(
            "Uchiyama review LLM failed, using rule-based fallback: %s", exc
        )
        return _rule_based_review(draft, iteration)
