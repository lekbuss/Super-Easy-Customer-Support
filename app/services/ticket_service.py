from sqlalchemy.orm import Session

from app.db.models import Ticket, WorkflowStatus


def create_ticket(
    db: Session,
    external_id: str,
    customer_email: str,
    subject: str,
    body: str,
    source: str,
) -> Ticket:
    ticket = Ticket(
        external_id=external_id,
        customer_email=customer_email,
        subject=subject,
        body=body,
        source=source,
        status=WorkflowStatus.received,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def list_tickets(db: Session, limit: int = 50) -> list[Ticket]:
    return db.query(Ticket).order_by(Ticket.created_at.desc(), Ticket.id.desc()).limit(limit).all()


def get_ticket_by_id(db: Session, ticket_id: int) -> Ticket | None:
    return db.get(Ticket, ticket_id)
