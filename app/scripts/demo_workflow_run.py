import json

from app.workflows.support_workflow import run_support_workflow


if __name__ == "__main__":
    result = run_support_workflow(
        ticket_id=101,
        subject="DocuWare indexing issue",
        body="Customer cannot retrieve newly indexed documents in expected folders.",
    )
    print(json.dumps(result, indent=2))
