from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models.db_models import Booking, Transaction, Notification

def cancel_unpaid_booking_handler(db: Session, booking_ref: str, guest_session_id: int) -> dict:
    """Cancels unpaid pending booking and immediately frees inventory."""
    booking = (
        db.query(Booking)
        .filter_by(booking_ref=booking_ref)
        .with_for_update()
        .first()
    )
    if not booking:
        raise ValueError("Booking reference not found.")

    if booking.guest_session_id != guest_session_id:
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

def process_refund_handler(
    db: Session,
    booking_ref: str,
    guest_session_id: int,
    idempotency_key: str
) -> dict:
    """Processes refund based on cancellation window policy."""
    now = datetime.now(timezone.utc)
    today = now.date()

    booking = (
        db.query(Booking)
        .filter_by(booking_ref=booking_ref)
        .with_for_update()
        .first()
    )
    if not booking:
        raise ValueError("Booking reference not found.")

    if booking.guest_session_id != guest_session_id:
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

    parent_tx = (
        db.query(Transaction)
        .filter_by(booking_id=booking.id, type="PAYMENT", status="SUCCEEDED")
        .first()
    )

    if percent > 0:
        refund_tx = Transaction(
            guest_session_id=guest_session_id,
            booking_id=booking.id,
            type="REFUND",
            status="SUCCEEDED",
            amount=refund_amount,
            parent_transaction_id=parent_tx.id if parent_tx else None,
            idempotency_key=idempotency_key
        )
        db.add(refund_tx)
        booking.payment_status = "REFUNDED"

    booking.status = "CANCELLED"
    for br in booking.booking_rooms:
        br.blocks_inventory = False

    notification = Notification(
        booking_id=booking.id,
        kind="REFUNDED" if percent > 0 else "CANCELLED",
        to_email=booking.guest_email,
        subject=f"PC Lahore Booking Update: {booking.booking_ref}",
        body=(
            f"Dear {booking.guest_name},\n\n"
            f"Your reservation {booking.booking_ref} has been cancelled.\n"
            f"Refund Rate: {percent}%\n"
            f"Refund Amount: PKR {refund_amount:,.2f}\n"
            f"Reason: {reason}\n\n"
            f"Pearl Continental Hotel Lahore Guest Relations."
        )
    )
    db.add(notification)

    db.commit()

    return {
        "success": True,
        "booking_ref": booking.booking_ref,
        "eligible": percent > 0,
        "percent": percent,
        "refund_amount": refund_amount,
        "reason": reason,
        "status": booking.status,
        "payment_status": booking.payment_status
    }
