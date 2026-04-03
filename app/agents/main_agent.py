def generate_draft(
    ticket_subject: str,
    ticket_body: str,
    previous_draft: str | None = None,
    review_notes: str | None = None,
) -> str:
    context = ticket_body.strip()
    if previous_draft and review_notes:
        return (
            f"Revised draft for '{ticket_subject}'. "
            f"Applied review guidance: {review_notes.strip()} "
            f"Updated response: {previous_draft.strip()}"
        )
    return (
        f"Draft response for '{ticket_subject}'. "
        "We reviewed your DocuWare issue and prepared initial troubleshooting steps. "
        f"Original request: {context[:300]}"
    )
