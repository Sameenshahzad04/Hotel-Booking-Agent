#!handler/payment_handler.py
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models.db_models import Booking, Transaction, Notification, UserAccount
from util.security_util import generate_confirmation_code

def process_payment_handler(
    db: Session,
    booking_ref: str,
    user_id: int,
    idempotency_key: str
) -> dict:
    """
    Handles payment transaction for the authenticated user, generates HB-XXXXXX code, 
    and enqueues confirmation email.
    """
    now = datetime.now(timezone.utc)

    # 1. Idempotency Check
    existing_tx = db.query(Transaction).filter_by(idempotency_key=idempotency_key).first()
    if existing_tx:
        booking = existing_tx.booking
        return {
            "success": True,
            "message": "Payment already processed (idempotent replay)",
            "booking_ref": booking.booking_ref,
            "confirmation_code": booking.confirmation_code,
            "amount": existing_tx.amount,
            "paid_at": booking.paid_at
        }

    # 2. Lock row
    booking = (
        db.query(Booking)
        .filter_by(booking_ref=booking_ref)
        .with_for_update()
        .first()
    )

    if not booking:
        raise ValueError("Booking reference not found.")

    # Validate ownership against authenticated user_id
    if booking.user_id != user_id:
        raise PermissionError("Access denied: You do not own this booking.")

    if booking.status != "PENDING":
        raise ValueError(f"Cannot pay: Booking status is {booking.status}.")

    hold_expires = booking.hold_expires_at
    if hold_expires and hold_expires.tzinfo is None:
        hold_expires = hold_expires.replace(tzinfo=timezone.utc)

    if hold_expires <= now:
        booking.status = "EXPIRED"
        for br in booking.booking_rooms:
            br.blocks_inventory = False
        db.commit()
        raise ValueError("Hold has expired. Please book again.")

    # Fetch user account for dynamic name and email details
    user_account = db.query(UserAccount).filter_by(id=user_id).first()
    guest_name = user_account.full_name if user_account else "Valued Guest"
    guest_email = user_account.email if user_account else ""

    # 3. Confirm booking
    confirmation_code = generate_confirmation_code()
    booking.confirmation_code = confirmation_code
    booking.status = "CONFIRMED"
    booking.payment_status = "PAID"
    booking.paid_at = now

    # 4. Insert Transaction (linked to user_id instead of guest_session_id)
    tx = Transaction(
        user_id=user_id,
        booking_id=booking.id,
        type="PAYMENT",
        status="SUCCEEDED",
        amount=booking.total_amount,
        idempotency_key=idempotency_key
    )
    db.add(tx)

    # 5. Insert Notification (Transactional Outbox)
    room_names = ", ".join(br.room.room_type.name for br in booking.booking_rooms)
    nights = (booking.check_out - booking.check_in).days
    email_body = (
        f"Dear {guest_name},\n\n"
        f"Your reservation at Pearl Continental Hotel Lahore is CONFIRMED!\n\n"
        f"Confirmation Code: {confirmation_code}\n"
        f"Booking Reference: {booking.booking_ref}\n"
        f"Accommodations: {room_names}\n"
        f"Check-In: {booking.check_in} (From 14:00)\n"
        f"Check-Out: {booking.check_out} (Until 12:00)\n"
        f"Nights: {nights} | Guests: {booking.guests}\n"
        f"Total Paid: PKR {booking.total_amount:,.2f}\n\n"
        f"Warm regards,\nPearl Continental Hotel Lahore Team"
    )

    notification = Notification(
        booking_id=booking.id,
        kind="CONFIRMED",
        to_email=guest_email,
        subject=f"PC Lahore Booking Confirmed: {confirmation_code}",
        body=email_body
    )
    db.add(notification)

    db.commit()
    db.refresh(booking)

    # 6. Send live confirmation email via SMTP
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
        "message": "Payment successful and booking confirmed!",
        "booking_ref": booking.booking_ref,
        "confirmation_code": confirmation_code,
        "amount": booking.total_amount,
        "paid_at": booking.paid_at
    }
