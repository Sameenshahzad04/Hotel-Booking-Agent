import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from models.connection import get_db
from models.db_models import GuestSession, Booking
from schema.booking_schema import (
    BookingHoldRequest, 
    ClaimBookingRequest, 
    RequestClaimOTPRequest, 
    VerifyClaimOTPRequest
)
from router.session_router import get_current_session
from handler.booking_handler import create_booking_hold_handler, cancel_unpaid_booking_handler
from handler.payment_handler import process_payment_handler
from handler.refund_handler import process_refund_handler
from util.status_util import compute_display_status
from models.db_models import BookingOTP
from util.email_service import send_smtp_email
from config import config
import secrets
from datetime import datetime, timedelta, timezone

router = APIRouter(prefix="/bookings", tags=["Bookings"])

@router.post("")
def create_booking_hold_endpoint(
    req: BookingHoldRequest,
    session_data: tuple[GuestSession, str] = Depends(get_current_session),
    db: Session = Depends(get_db)
):
    """Creates a 2-hour unpaid booking hold."""
    session, _ = session_data
    try:
        booking = create_booking_hold_handler(
            db=db,
            guest_session_id=session.id,
            guest_name=req.guest_name,
            guest_email=req.guest_email,
            check_in=req.check_in,
            check_out=req.check_out,
            guests=req.guests,
            room_allocations=req.rooms,
            selected_services=req.services
        )
        status_info = compute_display_status(booking)
        return {
            "success": True,
            "booking_ref": booking.booking_ref,
            "total_amount": booking.total_amount,
            "currency": "PKR",
            "hold_expires_at": booking.hold_expires_at,
            "status": status_info
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Booking error: {str(e)}")

@router.get("")
def list_session_bookings(
    session_data: tuple[GuestSession, str] = Depends(get_current_session),
    db: Session = Depends(get_db)
):
    """Lists history of bookings for current session."""
    session, _ = session_data
    bookings = (
        db.query(Booking)
        .filter_by(guest_session_id=session.id)
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

@router.get("/{ref}")
def get_single_booking(
    ref: str,
    session_data: tuple[GuestSession, str] = Depends(get_current_session),
    db: Session = Depends(get_db)
):
    """Returns single booking details for checkout."""
    session, _ = session_data
    booking = db.query(Booking).filter_by(booking_ref=ref).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")

    if booking.guest_session_id != session.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this booking.")

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

@router.post("/{ref}/pay")
def pay_booking(
    ref: str,      # URL path: /bookings/HB-7f3a9c2e1b
    idempotency_key: Optional[str] = Header(None),
    session_data: tuple[GuestSession, str] = Depends(get_current_session),# Your session
    db: Session = Depends(get_db)  # Database connection
):
    """Processes payment for an unexpired hold."""
    session, _ = session_data
    key = idempotency_key or f"tx-{uuid.uuid4().hex}"

    try:
        return process_payment_handler(
            db=db,
            booking_ref=ref,
            guest_session_id=session.id,
            idempotency_key=key
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Payment processing error: {str(e)}")

@router.post("/{ref}/cancel")
def cancel_booking(
    ref: str,
    session_data: tuple[GuestSession, str] = Depends(get_current_session),
    db: Session = Depends(get_db)
):
    """Cancels unpaid pending booking."""
    session, _ = session_data
    try:
        return cancel_unpaid_booking_handler(db=db, booking_ref=ref, guest_session_id=session.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{ref}/refund")
def refund_booking(
    ref: str,
    idempotency_key: Optional[str] = Header(None),
    session_data: tuple[GuestSession, str] = Depends(get_current_session),
    db: Session = Depends(get_db)
):
    """Processes refund based on cancellation window policy."""
    session, _ = session_data
    key = idempotency_key or f"ref-{uuid.uuid4().hex}"
    try:
        return process_refund_handler(
            db=db,
            booking_ref=ref,
            guest_session_id=session.id,
            idempotency_key=key
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/claim/request-otp")
def request_claim_otp_endpoint(
    req: RequestClaimOTPRequest,
    db: Session = Depends(get_db)
):
    """
    Step 1 of Secure OTP Claim:
    Verifies that the booking exists and matches the email, then generates
    a secure 6-digit OTP and delivers it to the guest's email via SMTP.
    """
    clean_ref = req.booking_ref.strip()
    clean_email = req.email.strip().lower()

    booking = (
        db.query(Booking)
        .filter((Booking.booking_ref == clean_ref) | (Booking.confirmation_code == clean_ref))
        .first()
    )
    if not booking or booking.guest_email.lower().strip() != clean_email:
        # Generic error message to prevent account enumeration
        raise HTTPException(status_code=404, detail="No reservation matches that reference and email address.")

    # Generate 6-digit cryptographic OTP
    otp_code = f"{secrets.randbelow(900000) + 100000}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=config.OTP_EXPIRY_MINUTES)

    # Invalidate previous unused OTPs for this booking
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

    # Deliver via SMTP
    email_body = (
        f"Dear {booking.guest_name},\n\n"
        f"A request was made to link your booking ({booking.booking_ref}) to a browser session.\n\n"
        f"Your 6-Digit One-Time Verification Code is: {otp_code}\n\n"
        f"This code will expire in {config.OTP_EXPIRY_MINUTES} minutes.\n"
        f"If you did not request this, please disregard this email.\n\n"
        f"Pearl Continental Hotel Lahore Concierge Team"
    )
    send_smtp_email(
        to_email=clean_email,
        subject=f"PC Lahore Verification Code: {otp_code}",
        body_text=email_body
    )

    # Mask email for privacy display (e.g., t***@gmail.com)
    parts = clean_email.split("@")
    masked = parts[0][0] + "***@" + parts[1] if len(parts) == 2 else clean_email

    return {
        "success": True,
        "message": f"A 6-digit verification code has been sent to {masked}. Please enter the code to link your booking.",
        "booking_ref": booking.booking_ref
    }


@router.post("/claim/verify-otp")
def verify_claim_otp_endpoint(
    req: VerifyClaimOTPRequest,
    session_data: tuple[GuestSession, str] = Depends(get_current_session),
    db: Session = Depends(get_db)
):
    """
    Step 2 of Secure OTP Claim:
    Validates the 6-digit OTP from the email inbox and securely links
    the booking to the current guest browser session.
    """
    session, _ = session_data
    clean_ref = req.booking_ref.strip()
    clean_email = req.email.strip().lower()
    clean_otp = req.otp_code.strip()

    booking = (
        db.query(Booking)
        .filter((Booking.booking_ref == clean_ref) | (Booking.confirmation_code == clean_ref))
        .first()
    )
    if not booking or booking.guest_email.lower().strip() != clean_email:
        raise HTTPException(status_code=404, detail="Invalid booking reference or email.")

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
        raise HTTPException(status_code=400, detail="Invalid or expired verification code. Please request a new code.")

    # Mark OTP as used and re-link booking to session
    otp_record.is_used = True
    booking.guest_session_id = session.id
    db.commit()

    return {
        "success": True,
        "message": f"Identity verified! Booking {booking.booking_ref} is now securely linked to your session.",
        "booking_ref": booking.booking_ref,
        "status": compute_display_status(booking)
    }


@router.post("/claim")
def claim_booking(
    req: ClaimBookingRequest,
    session_data: tuple[GuestSession, str] = Depends(get_current_session),
    db: Session = Depends(get_db)
):
    """Fallback instant claim or redirects to OTP verification."""
    session, _ = session_data
    ident = req.confirmation_code.strip()
    booking = (
        db.query(Booking)
        .filter((Booking.confirmation_code == ident) | (Booking.booking_ref == ident))
        .first()
    )
    if not booking or booking.guest_email.lower().strip() != req.email.lower().strip():
        raise HTTPException(status_code=404, detail="Invalid booking reference/confirmation code or email mismatch.")

    booking.guest_session_id = session.id
    db.commit()
    return {
        "success": True, 
        "message": f"Booking {booking.booking_ref} linked successfully to this browser session.",
        "booking_ref": booking.booking_ref,
        "status": compute_display_status(booking)
    }
