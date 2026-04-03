from datetime import datetime

import pandas as pd
import streamlit as st

from app.db.session import SessionLocal
from app.services.workflow_service import approve_workflow_run, get_iteration_history, run_and_persist_workflow

st.set_page_config(page_title="Support Workflow Dashboard", layout="wide")
st.title("DocuWare Internal Support Workflow")

if "workflow_run_id" not in st.session_state:
    st.session_state.workflow_run_id = None
if "result" not in st.session_state:
    st.session_state.result = None

with st.form("run_workflow"):
    external_id = st.text_input("External Ticket ID", value=f"sp-{int(datetime.utcnow().timestamp())}")
    customer_email = st.text_input("Customer Email", value="customer@example.com")
    subject = st.text_input("Subject", value="DocuWare indexing issue")
    body = st.text_area(
        "Body",
        value="Customer cannot retrieve newly indexed documents in expected folders.",
    )
    submitted = st.form_submit_button("Run Workflow")

if submitted:
    with SessionLocal() as db:
        workflow_run, result = run_and_persist_workflow(
            db=db,
            external_id=external_id,
            customer_email=customer_email,
            subject=subject,
            body=body,
        )
    st.session_state.workflow_run_id = workflow_run.id
    st.session_state.result = result

result = st.session_state.result
workflow_run_id = st.session_state.workflow_run_id

if result:
    st.subheader("Final Workflow Output")
    c1, c2 = st.columns(2)
    c1.metric("Final Status", result["status"])
    c2.metric("Next Action", result["next_action"])

    st.write("Final Draft Response")
    st.code(result["draft_response"])

    st.write("Review Notes")
    st.write(result["review_notes"])

    with SessionLocal() as db:
        history = get_iteration_history(db, workflow_run_id)

    history_rows = [
        {
            "iteration": row.iteration,
            "decision": row.decision,
            "review_notes": row.review_notes,
            "draft_response": row.draft_response,
        }
        for row in history
    ]
    st.write("Iteration History")
    st.dataframe(pd.DataFrame(history_rows), use_container_width=True)

    if result["status"] == "needs_human_approval":
        approver = st.text_input("Approver", value="team.lead@company.com")
        notes = st.text_input("Approval Notes", value="Looks good to send")
        if st.button("Human Approve", type="primary"):
            with SessionLocal() as db:
                approved_run = approve_workflow_run(db, workflow_run_id, approver=approver, notes=notes)
            result["status"] = approved_run.status.value
            result["next_action"] = approved_run.next_action
            st.session_state.result = result
            st.success("Approval saved and workflow updated.")
