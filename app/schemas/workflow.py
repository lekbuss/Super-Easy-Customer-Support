from typing import Literal

from pydantic import BaseModel


class WorkflowStartRequest(BaseModel):
    ticket_id: int


class WorkflowStateResponse(BaseModel):
    ticket_id: int
    draft_response: str
    decision: Literal["approve", "revise", "escalate"]
    iteration: int
    needs_human_approval: bool
    escalated: bool
