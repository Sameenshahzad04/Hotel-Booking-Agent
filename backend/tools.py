"""
Tool wrappers for the HotelAgent LangGraph chatbot.

This module provides pure Python functions that the LangGraph agent can call
as tools. These functions wrap the handler functions from the backend modules
and expose them in a format suitable for LangChain's StructuredTool.

The tools are designed to be called by the agent with the same parameters
as the original handler functions, but without the FastAPI dependencies
and HTTP request/response context.
"""

from datetime import date
from typing import Dict, List, Any, Optional
from contextlib import contextmanager

# Import handler functions
from handler.booking_handler import (
    create_booking_hold_handler,
    cancel_unpaid_booking_handler
)
from handler.availability_handler import query_live_availability
from models.connection import get_db
from models.db_models import Booking
from util.status_util import compute_display_status


@contextmanager
def _get_db_context():
    """Context manager for database sessions."""
    db = next(get_db())
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# BOOKING TOOLS
# ============================================================================

def search_availability_tool(check_in: date, check_out: date, guests: int = 1, session_id: int = None) -> dict:
    """Search available rooms for given dates.
    
    Args:
        check_in: Check-in date (YYYY-MM-DD)
        check_out: Check-out date (YYYY-MM-DD)
        guests: Number of guests (default 1)
        session_id: Optional guest session ID for context
    
    Returns:
        Availability data for the requested dates
    """
    with _get_db_context() as db:
        if check_out <= check_in:
            return {"error": "Check-out date must be strictly after check-in date."}
        availability = query_live_availability(db, check_in=check_in, check_out=check_out, guests=guests)
        return {
            "check_in": check_in,
            "check_out": check_out,
            "guests": guests,
            "availability": availability
        }


def create_booking_tool(check_in: date, check_out: date, guests: int, rooms: Dict[int, int], services: List[Dict[str, Any]], 
                        guest_name: str, guest_email: str, session_id: int = None) -> dict:
    """Create an UNPAID 2-hour booking hold. Server assigns physical rooms.
    
    Args:
        check_in: Check-in date (YYYY-MM-DD)
        check_out: Check-out date (YYYY-MM-DD)
        guests: Number of guests
        rooms: Room allocations {room_type_id: quantity}
        services: Selected services [{service_id, quantity}]
        guest_name: Guest name
        guest_email: Guest email
        session_id: Optional guest session ID
    
    Returns:
        Booking confirmation with ref, total amount, and expiry
    """
    with _get_db_context() as db:
        booking = create_booking_hold_handler(
            db=db,
            guest_session_id=session_id or 0,
            guest_name=guest_name,
            guest_email=guest_email,
            check_in=check_in,
            check_out=check_out,
            guests=guests,
            room_allocations=rooms,
            selected_services=services
        )
        status_info = compute_display_status(booking)
        return {
            "success": True,
            "booking_ref": booking.booking_ref,
            "confirmation_code": None,
            "total_amount": booking.total_amount,
            "currency": "PKR",
            "hold_expires_at": booking.hold_expires_at,
            "status": status_info
        }


def list_my_bookings_tool(session_id: int = None) -> dict:
    """List the guest's bookings with computed statuses.
    
    Args:
        session_id: Optional guest session ID
    
    Returns:
        List of bookings with computed statuses
    """
    with _get_db_context() as db:
        session = session_id or 0
        bookings = (
            db.query(Booking)
            .filter_by(guest_session_id=session)
            .order_by(Booking.created_at.desc())
            .all()
        )
        
        items = []
        for b in bookings:
            status_info = compute_display_status(b)
            items.append({
                "booking_ref": b.booking_ref,
                "confirmation_code": b.confirmation_code if b.payment_status == "PAID" else None,
                "guest_name": b.guest_name,
                "check_in": b.check_in,
                "check_out": b.check_out,
                "nights": (b.check_out - b.check_in).days,
                "guests": b.guests,
                "rooms": [br.room.room_type.name for br in b.booking_rooms],
                "total_amount": b.total_amount,
                "status": status_info
            })
        
        return {"bookings": items}


def explain_status_tool(ref: str) -> dict:
    """Get full details of one booking.
    
    Args:
        ref: Booking reference
    
    Returns:
        Full booking details
    """
    with _get_db_context() as db:
        booking = db.query(Booking).filter_by(booking_ref=ref).first()
        if not booking:
            return {"error": "Booking not found.", "ref": ref}
        
        status_info = compute_display_status(booking)
        return {
            "booking_ref": booking.booking_ref,
            "confirmation_code": booking.confirmation_code,
            "guest_name": booking.guest_name,
            "guest_email": booking.guest_email,
            "check_in": booking.check_in,
            "check_out": booking.check_out,
            "nights": (booking.check_out - booking.check_in).days,
            "guests": booking.guests,
            "rooms": [
                {
                    "room_type": br.room.room_type.name,
                    "price_per_night": br.price_per_night,
                    "room_number": br.room.room_number if booking.payment_status == "PAID" else None
                }
                for br in booking.booking_rooms
            ],
            "services": [
                {
                    "name": bs.service.name,
                    "quantity": bs.quantity,
                    "unit_price": bs.unit_price
                }
                for bs in booking.booking_services
            ],
            "total_amount": booking.total_amount,
            "currency": "PKR",
            "hold_expires_at": booking.hold_expires_at,
            "status": status_info
        }


def claim_booking_tool(confirmation_code: str, email: str, session_id: int = None) -> dict:
    """Link an existing booking to this browser session.
    
    Args:
        confirmation_code: Booking confirmation code
        email: Guest email matching the booking
        session_id: Optional guest session ID
    
    Returns:
        Success message
    """
    with _get_db_context() as db:
        booking = (
            db.query(Booking)
            .filter_by(confirmation_code=confirmation_code.strip())
            .first()
        )
        if not booking or booking.guest_email.lower().strip() != email.lower().strip():
            return {"error": "Invalid confirmation code or email mismatch."}
        
        booking.guest_session_id = session_id or 0
        db.commit()
        return {"success": True, "message": "Booking linked successfully to this browser session."}


def cancel_booking_tool(ref: str, session_id: int = None) -> dict:
    """Cancel an unpaid, unexpired booking hold and free the rooms.
    
    Args:
        ref: Booking reference
        session_id: Optional guest session ID
    
    Returns:
        Cancellation result
    """
    with _get_db_context() as db:
        try:
            return cancel_unpaid_booking_handler(
                db=db, 
                booking_ref=ref, 
                guest_session_id=session_id or 0
            )
        except PermissionError as e:
            return {"error": "Permission denied: " + str(e)}
        except ValueError as e:
            return {"error": str(e)}


def checkout_link_tool(ref: str) -> dict:
    """Return the Checkout page URL so the guest can pay.
    
    Args:
        ref: Booking reference
    
    Returns:
        Checkout URL for the booking
    """
    with _get_db_context() as db:
        booking = db.query(Booking).filter_by(booking_ref=ref).first()
        if not booking:
            return {"error": "Booking not found.", "ref": ref}
        return {
            "booking_ref": ref,
            "checkout_url": f"/bookings/{ref}/pay",
            "total_amount": booking.total_amount,
            "currency": "PKR"
        }


def cancel_booking_with_confirmation_tool(booking_ref: str, confirmation_code: str = None) -> dict:
    """Cancel a booking with human confirmation. Requires booking reference.
    
    Args:
        booking_ref: Booking reference
        confirmation_code: Optional confirmation code
    
    Returns:
        Cancellation result
    """
    with _get_db_context() as db:
        if confirmation_code:
            booking = (
                db.query(Booking)
                .filter_by(confirmation_code=confirmation_code.strip())
                .first()
            )
            if not booking or booking.booking_ref != booking_ref:
                return {"error": "Confirmation code mismatch."}
        else:
            booking = db.query(Booking).filter_by(booking_ref=booking_ref).first()
        
        if not booking:
            return {"error": "Booking not found.", "ref": booking_ref}
        
        try:
            return cancel_unpaid_booking_handler(
                db=db, 
                booking_ref=booking_ref, 
                guest_session_id=booking.guest_session_id or 0
            )
        except PermissionError as e:
            return {"error": "Permission denied: " + str(e)}
        except ValueError as e:
            return {"error": str(e)}


# ============================================================================
# RAG TOOLS


def search_hostel_knowledge_base(query: str, category: str = None, session_id: int = None) -> dict:
    """Search the hostel official documentation, rules, booking policies, amenities, and FAQ vector database.
    
    Args:
        query: Search query
        category: Optional category filter (e.g. category='billing')
        session_id: Optional guest session ID for context
    
    Returns:
        Search results from the knowledge base
    """
    from rag.vector_store import get_retriever
    
    try:
        retriever = get_retriever()
        if not retriever:
            return {"error": "Vector store not initialized."}
        
        # For now, we'll just use the basic search - category filtering would require
        # more sophisticated vector store queries
        docs = retriever.invoke(query)
        return {
            "query": query,
            "results": [
                {
                    "content": doc.page_content,
                    "metadata": doc.metadata
                }
                for doc in docs
            ]
        }
    except Exception as e:
        return {"error": f"Search failed: {str(e)}"}
# SENTIMENT AND INTENT ANALYSIS TOOLS
# ============================================================================

def analyze_customer_interaction(ticket_text: str) -> str:
    """Analyzes customer emotional tone and intent in a single call.
    
    Returns: '<sentiment> | <intent> | (1-line reason)'
    
    Args:
        ticket_text: The customer's message
    
    Returns:
        Formatted string with sentiment, intent, and reason
    """
    from chatbot.tools.sentiment_detector import detect_customer_sentiment
    from chatbot.tools.intent_analyzer import analyze_ticket_intent
    
    try:
        sentiment = detect_customer_sentiment(ticket_text)
        intent = analyze_ticket_intent(ticket_text)
        
        # Extract the sentiment category from the formatted string
        sentiment_category = sentiment.split("|")[0].strip()
        
        return f"{sentiment_category} | {intent} | Customer inquiry"
    except Exception as e:
        return f"neutral | OTHER | Error analyzing customer interaction: {str(e)}"


# ============================================================================
# EXPORT ALL TOOLS
# ============================================================================

__all__ = [
    # Booking tools
    "search_availability_tool",
    "create_booking_tool",
    "list_my_bookings_tool",
    "explain_status_tool",
    "claim_booking_tool",
    "cancel_booking_tool",
    "checkout_link_tool",

    "cancel_booking_with_confirmation_tool",
    
    # RAG tools

    "search_hostel_knowledge_base",
    
    # Sentiment and intent analysis tools
    "analyze_customer_interaction",
]