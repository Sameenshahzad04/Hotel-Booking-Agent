"""
Guest Service Tools for Pearl Continental (PC) Hotel Concierge Agent.

All tools here use LangChain's `@tool` decorator so that LLMs can inspect
their schemas, parameter types, and docstrings for native tool calling.
"""

from datetime import date
from typing import Optional, List
from contextlib import contextmanager
import sys
import logging
from pathlib import Path
from langchain_core.tools import tool

# Ensure backend root directory is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from handler.booking_handler import (
    create_booking_hold_handler,
    cancel_unpaid_booking_handler
)
from handler.availability_handler import query_live_availability
from models.connection import get_db
from models.db_models import Booking
from util.status_util import compute_display_status

# ---------------------------------------------------------------------------
# DIAGNOSTIC LOGGING (instrumentation for the "cannot handle it" investigation)
# Records every tool-level failure / fallback so we can see which paths return
# raw internal error text to the guest instead of a graceful Front Desk message.
# ---------------------------------------------------------------------------
logger = logging.getLogger("pc_agent.tools")
if not logger.handlers:
    # ASCII-only prefix: the Windows console (cp1252) cannot encode emoji.
    _diag_handler = logging.StreamHandler(sys.stdout)
    _diag_handler.setFormatter(logging.Formatter("[DIAG] %(message)s"))
    logger.addHandler(_diag_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


@contextmanager
def _get_db_context():
    """Context manager for database sessions."""
    db = next(get_db())
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# 1. KNOWLEDGE BASE & POLICY TOOLS (RAG)
# ============================================================================

@tool
def search_hotel_policies_tool(query: str) -> str:
    """
    Search official hotel documentation, policies, amenities, timings, dining, and FAQs.
    Call this tool when the guest asks:
    - Check-in / check-out times
    - Breakfast, restaurant, or dining hours
    - Pet policy, smoking policy, dress code
    - Gym, pool, spa location and facilities
    - Cancellation rules, fees, and refund policy terms

    If no policy matches, instructs the guest to contact the Front Desk directly.
    """
    from rag.vector_store import get_retriever

    FRONT_DESK_FALLBACK = (
        "I could not locate specific information about that in our official policy guide. "
        "Please visit our Front Desk in the main lobby or call our 24/7 Concierge at "
        "+92-42-111-505-505 / frontdesk@pchotels.com for assistance."
    )

    try:
        retriever = get_retriever()
        if not retriever:
            return FRONT_DESK_FALLBACK

        docs = retriever.invoke(query)
        if not docs:
            return FRONT_DESK_FALLBACK

        formatted_snippets = []
        for doc in docs[:3]:
            source = doc.metadata.get("filename", "Hotel Handbook")
            formatted_snippets.append(f"[{source}]:\n{doc.page_content.strip()}")

        return "\n\n".join(formatted_snippets)

    except Exception as e:
        return f"{FRONT_DESK_FALLBACK} (Technical error: {str(e)})"


# ============================================================================
# 2. AVAILABILITY & BOOKING MANAGEMENT TOOLS
# ============================================================================

@tool
def search_room_availability_tool(check_in: str, check_out: str, guests: int = 1) -> str:
    """
    Search live room availability for specific dates.
    Args:
        check_in: Check-in date in YYYY-MM-DD format (e.g. '2026-10-20')
        check_out: Check-out date in YYYY-MM-DD format (e.g. '2026-10-22')
        guests: Number of guests (default 1)
    """
    try:
        d_in = date.fromisoformat(check_in)
        d_out = date.fromisoformat(check_out)
    except ValueError:
        logger.warning("TOOL search_room_availability -> RAW ERROR returned to guest (bad date format)")
        return "Error: Dates must be in YYYY-MM-DD format."

    if d_out <= d_in:
        logger.warning("TOOL search_room_availability -> RAW ERROR returned to guest (bad date range)")
        return "Error: Check-out date must be strictly after check-in date."

    with _get_db_context() as db:
        availability = query_live_availability(db, check_in=d_in, check_out=d_out, guests=guests)
        if not availability:
            logger.info("TOOL search_room_availability -> no inventory for %s..%s", check_in, check_out)
            return f"No rooms available between {check_in} and {check_out} for {guests} guest(s)."

        results = [f"Available options from {check_in} to {check_out}:"]
        for room in availability:
            name = room.get("name") or room.get("room_type", "Standard Room")
            bed_type = room.get("bed_type", "Standard Bed")
            max_guests = room.get("max_guests", 2)
            price = room.get("base_price", "N/A")
            avail_rooms = room.get("available_rooms", 0)
            amenities_list = room.get("amenities", [])
            amenities_str = ", ".join(amenities_list) if amenities_list else "Free Wi-Fi, Central AC, Safe"
            results.append(
                f"- Room Type: {name} (Internal ID: {room.get('room_type_id')}) | Beds: {bed_type} "
                f"| Max Guests: {max_guests} | Available: {avail_rooms} | Rate: PKR {price:,.0f} / night | "
                f"Amenities: {amenities_str}"
            )
        return "\n".join(results)


@tool
def create_booking_hold_tool(
    room_type_id: int,
    check_in: str,
    check_out: str,
    guests: int,
    guest_name: str,
    guest_email: str,
    quantity: int = 1,
    session_id: int = 1
) -> str:
    """
    Creates an unpaid 2-hour booking hold for room(s).
    ONLY invoke this tool AFTER the guest has explicitly provided their real full name, email, and preferred room type.
    NEVER invoke with dummy or placeholder names like '[Guest Name]' or '[Guest Email]'.
    Args:
        room_type_id: Numeric ID of the room type chosen by the guest
        check_in: Check-in date in YYYY-MM-DD format
        check_out: Check-out date in YYYY-MM-DD format
        guests: Total number of guests
        guest_name: Real full name provided by the guest
        guest_email: Real email address provided by the guest
        quantity: Number of rooms of this type to book (default 1). For groups, book enough rooms so total capacity >= guests.
        session_id: Internal session ID (automatically assigned, do not ask the user)
    """
    try:
        d_in = date.fromisoformat(check_in)
        d_out = date.fromisoformat(check_out)
    except ValueError:
        logger.warning("TOOL create_booking_hold -> RAW ERROR returned to guest (bad date format)")
        return "Error: Dates must be in YYYY-MM-DD format."

    with _get_db_context() as db:
        try:
            booking = create_booking_hold_handler(
                db=db,
                guest_session_id=session_id,
                guest_name=guest_name,
                guest_email=guest_email,
                check_in=d_in,
                check_out=d_out,
                guests=guests,
                room_allocations={room_type_id: quantity},
                selected_services=[]
            )
            return (
                f"Booking hold successfully created and saved in database!\n"
                f"Booking Reference: {booking.booking_ref}\n"
                f"Guest: {booking.guest_name} ({booking.guest_email})\n"
                f"Total Amount: PKR {booking.total_amount:,.2f}\n"
                f"Status: PENDING (UNPAID)\n"
                f"Hold expires at: {booking.hold_expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                f"To confirm reservation and receive your Confirmation Code, complete payment here: "
                f"http://localhost:3000/checkout/{booking.booking_ref}"
            )
        except Exception as e:
            logger.exception("TOOL create_booking_hold -> FAILED (raw exception text goes to the guest)")
            return f"Failed to create booking hold: {str(e)}"

# Inside list_guest_bookings_tool implementation:
def mask_code(code: str) -> str:
    if len(code) <= 4:
        return "****"
    return code[:2] + "****" + code[-2:]  # e.g., HB-H86LFM -> HB****FM


@tool
def list_guest_bookings_tool(session_id: int = 1) -> str:
    """
    List all bookings made by the current guest in this session.
    Automatically retrieves bookings using the active guest session.
    Args:
        session_id: Active guest session ID (automatically assigned, do not ask the user)
    """
    with _get_db_context() as db:
        bookings = (
            db.query(Booking)
            .filter_by(guest_session_id=session_id)
            .order_by(Booking.created_at.desc())
            .all()
        )
        if not bookings:
            logger.info("TOOL list_guest_bookings -> session %s has no bookings", session_id)
            return "You currently have no bookings in this session."

        output = [f"Found {len(bookings)} booking(s):"]
        for b in bookings:
            status_info = compute_display_status(b)
            code_str = f" | Confirmation: {b.confirmation_code}" if b.confirmation_code else ""
            output.append(
                f"- Ref: {b.booking_ref}{code_str} | Status: {status_info} "
                f"| Dates: {b.check_in} to {b.check_out} | Total: PKR {b.total_amount:.2f}"
            )
        output = [f"Found {len(bookings)} booking(s):"]
        for b in bookings:
            status_info = compute_display_status(b)
            masked_ref = mask_code(b.booking_ref)
            code_str = f" | Confirmation: {b.confirmation_code}" if b.confirmation_code else ""
            output.append(
                f"- Ref: {masked_ref}{code_str} | Status: {status_info} "
                f"| Dates: {b.check_in} to {b.check_out} | Total: PKR {b.total_amount:.2f}"
            )
        return "\n".join(output)


@tool
def cancel_booking_tool(booking_ref: str, session_id: int = 1) -> str:
    """
    Cancel an unpaid, unexpired booking hold and release the room.
    ONLY call this tool AFTER the guest has provided their real Booking Reference (e.g. 'HB-...').
    NEVER call with dummy placeholders like '[Booking Reference]' or '[HB-...]'.
    Args:
        booking_ref: The real booking reference provided by the guest (e.g. 'HB-...')
        session_id: Active guest session ID (automatically assigned, do not ask the user)
    """
    with _get_db_context() as db:
        try:
            res = cancel_unpaid_booking_handler(
                db=db,
                booking_ref=booking_ref,
                guest_session_id=session_id
            )
            return f"Booking {booking_ref} cancelled successfully. Rooms released."
        except Exception as e:
            logger.exception("TOOL cancel_booking -> FAILED (raw exception text goes to the guest)")
            return f"Cancellation failed: {str(e)}"


@tool
def request_claim_otp_tool(identifier: str, email: str) -> str:
    """
    Step 1 of Cross-Session Booking Re-linking (Bank-Grade Security):
    Sends a 6-digit One-Time Verification Code (OTP) to the guest's private email address.
    Call this when a guest in a new session wants to check, view, or claim their booking using
    their Booking Reference (BK-...) and Email.
    Args:
        identifier: Booking Reference (e.g. 'BK-509965') or Confirmation Code
        email: The exact guest email used during booking
    """
    clean_id = identifier.strip()
    clean_email = email.strip().lower()

    with _get_db_context() as db:
        booking = (
            db.query(Booking)
            .filter((Booking.booking_ref == clean_id) | (Booking.confirmation_code == clean_id))
            .first()
        )
        if not booking or booking.guest_email.lower().strip() != clean_email:
            return "Security Check Failed: No reservation found matching that reference and email combination."

        import secrets
        from datetime import datetime, timedelta, timezone
        from models.db_models import BookingOTP
        from util.email_service import send_smtp_email
        from config import config

        otp_code = f"{secrets.randbelow(900000) + 100000}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=config.OTP_EXPIRY_MINUTES)

        db.query(BookingOTP).filter_by(booking_id=booking.id, is_used=False).update({"is_used": True})
        otp_record = BookingOTP(
            booking_id=booking.id,
            target_email=clean_email,
            otp_code=otp_code,
            expires_at=expires_at,
            is_used=False
        )
        db.add(otp_record)
        db.commit()

        email_body = (
            f"Dear {booking.guest_name},\n\n"
            f"You requested to view/link your booking ({booking.booking_ref}) in our concierge chat.\n\n"
            f"Your 6-Digit One-Time Verification Code is: {otp_code}\n\n"
            f"This code will expire in {config.OTP_EXPIRY_MINUTES} minutes.\n\n"
            f"Pearl Continental Hotel Lahore Concierge Team"
        )
        send_smtp_email(
            to_email=clean_email,
            subject=f"PC Lahore Verification Code: {otp_code}",
            body_text=email_body
        )

        parts = clean_email.split("@")
        masked = parts[0][0] + "***@" + parts[1] if len(parts) == 2 else clean_email
        return (
            f"Verification code sent! To verify your ownership of booking {booking.booking_ref}, "
            f"we just emailed a 6-digit code to {masked}. "
            f"Please reply with the 6-digit code to complete verification."
        )


@tool
def verify_claim_otp_tool(identifier: str, email: str, otp_code: str, session_id: int = 1) -> str:
    """
    Step 2 of Cross-Session Booking Re-linking:
    Verifies the 6-digit code from the guest's email and securely links the booking to this session.
    Args:
        identifier: Booking Reference (e.g. 'BK-509965') or Confirmation Code
        email: The guest's email address
        otp_code: The 6-digit numeric OTP code sent to the guest's email
        session_id: Active guest session ID (automatically assigned, do not ask the user)
    """
    clean_id = identifier.strip()
    clean_email = email.strip().lower()
    clean_otp = otp_code.strip()

    with _get_db_context() as db:
        booking = (
            db.query(Booking)
            .filter((Booking.booking_ref == clean_id) | (Booking.confirmation_code == clean_id))
            .first()
        )
        if not booking or booking.guest_email.lower().strip() != clean_email:
            return "Security Verification Failed: Invalid booking reference or email."

        from datetime import datetime, timezone
        from models.db_models import BookingOTP

        now = datetime.now(timezone.utc)
        otp_record = (
            db.query(BookingOTP)
            .filter(
                BookingOTP.booking_id == booking.id,
                BookingOTP.target_email == clean_email,
                BookingOTP.otp_code == clean_otp,
                BookingOTP.is_used == False,
                BookingOTP.expires_at >= now
            )
            .first()
        )
        if not otp_record:
            return "Invalid or expired verification code. Please request a new code."

        otp_record.is_used = True
        booking.guest_session_id = session_id
        db.commit()

        status_info = compute_display_status(booking)
        code_str = f" | Confirmation Code: {booking.confirmation_code}" if booking.confirmation_code else " (Unpaid Hold - Confirmation code issued upon payment)"
        return (
            f"Success! Booking {booking.booking_ref} has been verified and securely linked to your session.\n"
            f"- Status: {status_info}{code_str}\n"
            f"- Guest Name: {booking.guest_name}\n"
            f"- Dates: {booking.check_in} to {booking.check_out}\n"
            f"- Total: PKR {booking.total_amount:,.2f}"
        )


@tool
def claim_booking_tool(identifier: str, email: str, session_id: int = 1) -> str:
    """
    Re-link an existing booking directly if OTP is not required.
    Guest must provide BOTH:
    1. Their Booking Reference (e.g., 'BK-...') OR Confirmation Code (e.g., 'PC-CONF-...')
    2. The exact Email address used during the reservation.

    Args:
        identifier: Booking reference (BK-...) or confirmation code (PC-CONF-...) provided by guest
        email: Exact guest email address used during booking
        session_id: Active guest session ID (automatically assigned, do not ask the user)
    """
    clean_id = identifier.strip()
    clean_email = email.strip().lower()

    with _get_db_context() as db:
        booking = (
            db.query(Booking)
            .filter((Booking.confirmation_code == clean_id) | (Booking.booking_ref == clean_id))
            .first()
        )
        if not booking or booking.guest_email.lower().strip() != clean_email:
            logger.warning("TOOL claim_booking -> security mismatch for identifier=%s email=%s", clean_id, clean_email)
            return "Security Verification Failed: No booking found matching that reference/code and email combination."

        booking.guest_session_id = session_id
        db.commit()
        status_info = compute_display_status(booking)
        return (
            f"Booking {booking.booking_ref} has been verified and successfully linked to your current session!\n"
            f"- Status: {status_info}\n"
            f"- Dates: {booking.check_in} to {booking.check_out}\n"
            f"- Total: PKR {booking.total_amount:,.2f}"
        )


# ============================================================================
# 3. SECURE REDIRECTION TOOLS (PAYMENT & REFUND PORTALS)
# ============================================================================

@tool
def get_payment_checkout_link_tool(booking_ref: str, session_id: int = 1) -> str:
    """
    Provides the secure checkout page link so the guest can pay for an unpaid booking hold.
    Never collect credit card numbers in the chat!
    ONLY call this tool AFTER the guest provides their real Booking Reference (e.g. 'HB-...').
    NEVER call with dummy placeholders like '[Booking Reference]' or '[HB-...]'.
    Args:
        booking_ref: Real booking reference provided by the guest
        session_id: Active guest session ID (automatically assigned, do not ask the user)
    """
    with _get_db_context() as db:
        booking = db.query(Booking).filter_by(booking_ref=booking_ref, guest_session_id=session_id).first()
        if not booking:
            logger.warning("TOOL get_payment_checkout_link -> booking %s not found in session", booking_ref)
            return f"Booking {booking_ref} not found for this session."

        if booking.payment_status == "PAID":
            return f"Booking {booking_ref} is already paid and confirmed."

        return (
            f"Please complete your payment safely on our checkout portal: "
            f"http://localhost:3000/checkout/{booking.booking_ref} (Total: PKR {booking.total_amount:.2f})"
        )


@tool
def get_refund_portal_link_tool(booking_ref: str, session_id: int = 1) -> str:
    """
    Provides the secure refund request portal link for a paid booking.
    Financial refunds must be submitted through the portal after verifying policy.
    ONLY call this tool AFTER the guest provides their real Booking Reference (e.g. 'HB-...').
    NEVER call with dummy placeholders like '[Booking Reference]' or '[HB-...]'.
    Args:
        booking_ref: Real booking reference provided by the guest
        session_id: Active guest session ID (automatically assigned, do not ask the user)
    """
    with _get_db_context() as db:
        booking = db.query(Booking).filter_by(booking_ref=booking_ref, guest_session_id=session_id).first()
        if not booking:
            logger.warning("TOOL get_refund_portal_link -> booking %s not found in session", booking_ref)
            return f"Booking {booking_ref} not found for this session."

        return (
            f"To review cancellation policies and initiate a refund for booking {booking_ref}, "
            f"please visit: http://localhost:3000/refunds/{booking.booking_ref}"
        )


ALL_GUEST_TOOLS = [
    search_hotel_policies_tool,
    search_room_availability_tool,
    create_booking_hold_tool,
    list_guest_bookings_tool,
    cancel_booking_tool,
    claim_booking_tool,
    request_claim_otp_tool,
    verify_claim_otp_tool,
    get_payment_checkout_link_tool,
    get_refund_portal_link_tool
]
