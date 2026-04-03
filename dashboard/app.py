import streamlit as st

from app.workflows.support_workflow import run_support_workflow

st.set_page_config(page_title="Support Workflow Dashboard", layout="wide")
st.title("DocuWare Internal Support Workflow")

with st.form("run_workflow"):
    ticket_id = st.number_input("Ticket ID", min_value=1, value=1, step=1)
    subject = st.text_input("Subject", value="DocuWare indexing issue")
    body = st.text_area(
        "Body",
        value="Customer cannot retrieve newly indexed documents in expected folders.",
    )
    submitted = st.form_submit_button("Run Workflow")

if submitted:
    result = run_support_workflow(ticket_id=int(ticket_id), subject=subject, body=body)
    st.subheader("Workflow Output")
    st.json(result)
