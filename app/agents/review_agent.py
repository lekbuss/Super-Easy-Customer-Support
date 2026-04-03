from typing import Literal


Decision = Literal["approve", "revise", "escalate"]


def review_draft(draft: str, iteration: int) -> tuple[Decision, str]:
    if "escalate" in draft.lower():
        return "escalate", "Detected escalation trigger"
    if iteration < 1:
        return "revise", "First-pass quality gate requested revision"
    return "approve", "Draft meets baseline review rules"
