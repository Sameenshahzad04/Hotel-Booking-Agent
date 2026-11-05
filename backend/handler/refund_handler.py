#!handler/refund_handler.py
from datetime import datetime, timezone
from typing import Dict, Any
import logging
from sqlalchemy.orm import Session
from models.db_models import Booking, Transaction, Notification, UserAccount

logger = logging.getLogger("pc_agent.refund")

def cancel_unpaid_booking_handler(db: Session, booking_ref: str, user_id: int) -> Dict[str, Any]:
    """Cancels unpaid pending booking and immediately frees inventory."""
    booking = (
        db.query(Booking)
        .filter_by(booking_ref=booking_ref)
        .with_for_update()
        .first()
    )
    if not booking:
        raise ValueError("Booking reference not found.")

    if booking.user_id != user_id:
        raise PermissionError("Access denied: You do not own this booking.")

    if booking.status != "PENDING" or booking.payment_status != "UNPAID":
        raise ValueError(f"Cannot cancel: Booking status is {booking.status}.")

    booking.status = "CANCELLED"
    for br in booking.booking_rooms:
        br.blocks_inventory = False

    db.commit()
    return {
        "success": True,
        "message": "Hold cancelled and rooms released successfully.",
        "booking_ref": booking.booking_ref,
        "status": "CANCELLED"
    }

def get_refund_quote_handler(db: Session, booking_ref: str, user_id: int) -> Dict[str, Any]:
    """Read-only preview handler. Calculates refund percentage and amount without requiring a confirmation code."""
    now = datetime.now(timezone.utc)
    today = now.date()

    booking = db.query(Booking).filter_by(booking_ref=booking_ref).first()
    if not booking:
        raise ValueError("Booking reference not found.")

    if booking.user_id != user_id:
        raise PermissionError("Access denied: You do not own this booking.")

    if booking.status != "CONFIRMED" or booking.payment_status != "PAID":
        raise ValueError("Only confirmed and paid bookings are eligible for refund review.")

    if today >= booking.check_in:
        raise ValueError("Refund refused: Stay has already started or completed.")

    days_until_checkin = (booking.check_in - today).days

    if days_until_checkin >= 7:
        percent = 100
        reason = "Standard cancellation (7+ days prior to check-in)"
    elif 2 <= days_until_checkin < 7:
        percent = 50
        reason = "Partial cancellation window (2-7 days prior to check-in)"
    else:
        percent = 0
        reason = "Late cancellation (< 48 hours prior to check-in: non-refundable per policy)"

    refund_amount = round(booking.total_amount * (percent / 100.0), 2)

    return {
        "booking_ref": booking.booking_ref,
        "eligible": percent > 0,
        "percent": percent,
        "refund_amount": refund_amount,
        "reason": reason,
        "total_amount": booking.total_amount
    }

def execute_refund_and_cancel_handler(
    db: Session,
    booking_ref: str,
    user_id: int,
    confirmation_code: str,
    idempotency_key: str
) -> Dict[str, Any]:
    """Execution handler. Validates confirmation code, cancels booking, and processes refund."""
    booking = db.query(Booking).filter_by(booking_ref=booking_ref).first()
    if not booking:
        raise ValueError("Booking reference not found.")

    if booking.user_id != user_id:
        raise PermissionError("Access denied: You do not own this booking.")

    # Strictly validate confirmation code before proceeding with execution
    if not booking.confirmation_code or booking.confirmation_code != confirmation_code:
        raise ValueError("Invalid confirmation code provided. Cannot execute refund.")

    # Fetch quote info
    quote = get_refund_quote_handler(db, booking_ref, user_id)
    
    if not quote["eligible"]:
        raise ValueError(f"Cancellation refused: {quote['reason']}")

    # Lock row for transaction update
    booking = (
        db.query(Booking)
        .filter_by(booking_ref=booking_ref)
        .with_for_update()
        .first()
    )

    parent_tx = (
        db.query(Transaction)
        .filter_by(booking_id=booking.id, type="PAYMENT", status="SUCCEEDED")
        .first()
    )

    refund_tx = Transaction(
        user_id=user_id,
        booking_id=booking.id,
        type="REFUND",
        status="SUCCEEDED",
        amount=quote["refund_amount"],
        parent_transaction_id=parent_tx.id if parent_tx else None,
        idempotency_key=idempotency_key
    )
    db.add(refund_tx)

    booking.payment_status = "REFUNDED"
    booking.status = "CANCELLED"
    for br in booking.booking_rooms:
        br.blocks_inventory = False

    user_account = db.query(UserAccount).filter_by(id=user_id).first()
    guest_name = user_account.full_name if user_account else "Valued Guest"
    guest_email = user_account.email if user_account else ""

    notification = Notification(
        booking_id=booking.id,
        kind="REFUNDED",
        to_email=guest_email,
        subject=f"PC Lahore Booking Cancelled & Refunded: {booking.booking_ref}",
        body=(
            f"Dear {guest_name},\n\n"
            f"Your reservation {booking.booking_ref} has been successfully cancelled.\n"
            f"Refund Rate: {quote['percent']}%\n"
            f"Refund Amount: PKR {quote['refund_amount']:,.2f}\n"
            f"Reason: {quote['reason']}\n\n"
            f"Pearl Continental Hotel Lahore Guest Relations."
        )
    )
    db.add(notification)
    db.commit()

    try:
        from util.email_service import send_smtp_email
        send_smtp_email(
            to_email=guest_email,
            subject=notification.subject,
            body_text=notification.body
        )
        notification.sent_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as email_err:
        notification.last_error = str(email_err)
        notification.attempts += 1
        db.commit()

    return {
        "success": True,
        "booking_ref": booking.booking_ref,
        "eligible": True,
        "percent": quote["percent"],
        "refund_amount": quote["refund_amount"],
        "reason": quote["reason"],
        "status": booking.status,
        "payment_status": booking.payment_status
    }

