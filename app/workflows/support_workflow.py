from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph

from app.agents.main_agent import generate_draft
from app.agents.review_agent import review_draft
from app.core.config import settings


Decision = Literal["approve", "revise", "escalate"]
Status = Literal[
    "drafting",
    "reviewing",
    "revising",
    "needs_human_approval",
    "escalated",
    "failed",
]


class IterationRecord(TypedDict):
    iteration: int
    draft_response: str
    review_notes: str
    decision: Decision


class SupportState(TypedDict):
    ticket_id: int
    subject: str
    body: str
    status: Status
    draft_response: str
    review_notes: str
    decision: Decision | None
    iteration: int
    max_iterations: int
    iteration_history: list[IterationRecord]
    needs_human_approval: bool
    escalated: bool
    escalation_reason: str | None
    next_action: str


def main_agent_node(state: SupportState) -> SupportState:
    try:
        draft = generate_draft(state["subject"], state["body"])
        return {**state, "draft_response": draft, "status": "reviewing", "next_action": "review_draft"}
    except Exception as exc:
        return {
            **state,
            "status": "failed",
            "escalation_reason": f"main_agent_error: {exc}",
            "next_action": "manual_triage",
            "escalated": True,
        }


def review_agent_node(state: SupportState) -> SupportState:
    try:
        decision, notes = review_draft(state["draft_response"], state["iteration"])
        history = [
            *state["iteration_history"],
            {
                "iteration": state["iteration"],
                "draft_response": state["draft_response"],
                "review_notes": notes,
                "decision": decision,
            },
        ]
        return {
            **state,
            "decision": decision,
            "review_notes": notes,
            "iteration_history": history,
            "status": "reviewing",
            "next_action": f"route_{decision}",
        }
    except Exception as exc:
        return {
            **state,
            "status": "failed",
            "decision": "escalate",
            "escalation_reason": f"review_agent_error: {exc}",
            "next_action": "manual_triage",
            "escalated": True,
        }


def revise_node(state: SupportState) -> SupportState:
    try:
        revised_draft = generate_draft(
            ticket_subject=state["subject"],
            ticket_body=state["body"],
            previous_draft=state["draft_response"],
            review_notes=state["review_notes"],
        )
        return {
            **state,
            "draft_response": revised_draft,
            "iteration": state["iteration"] + 1,
            "status": "reviewing",
            "next_action": "review_revised_draft",
        }
    except Exception as exc:
        return {
            **state,
            "status": "failed",
            "decision": "escalate",
            "escalation_reason": f"revise_error: {exc}",
            "next_action": "manual_triage",
            "escalated": True,
        }


def finish_node(state: SupportState) -> SupportState:
    return {
        **state,
        "status": "needs_human_approval",
        "needs_human_approval": True,
        "escalated": False,
        "next_action": "await_human_approval",
    }


def escalate_node(state: SupportState) -> SupportState:
    reason = state["escalation_reason"]
    if not reason:
        reason = "Review agent escalated ticket"
    return {
        **state,
        "status": "escalated",
        "needs_human_approval": False,
        "escalated": True,
        "escalation_reason": reason,
        "next_action": "assign_to_human_specialist",
    }


def route_after_review(state: SupportState) -> str:
    if state["status"] == "failed":
        return "escalate"
    if state["decision"] == "approve":
        return "finish"
    if state["decision"] == "escalate":
        return "escalate"
    if state["iteration"] >= state["max_iterations"]:
        return "escalate"
    return "revise"


def build_support_workflow():
    graph = StateGraph(SupportState)
    graph.add_node("main_agent", main_agent_node)
    graph.add_node("review_agent", review_agent_node)
    graph.add_node("revise", revise_node)
    graph.add_node("finish", finish_node)
    graph.add_node("escalate", escalate_node)

    graph.set_entry_point("main_agent")
    graph.add_edge("main_agent", "review_agent")
    graph.add_conditional_edges(
        "review_agent",
        route_after_review,
        {"revise": "revise", "finish": "finish", "escalate": "escalate"},
    )
    graph.add_edge("revise", "review_agent")
    graph.add_edge("finish", END)
    graph.add_edge("escalate", END)

    return graph.compile()


def run_support_workflow(ticket_id: int, subject: str, body: str):
    app = build_support_workflow()
    initial_state: SupportState = {
        "ticket_id": ticket_id,
        "subject": subject,
        "body": body,
        "status": "drafting",
        "draft_response": "",
        "review_notes": "",
        "decision": None,
        "iteration": 0,
        "max_iterations": settings.max_review_iterations,
        "iteration_history": [],
        "needs_human_approval": False,
        "escalated": False,
        "escalation_reason": None,
        "next_action": "generate_initial_draft",
    }
    return app.invoke(initial_state)
