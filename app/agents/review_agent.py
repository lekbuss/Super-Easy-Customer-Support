from typing import Literal


Decision = Literal["approve", "revise", "escalate"]


def review_draft(draft: str, iteration: int) -> tuple[Decision, str]:
    if not draft.strip():
        raise ValueError("Draft is empty")
    lowered = draft.lower()
    if "legal" in lowered or "security incident" in lowered:
        return "escalate", "法務またはセキュリティの専門担当による確認が必要です。"
    if iteration < 1:
        return "revise", "顧客ごとの具体的な対処手順と期待される結果を、もう少し明確にしてください。"
    return "approve", "案内内容は基準を満たしており、そのまま送付可能です。"
