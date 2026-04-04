from sqlalchemy.orm import Session

from app.db.models import WorkflowStatus
from app.services.ticket_service import get_ticket_by_id
from app.services.workflow_service import get_workflow_outcome


def build_workflow_drafts(db: Session, workflow_run_id: int) -> dict | None:
    outcome = get_workflow_outcome(db, workflow_run_id)
    if outcome is None:
        return None

    workflow_run, steps, approvals = outcome
    ticket = get_ticket_by_id(db, workflow_run.ticket_id)
    if ticket is None:
        return None

    customer_reply_draft = None
    if workflow_run.final_draft_response and workflow_run.status in {
        WorkflowStatus.needs_human_approval,
        WorkflowStatus.approved,
    }:
        customer_reply_draft = (
            f"いつもお世話になっております。\n\n"
            f"チケット {ticket.external_id} について、以下のとおりご案内いたします。\n\n"
            f"{workflow_run.final_draft_response}\n\n"
            f"どうぞよろしくお願いいたします。\n"
            f"DocuWare テクニカルサポート"
        )

    vendor_escalation_draft = None
    if workflow_run.status == WorkflowStatus.escalated or workflow_run.final_decision == "escalate":
        latest_notes = workflow_run.final_review_notes or "レビューコメントは記録されていません。"
        vendor_escalation_draft = (
            f"件名: チケット {ticket.external_id} のエスカレーション\n\n"
            f"顧客: {ticket.customer_email}\n"
            f"事象: {ticket.subject}\n"
            f"詳細: {ticket.body}\n\n"
            f"エスカレーション理由:\n{latest_notes}\n"
        )

    approval_text = "なし"
    if approvals:
        last = approvals[-1]
        approval_text = f"{last.approver} により {last.action}"

    internal_summary = (
        f"チケット {ticket.external_id} ({ticket.source}) の現在の状態は "
        f"「{workflow_run.status.value}」です。"
        f"ワークフロー実行 #{workflow_run.id} の最終判断は "
        f"「{workflow_run.final_decision}」です。"
        f"反復回数は {workflow_run.iteration_count} 回、"
        f"記録済みステップは {len(steps)} 件です。"
        f"最新の承認情報は {approval_text}。"
        f"次のアクションは {workflow_run.next_action or 'なし'} です。"
    )

    return {
        "workflow_run_id": workflow_run.id,
        "ticket_id": ticket.id,
        "customer_reply_draft": customer_reply_draft,
        "vendor_escalation_draft": vendor_escalation_draft,
        "internal_summary": internal_summary,
    }
