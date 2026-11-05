#!handler/booking_handler.py
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from config import config
from models.db_models import UserAccount, Booking, BookingRoom, BookingService, Room, RoomType, Service
from handler.availability_handler import expire_stale_holds
from util.security_util import generate_booking_ref
from util.pricing_util import calculate_stay_pricing

def create_booking_hold_handler(
    db: Session,
    user_id: int,
    special_requests: Optional[str],
    check_in: date,
    check_out: date,
    guests: int,
    room_allocations: Dict[int, int],
    selected_services: List[Dict[str, Any]]
) -> Booking:
    """
    Creates an unpaid booking hold tied to the authenticated user.
    Pulls name, email, and phone dynamically from the UserAccount profile.
    """
    expire_stale_holds(db)

    # 1. Fetch user account to get contact/name details dynamically
    user = db.query(UserAccount).filter_by(id=user_id).first()
    if not user:
        raise ValueError("User account not found.")

    # 2. Capacity validation
    total_capacity = 0
    total_requested_rooms = 0
    room_data_for_pricing = []

    for rt_id, qty in room_allocations.items():
        if qty <= 0:
            continue
        rt = db.query(RoomType).filter_by(id=rt_id).first()
        if not rt:
            raise ValueError(f"Invalid room type ID: {rt_id}")
        total_capacity += rt.max_guests * qty
        total_requested_rooms += qty
        room_data_for_pricing.append({
            "room_type_id": rt.id,
            "name": rt.name,
            "base_price": rt.base_price,
            "quantity": qty
        })

    if total_requested_rooms == 0:
        raise ValueError("Please select at least 1 room.")

    if guests > total_capacity:
        raise ValueError(f"Guest count ({guests}) exceeds total capacity ({total_capacity}) for chosen rooms.")

    # 3. Service data for pricing
    service_data_for_pricing = []
    for s_item in selected_services:
        s_id = s_item.get("service_id")
        qty = s_item.get("quantity", 1)
        srv = db.query(Service).filter_by(id=s_id).first()
        if srv:
            service_data_for_pricing.append({
                "service_id": srv.id,
                "name": srv.name,
                "price": srv.price,
                "pricing_unit": srv.pricing_unit,
                "quantity": qty
            })

    # 4. Compute pricing
    pricing = calculate_stay_pricing(
        check_in=check_in,
        check_out=check_out,
        room_allocations=room_data_for_pricing,
        selected_services=service_data_for_pricing,
        guests=guests
    )

    now = datetime.now(timezone.utc)
    hold_expires_at = now + timedelta(hours=config.HOLD_EXPIRY_HOURS)
    ref = generate_booking_ref()

    # 5. Create Booking record using profile details from user_id
    booking = Booking(
        booking_ref=ref,
        user_id=user_id,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        status="PENDING",
        payment_status="UNPAID",
        hold_expires_at=hold_expires_at,
        total_amount=pricing["total_amount"]
    )
    db.add(booking)
    db.flush()

    # 6. SAVEPOINT physical room assignment loop
    for rt_id, qty in room_allocations.items():
        if qty <= 0:
            continue

        taken = 0
        candidate_rooms = (
            db.query(Room)
            .filter(Room.room_type_id == rt_id, Room.is_active == True)
            .order_by(Room.room_number)
            .all()
        )

        for candidate in candidate_rooms:
            try:
                with db.begin_nested():
                    rt = db.query(RoomType).filter_by(id=rt_id).first()
                    b_room = BookingRoom(
                        booking_id=booking.id,
                        room_id=candidate.id,
                        check_in=check_in,
                        check_out=check_out,
                        price_per_night=rt.base_price,
                        blocks_inventory=True
                    )
                    db.add(b_room)
                    db.flush()

                taken += 1
                if taken == qty:
                    break
            except Exception:
                continue

        if taken < qty:
            db.rollback()
            raise ValueError("Sorry, not enough available rooms for the selected category.")

    # 7. Add services
    for s_info in service_data_for_pricing:
        b_service = BookingService(
            booking_id=booking.id,
            service_id=s_info["service_id"],
            quantity=s_info["quantity"],
            unit_price=s_info["price"]
        )
        db.add(b_service)

    db.commit()
    db.refresh(booking)
    return booking

def cancel_unpaid_booking_handler(db: Session, booking_ref: str, user_id: int) -> dict:
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

def get_booking_services_handler(db: Session, booking_ref: str, user_id: int):
    """
    Backend handler to fetch services attached to a booking reference securely.
    """
    booking = db.query(Booking).filter_by(booking_ref=booking_ref, user_id=user_id).first()
    if not booking:
        raise ValueError(f"Booking {booking_ref} not found.")

    results = (
        db.query(BookingService, Service)
        .join(Service, BookingService.service_id == Service.id)
        .filter(BookingService.booking_id == booking.id)
        .all()
    )
    
    return [
        {
            "name": s.name,
            "quantity": bs.quantity,
            "unit_price": bs.unit_price,
            "subtotal": bs.quantity * bs.unit_price
        }
        for bs, s in results
    ]