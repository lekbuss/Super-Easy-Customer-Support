from typing import Literal


Decision = Literal["approve", "revise", "escalate"]


def review_draft(draft: str, iteration: int) -> tuple[Decision, str]:
    if not draft.strip():
        raise ValueError("Draft is empty")
    lowered = draft.lower()
    if "legal" in lowered or "security incident" in lowered:
        return "escalate", "Requires specialist legal/security handling"
    if iteration < 1:
        return "revise", "Clarify customer-specific remediation steps and expected outcome"
    return "approve", "Draft meets baseline review rules"
