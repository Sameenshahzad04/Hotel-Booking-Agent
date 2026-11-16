#!router/booking_router.py
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from models.connection import get_db
from models.db_models import UserAccount, Booking
from router.auth_router import get_current_user
from handler.booking_handler import create_booking_hold_handler, cancel_unpaid_booking_handler
from util.pricing_util import calculate_service_line_total

from handler.payment_handler import process_payment_handler
from handler.refund_handler import get_refund_quote_handler, execute_refund_and_cancel_handler
from util.status_util import compute_display_status
from schema.booking_schema import BookingHoldRequest
from datetime import date

router = APIRouter(prefix="/bookings", tags=["Bookings"])

def _service_row(bs, booking):
    c = service_line(bs, booking)
    return {
        "service_id": bs.service_id,
        "name": bs.service.name,
        "quantity": c["quantity"],
        "unit_price": bs.unit_price,
        "pricing_unit": c["pricing_unit"],
        "multiplier": c["multiplier"],          # nights, guests, or both
        "line_total": c["line_total"],
        "start_date": str(c["start_date"]),
        "end_date": str(c["end_date"]),
    }

def validate_not_past(v: date) -> date:
    if v < date.today():
        raise HTTPException(status_code=422, detail="Date cannot be in the past.")
    return v

@router.post("")
def create_booking_hold_endpoint(
    req: BookingHoldRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Creates a 2-hour unpaid booking hold for the authenticated user."""
    req.check_in = validate_not_past(req.check_in)
    req.check_out = validate_not_past(req.check_out)
    
    try:
        # booking = create_booking_hold_handler(
        #     db=db,
        #     user_id=current_user.id,
        #     special_requests=getattr(req, "special_requests", None),
        #     check_in=req.check_in,
        #     check_out=req.check_out,
        #     guests=req.guests,
        #     room_allocations=req.rooms,
        #     selected_services=req.services or [],
        #     children=getattr(req, "children", 0),
        #     infants=getattr(req, "infants", 0)
        # )
        booking = create_booking_hold_handler(
            db=db,
            user_id=current_user.id,
            special_requests=getattr(req, "special_requests", None),
            check_in=req.check_in,
            check_out=req.check_out,
            guests=req.guests,
            children_details=req.children_details,  # <--- Pass children_details here
            room_allocations=req.rooms,
            selected_services=req.services or []
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
def list_user_bookings(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lists history of bookings for the authenticated user."""
    bookings = (
        db.query(Booking)
        .filter_by(user_id=current_user.id)
        .order_by(Booking.created_at.desc())
        .all()
    )

    items = []
    for b in bookings:
        status_info = compute_display_status(b)
        
        nights = (b.check_out - b.check_in).days

# Format rooms with breakdown details
        room_details = [
            {
                "name": br.room.room_type.name,
                "price_per_night": br.price_per_night,
                "nights": nights,
                "subtotal": br.price_per_night * nights
            }
            for br in b.booking_rooms
        ]

        # Format services with quantities and prices
        service_details = [
            {
                "name": bs.service.name,
                "quantity": bs.quantity,
                "unit_price": bs.unit_price,
                "pricing_unit": bs.service.pricing_unit,
                "line_total": bs.quantity * bs.unit_price
            }
            for bs in b.booking_services
        ]
        items.append({
            "booking_ref": b.booking_ref,
            "confirmation_code": b.confirmation_code if b.payment_status == "PAID" else None,
            "guest_name": current_user.full_name,
            "check_in": b.check_in,
            "check_out": b.check_out,
            "nights": nights,
            "guests": b.guests,
            "children": getattr(b, "children", 0),
            "rooms":room_details,
            "services": service_details,
            "total_amount": b.total_amount,
            "status": status_info
        })

    return {"bookings": items}

@router.get("/{ref}")
def get_single_booking(
    ref: str,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Returns single booking details for checkout ensuring ownership."""
    booking = db.query(Booking).filter_by(booking_ref=ref).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")

    if booking.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this booking.")

    status_info = compute_display_status(booking)
    return {
        "booking_ref": booking.booking_ref,
        "confirmation_code": booking.confirmation_code,
        "guest_name": current_user.full_name,
        "guest_email": current_user.email,
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
                "service_id": bs.service_id,
                "name": bs.service.name,
                "quantity": bs.quantity,
                "unit_price": bs.unit_price,
               "pricing_unit": getattr(bs, "pricing_unit", None) or bs.service.pricing_unit, # <--- Fix here
                "multiplier": getattr(bs, "multiplier", 1.0),
                "line_total": bs.line_total if (getattr(bs, "line_total", 0) and bs.line_total > 0) else round(bs.quantity * bs.unit_price, 2),
                "start_date": str(bs.start_date) if bs.start_date else str(booking.check_in),
                "end_date": str(bs.end_date) if bs.end_date else str(booking.check_out)
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
    ref: str,
    idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Processes payment for an unexpired hold."""
    key = idempotency_key or f"tx-{uuid.uuid4().hex}"

    try:
        return process_payment_handler(
            db=db,
            booking_ref=ref,
            user_id=current_user.id,
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
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancels unpaid pending booking."""
    try:
        return cancel_unpaid_booking_handler(db=db, booking_ref=ref, user_id=current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
@router.get("/{ref}/refund-quote")
def get_refund_quote(
    ref: str,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Step 1: Preview refund eligibility and amounts without needing confirmation code."""
    try:
        return get_refund_quote_handler(db, ref, current_user.id)
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{ref}/refund-and-cancel")
def cancel_and_refund_booking(
    ref: str,
    confirmation_code: str = Query(..., description="Payment confirmation code received after payment"),
    idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Step 2: Execute cancellation and issue refund requiring confirmation code."""
    key = idempotency_key or f"ref-{uuid.uuid4().hex}"

    try:
        return execute_refund_and_cancel_handler(db, ref, current_user.id, confirmation_code, key)
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))