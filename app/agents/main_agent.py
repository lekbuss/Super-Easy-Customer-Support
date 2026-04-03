def generate_draft(ticket_subject: str, ticket_body: str) -> str:
    return (
        f"Draft response for '{ticket_subject}'. "
        "We reviewed your DocuWare issue and prepared initial troubleshooting steps. "
        f"Original request: {ticket_body[:200]}"
    )
