from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph

from app.agents.main_agent import generate_draft
from app.agents.review_agent import review_draft
from app.core.config import settings


Decision = Literal["approve", "revise", "escalate"]


class SupportState(TypedDict):
    ticket_id: int
    subject: str
    body: str
    draft_response: str
    review_notes: str
    decision: Decision
    iteration: int
    max_iterations: int
    needs_human_approval: bool
    escalated: bool


def main_agent_node(state: SupportState) -> SupportState:
    draft = generate_draft(state["subject"], state["body"])
    return {**state, "draft_response": draft}


def review_agent_node(state: SupportState) -> SupportState:
    decision, notes = review_draft(state["draft_response"], state["iteration"])
    return {**state, "decision": decision, "review_notes": notes}


def revise_node(state: SupportState) -> SupportState:
    revised = state["draft_response"] + "\n\nApplied reviewer revisions."
    return {**state, "draft_response": revised, "iteration": state["iteration"] + 1}


def finish_node(state: SupportState) -> SupportState:
    return {**state, "needs_human_approval": True, "escalated": False}


def escalate_node(state: SupportState) -> SupportState:
    return {**state, "needs_human_approval": False, "escalated": True}


def route_after_review(state: SupportState) -> str:
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
        "draft_response": "",
        "review_notes": "",
        "decision": "revise",
        "iteration": 0,
        "max_iterations": settings.max_review_iterations,
        "needs_human_approval": False,
        "escalated": False,
    }
    return app.invoke(initial_state)
