"""Database work for CRM tickets.

The chatbot node only calls the functions below, so all the SQLAlchemy code stays
here and out of the graph.
"""
from sqlalchemy.orm import Session

from models.db_models import Booking, GuestSession, Ticket


def save_conversation_ticket_handler(
    db: Session,
    guest_session_id: int,
    transcript: list[dict],
    category: str,
) -> dict:
    """
    Save the conversation transcript into the CRM ticket table.

    Creates the guest session row when it is missing, reuses the latest ticket of that
    session (or creates one), and links it to the latest booking when there is one.
    """
    # The ticket points at a guest session, so that row has to exist first.
    if not db.query(GuestSession).filter_by(id=guest_session_id).first():
        db.add(GuestSession(id=guest_session_id, session_token_hash=f"cli-token-{guest_session_id}"))
        db.commit()

    booking = (
        db.query(Booking)
        .filter_by(guest_session_id=guest_session_id)
        .order_by(Booking.created_at.desc())
        .first()
    )

    ticket = (
        db.query(Ticket)
        .filter_by(guest_session_id=guest_session_id)
        .order_by(Ticket.created_at.desc())
        .first()
    )
    if ticket is None:
        ticket = Ticket(guest_session_id=guest_session_id)
        db.add(ticket)

    ticket.messages = transcript
    ticket.category = category
    ticket.booking_id = booking.id if booking else ticket.booking_id
    ticket.status = "RESOLVED" if ticket.booking_id else "OPEN"
    db.commit()
    db.refresh(ticket)

    return {
        "crm_ticket_id": f"TKT-{ticket.id:05d}",
        "ticket_id": ticket.id,
        "status": ticket.status,
    }
