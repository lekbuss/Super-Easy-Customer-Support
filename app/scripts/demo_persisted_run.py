import json
from datetime import datetime

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.services.workflow_service import approve_workflow_run, get_iteration_history, run_and_persist_workflow


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        workflow_run, result = run_and_persist_workflow(
            db=db,
            external_id=f"demo-{int(datetime.utcnow().timestamp())}",
            customer_email="customer@example.com",
            subject="DocuWare indexing issue",
            body="Customer cannot retrieve newly indexed documents in expected folders.",
        )
        history = get_iteration_history(db, workflow_run.id)
        output = {
            "workflow_run_id": workflow_run.id,
            "status": result["status"],
            "next_action": result["next_action"],
            "history_count": len(history),
        }

        if result["status"] == "needs_human_approval":
            approved_run = approve_workflow_run(db, workflow_run.id, approver="demo.approver@company.com", notes="Approved in demo")
            output["approved_status"] = approved_run.status.value
            output["approved_next_action"] = approved_run.next_action

    print(json.dumps(output, indent=2))
