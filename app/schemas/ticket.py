from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.db.models import WorkflowStatus


class TicketCreate(BaseModel):
    external_id: str
    customer_email: EmailStr
    subject: str
    body: str


class TicketRead(BaseModel):
    id: int
    external_id: str
    customer_email: str
    subject: str
    body: str
    status: WorkflowStatus
    created_at: datetime

    model_config = {"from_attributes": True}
