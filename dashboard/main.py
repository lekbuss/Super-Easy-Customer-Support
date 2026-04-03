import sys
from pathlib import Path
from datetime import datetime, UTC

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st

from app.workflows.support_workflow import run_support_workflow

st.set_page_config(page_title="Support Workflow Dashboard", layout="wide")
st.title("DocuWare Internal Support Workflow")

if "result" not in st.session_state:
    st.session_state.result = None

with st.form("run_workflow"):
    ticket_id = st.number_input("Ticket ID", min_value=1, value=1, step=1)
    external_id = st.text_input(
        "External Ticket ID",
        value=f"sp-{int(datetime.now(UTC).timestamp())}"
    )
    customer_email = st.text_input("Customer Email", value="customer@example.com")
    subject = st.text_input("Subject", value="DocuWare indexing issue")
    body = st.text_area(
        "Body",
        value="Customer cannot retrieve newly indexed documents in expected folders.",
    )
    submitted = st.form_submit_button("Run Workflow")

if submitted:
    result = run_support_workflow(ticket_id=ticket_id, subject=subject, body=body)
    result["external_id"] = external_id
    result["customer_email"] = customer_email
    st.session_state.result = result

result = st.session_state.result

if result:
    st.subheader("Final Workflow Output")
    c1, c2 = st.columns(2)
    c1.metric("Final Status", result.get("status", "unknown"))
    c2.metric("Next Action", result.get("next_action", "unknown"))

    st.write("Final Draft Response")
    st.code(result.get("draft_response", ""))

    st.write("Review Notes")
    st.write(result.get("review_notes", ""))

    st.write("Iteration History")
    st.json(result.get("iteration_history", []))

    if result.get("status") == "needs_human_approval":
        approver = st.text_input("Approver", value="team.lead@company.com")
        notes = st.text_input("Approval Notes", value="Looks good to send")
        if st.button("Human Approve", type="primary"):
            result["status"] = "human_approved"
            result["next_action"] = "ready_to_send"
            result["approved_by"] = approver
            result["approval_notes"] = notes
            st.session_state.result = result
            st.success("Approval saved in session state.")