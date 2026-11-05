#!util/status_util.py
from datetime import datetime, timezone

def compute_display_status(booking, now: datetime | None = None) -> dict:
    """
    Pure utility function computing display status, badge color, and countdown.
    Used uniformly across API, UI, and Chatbot.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    hold_expires = booking.hold_expires_at
    if hold_expires and hold_expires.tzinfo is None:
        hold_expires = hold_expires.replace(tzinfo=timezone.utc)

    # 1. PENDING status checks
    if booking.status == "PENDING":
        if hold_expires and hold_expires > now:
            remaining_seconds = int((hold_expires - now).total_seconds())
            hours, remainder = divmod(remaining_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            countdown_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            return {
                "display_status": "Pending",
                "badge_class": "badge-pending",
                "countdown": countdown_str,
                "seconds_left": remaining_seconds,
                "is_expired": False,
                "can_pay": True,
                "can_cancel": True,
                "can_refund": False
            }
        else:
            return {
                "display_status": "Expired",
                "badge_class": "badge-expired",
                "countdown": "00:00:00",
                "seconds_left": 0,
                "is_expired": True,
                "can_pay": False,
                "can_cancel": False,
                "can_refund": False
            }

    # 2. EXPIRED status
    if booking.status == "EXPIRED":
        return {
            "display_status": "Expired",
            "badge_class": "badge-expired",
            "countdown": None,
            "seconds_left": 0,
            "is_expired": True,
            "can_pay": False,
            "can_cancel": False,
            "can_refund": False
        }

    # 3. CONFIRMED status
    if booking.status == "CONFIRMED":
        today_date = now.date()
        if today_date >= booking.check_in:
            return {
                "display_status": "Active Stay",
                "badge_class": "badge-confirmed",
                "countdown": None,
                "seconds_left": 0,
                "is_expired": False,
                "can_pay": False,
                "can_cancel": False,
                "can_refund": False
            }
        return {
            "display_status": "Confirmed & Paid",
            "badge_class": "badge-confirmed",
            "countdown": None,
            "seconds_left": 0,
            "is_expired": False,
            "can_pay": False,
            "can_cancel": False,
            "can_refund": True
        }

    # 4. CANCELLED / REFUNDED
    if booking.status == "CANCELLED":
        if booking.payment_status == "REFUNDED":
            return {
                "display_status": "Refunded",
                "badge_class": "badge-refunded",
                "countdown": None,
                "seconds_left": 0,
                "is_expired": False,
                "can_pay": False,
                "can_cancel": False,
                "can_refund": False
            }
        return {
            "display_status": "Cancelled",
            "badge_class": "badge-cancelled",
            "countdown": None,
            "seconds_left": 0,
            "is_expired": False,
            "can_pay": False,
            "can_cancel": False,
            "can_refund": False
        }

    # 5. COMPLETED
    if booking.status == "COMPLETED":
        return {
            "display_status": "Completed",
            "badge_class": "badge-completed",
            "countdown": None,
            "seconds_left": 0,
            "is_expired": False,
            "can_pay": False,
            "can_cancel": False,
            "can_refund": False
        }

    return {
        "display_status": booking.status,
        "badge_class": "badge-neutral",
        "countdown": None,
        "seconds_left": 0,
        "is_expired": False,
        "can_pay": False,
        "can_cancel": False,
        "can_refund": False
    }