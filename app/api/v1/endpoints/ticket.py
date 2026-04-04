from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.ticket import TicketCreate, TicketRead
from app.services.ticket_service import create_ticket, get_ticket_by_id, list_tickets

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", response_model=TicketRead)
def create_ticket_endpoint(payload: TicketCreate, db: Session = Depends(get_db)):
    ticket = create_ticket(
        db=db,
        external_id=payload.external_id,
        customer_email=payload.customer_email,
        subject=payload.subject,
        body=payload.body,
        source=payload.source,
    )
    return ticket


@router.get("", response_model=list[TicketRead])
def list_tickets_endpoint(limit: int = 50, db: Session = Depends(get_db)):
    return list_tickets(db, limit=limit)


@router.get("/{ticket_id}", response_model=TicketRead)
def get_ticket_endpoint(ticket_id: int, db: Session = Depends(get_db)):
    ticket = get_ticket_by_id(db, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket
