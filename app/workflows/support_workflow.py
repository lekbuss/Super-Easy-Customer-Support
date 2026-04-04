import json
from typing import Any, Literal, TypedDict

try:
    from langgraph.graph import END, StateGraph
except Exception:
    END = "__END__"
    StateGraph = None

from app.agents.main_agent import DraftResult, generate_draft
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
    llm_fallback: bool
    rag_sources: list[str]


def main_agent_node(state: SupportState) -> SupportState:
    try:
        result: DraftResult = generate_draft(state["subject"], state["body"])
        return {
            **state,
            "draft_response": result.draft,
            "llm_fallback": result.llm_fallback,
            "rag_sources": result.rag_sources,
            "status": "reviewing",
            "next_action": "review_draft",
        }
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
        decision, notes = review_draft(
            state["draft_response"],
            state["iteration"],
            ticket_subject=state.get("subject", ""),
            ticket_body=state.get("body", ""),
        )
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


def _readable_review_notes(notes_json: str) -> str:
    """Extract human-readable text from JSON review notes for use in revision prompts."""
    try:
        data = json.loads(notes_json)
        comment = data.get("review_comment", "")
        suggestions = data.get("suggestions", "")
        if suggestions:
            return f"{comment}\n\n修正提案: {suggestions}"
        return comment
    except (json.JSONDecodeError, TypeError):
        return notes_json


def revise_node(state: SupportState) -> SupportState:
    try:
        result: DraftResult = generate_draft(
            ticket_subject=state["subject"],
            ticket_body=state["body"],
            previous_draft=state["draft_response"],
            review_notes=_readable_review_notes(state["review_notes"]),
        )
        return {
            **state,
            "draft_response": result.draft,
            "llm_fallback": result.llm_fallback,
            "rag_sources": result.rag_sources,
            "iteration": state["iteration"] + 1,
            "status": "revising",
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


class LocalWorkflowApp:
    def invoke(self, state: SupportState) -> SupportState:
        current = main_agent_node(state)
        while True:
            current = review_agent_node(current)
            route = route_after_review(current)
            if route == "revise":
                current = revise_node(current)
                continue
            if route == "finish":
                return finish_node(current)
            return escalate_node(current)


def build_support_workflow() -> Any:
    if StateGraph is None:
        return LocalWorkflowApp()

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
        "llm_fallback": False,
        "rag_sources": [],
    }
    return app.invoke(initial_state)
