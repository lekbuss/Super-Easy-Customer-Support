"""UchiyamaProfile — few-shot example loader for the Uchiyama review agent."""
from __future__ import annotations

import json
import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)

_EXAMPLES_PATH = Path(__file__).resolve().parents[2] / "app" / "data" / "review_examples.json"


class UchiyamaProfile:
    """Loads and retrieves past review examples authored by Uchiyama Seizo."""

    def __init__(self, examples_path: str | Path | None = None) -> None:
        self._path = Path(examples_path) if examples_path else _EXAMPLES_PATH
        self._examples: list[dict] = self._load_examples()

    def _load_examples(self) -> list[dict]:
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Failed to load review examples from %s: %s", self._path, exc)
            return []

    def load_examples(self) -> list[dict]:
        return self._examples

    def get_relevant_examples(self, ticket_topic: str, top_k: int = 5) -> list[dict]:
        """Return up to top_k examples most relevant to ticket_topic.

        Strategy:
        1. Keyword overlap scoring against example ticket_topic fields.
        2. If not enough scored matches, fill remaining slots with a balanced
           approve/revise mix chosen randomly.
        """
        if not self._examples:
            return []

        topic_lower = ticket_topic.lower()
        words = set(topic_lower.split())

        scored: list[tuple[int, dict]] = []
        for ex in self._examples:
            ex_topic = ex.get("ticket_topic", "").lower()
            ex_words = set(ex_topic.split())
            score = len(words & ex_words)
            scored.append((score, ex))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Take examples that actually matched at least one keyword
        matched = [ex for score, ex in scored if score > 0]
        top = matched[:top_k]

        if len(top) >= top_k:
            return top

        # Fill remaining with balanced approve/revise selection
        already_ids = {ex["case_id"] for ex in top}
        approve_pool = [
            ex for ex in self._examples
            if ex.get("decision") == "approve" and ex["case_id"] not in already_ids
        ]
        revise_pool = [
            ex for ex in self._examples
            if ex.get("decision") == "revise" and ex["case_id"] not in already_ids
        ]

        random.shuffle(approve_pool)
        random.shuffle(revise_pool)

        fill: list[dict] = []
        ai, ri = 0, 0
        needed = top_k - len(top)
        while len(fill) < needed:
            added = False
            if ai < len(approve_pool):
                fill.append(approve_pool[ai])
                ai += 1
                added = True
            if len(fill) < needed and ri < len(revise_pool):
                fill.append(revise_pool[ri])
                ri += 1
                added = True
            if not added:
                break

        return top + fill

    def format_few_shot(self, examples: list[dict]) -> str:
        """Format examples into a few-shot prompt block."""
        if not examples:
            return ""

        lines = ["【過去のレビュー事例（参考）】", ""]
        for i, ex in enumerate(examples, start=1):
            lines.append(f"事例{i}:")
            lines.append(f"案件: {ex.get('ticket_topic', '')}")
            summary = ex.get("draft_summary", "")
            if summary:
                lines.append(f"ドラフト概要: {summary}")
            lines.append(f"内山のレビュー: {ex.get('uchiyama_review', '')}")
            lines.append(f"判定: {ex.get('decision', '')}")
            lines.append("")

        return "\n".join(lines)
