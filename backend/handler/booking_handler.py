import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from config import config
from models.db_models import UserAccount, Booking, BookingRoom, BookingService, Room, RoomType, Service
from handler.availability_handler import expire_stale_holds
from util.security_util import generate_booking_ref
from types import SimpleNamespace
from util.pricing_util import calculate_stay_pricing, calculate_service_line_total

from models.db_models import HotelPolicy

# def create_booking_hold_handler(
#     db: Session,
#     user_id: int,
#     special_requests: Optional[str],
#     check_in: date,
#     check_out: date,
#     guests: int,
#     children: int,  # <--- Accept children parameter
#     room_allocations: Dict[int, int],
#     selected_services: List[Dict[str, Any]]
# ) -> Booking:
#     """
#     Creates an unpaid booking hold tied to the authenticated user.
#     Pulls name, email, and phone dynamically from the UserAccount profile.
#     """
#     expire_stale_holds(db)

#     # 1. Fetch user account to get contact/name details dynamically
#     user = db.query(UserAccount).filter_by(id=user_id).first()
#     if not user:
#         raise ValueError("User account not found.")

#     # 2. Capacity validation
#     total_capacity = 0
#     total_requested_rooms = 0
#     room_data_for_pricing = []

#     for rt_id, qty in room_allocations.items():
#         if qty <= 0:
#             continue
#         rt = db.query(RoomType).filter_by(id=rt_id).first()
#         if not rt:
#             raise ValueError(f"Invalid room type ID: {rt_id}")
#         total_capacity += rt.max_guests * qty
#         total_requested_rooms += qty
#         room_data_for_pricing.append({
#             "room_type_id": rt.id,
#             "name": rt.name,
#             "base_price": rt.base_price,
#             "quantity": qty
#         })

#     if total_requested_rooms == 0:
#         raise ValueError("Please select at least 1 room.")

#     if guests > total_capacity:
#         raise ValueError(f"Guest count ({guests}) exceeds total capacity ({total_capacity}) for chosen rooms.")

#     # 3. Service data for pricing
#     service_data_for_pricing = []
#     for s_item in selected_services:
#         s_id = s_item.get("service_id")
#         qty = s_item.get("quantity", 1)
#         srv = db.query(Service).filter_by(id=s_id).first()
#         if srv:
#             service_data_for_pricing.append({
#                 "service_id": srv.id,
#                 "name": srv.name,
#                 "price": srv.price,
#                 "pricing_unit": srv.pricing_unit,
#                 "quantity": qty
#             })

#     # 4. Compute pricing
#     pricing = calculate_stay_pricing(
#         check_in=check_in,
#         check_out=check_out,
#         room_allocations=room_data_for_pricing,
#         selected_services=service_data_for_pricing,
#         guests=guests
#     )

#     now = datetime.now(timezone.utc)
#     hold_expires_at = now + timedelta(hours=config.HOLD_EXPIRY_HOURS)
#     ref = generate_booking_ref()

#     # 5. Create Booking record using profile details from user_id
#     booking = Booking(
#         booking_ref=ref,
#         user_id=user_id,
#         check_in=check_in,
#         check_out=check_out,
#         guests=guests,
#         status="PENDING",
#         payment_status="UNPAID",
#         hold_expires_at=hold_expires_at,
#         total_amount=pricing["total_amount"]
#     )
#     db.add(booking)
#     db.flush()

#     # 6. SAVEPOINT physical room assignment loop
#     for rt_id, qty in room_allocations.items():
#         if qty <= 0:
#             continue

#         taken = 0
#         candidate_rooms = (
#             db.query(Room)
#             .filter(Room.room_type_id == rt_id, Room.is_active == True)
#             .order_by(Room.room_number)
#             .all()
#         )

#         for candidate in candidate_rooms:
#             try:
#                 with db.begin_nested():
#                     rt = db.query(RoomType).filter_by(id=rt_id).first()
#                     b_room = BookingRoom(
#                         booking_id=booking.id,
#                         room_id=candidate.id,
#                         check_in=check_in,
#                         check_out=check_out,
#                         price_per_night=rt.base_price,
#                         blocks_inventory=True
#                     )
#                     db.add(b_room)
#                     db.flush()

#                 taken += 1
#                 if taken == qty:
#                     break
#             except Exception:
#                 continue

#         if taken < qty:
#             db.rollback()
#             raise ValueError("Sorry, not enough available rooms for the selected category.")

#     # 7. Add services
#     for s_info in service_data_for_pricing:
#         b_service = BookingService(
#             booking_id=booking.id,
#             service_id=s_info["service_id"],
#             quantity=s_info["quantity"],
#             unit_price=s_info["price"]
#         )
#         db.add(b_service)

#     db.commit()
#     db.refresh(booking)
#     return booking


def _room_allocations(rooms, room_type_id, quantity) -> dict:
    """[{'room_type_id': 1, 'quantity': 2}, {'room_type_id': 3, 'quantity': 2}] -> {1: 2, 3: 2}
    Falls back to the old single room_type_id + quantity when 'rooms' is not given."""
    items = rooms or [{"room_type_id": room_type_id, "quantity": quantity}]
    alloc = {}
    for r in items:
        rid, qty = int(r["room_type_id"]), int(r.get("quantity", 1) or 0)
        if qty > 0:
            alloc[rid] = alloc.get(rid, 0) + qty
    return alloc
    
def create_booking_hold_handler(
    db: Session,
    user_id: int,
    special_requests: Optional[str],
    check_in: date,
    check_out: date,
    guests: int,
    children_details: List[Any],  # <--- Accept children details (ages)
    room_allocations: Dict[int, int],
    selected_services: List[Dict[str, Any]]
) -> Booking:
    """
    Creates an unpaid booking hold tied to the authenticated user with dynamic policy enforcement.
    """
    expire_stale_holds(db)
    
    # 1. Fetch user account
    user = db.query(UserAccount).filter_by(id=user_id).first()
    if not user:
        raise ValueError("User account not found.")

    # 2. Fetch live child policy dynamically from hotel_policy table
    policy_row = db.query(HotelPolicy).filter_by(key="child").first()
    child_policy = policy_row.data if policy_row else {"max_age": 12, "stay_free": True}

    # 3. Capacity validation & Room allocations
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

    # 4. Service data preparation & date validation bounds
    # service_data_for_pricing = []
    # for s_item in selected_services:
    #     s_id = s_item.get("service_id")
    #     qty = s_item.get("quantity", 1)
    #     srv = db.query(Service).filter_by(id=s_id).first()
    #     if srv:
    #         s_start = s_item.get("start_date") or check_in
    #         s_end = s_item.get("end_date") or check_out
    #         if s_start < check_in or s_end > check_out or s_end <= s_start:
    #             raise ValueError(f"Service dates for '{srv.name}' must be within check-in and check-out bounds.")
            
    #         service_data_for_pricing.append({
    #             "service_id": srv.id,
    #             "name": srv.name,
    #             "price": srv.price,
    #             "pricing_unit": srv.pricing_unit,
    #             "quantity": qty,
    #             "start_date": s_start,
    #             "end_date": s_end
    #         })

    # 4. Service data preparation & date validation bounds
    service_data_for_pricing = []
    for s_item in selected_services:
        # FIX: Use dot notation instead of .get() since s_item is a Pydantic object
        s_id = s_item.service_id
        qty = s_item.quantity if hasattr(s_item, 'quantity') else 1
        
        srv = db.query(Service).filter_by(id=s_id).first()
        if srv:
            s_start = getattr(s_item, 'start_date', None) or check_in
            s_end = getattr(s_item, 'end_date', None) or check_out
            if s_start < check_in or s_end > check_out or s_end <= s_start:
                raise ValueError(f"Service dates for '{srv.name}' must be within check-in and check-out bounds.")
            
            service_data_for_pricing.append({
                "service_id": srv.id,
                "name": srv.name,
                "price": srv.price,
                "pricing_unit": srv.pricing_unit,
                "quantity": qty,
                "start_date": s_start,
                "end_date": s_end
            })

    # 5. Compute pricing with dynamic child policy rules & billable adult checks
    pricing = calculate_stay_pricing(
        check_in=check_in,
        check_out=check_out,
        room_allocations=room_data_for_pricing,
        selected_services=service_data_for_pricing,
        guests=guests,
        child_policy=child_policy,
        children_details=children_details
    )

    if pricing["billable_adults"] > total_capacity:
        raise ValueError(f"Billable guest count ({pricing['billable_adults']}) exceeds total room capacity ({total_capacity}).")

    now = datetime.now(timezone.utc)
    hold_expires_at = now + timedelta(hours=config.HOLD_EXPIRY_HOURS)
    ref = generate_booking_ref()

    # 6. Create Booking record
    booking = Booking(
        booking_ref=ref,
        user_id=user_id,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        children=len(children_details or []),
        status="PENDING",
        payment_status="UNPAID",
        hold_expires_at=hold_expires_at,
        total_amount=pricing["total_amount"]
    )
    db.add(booking)
    db.flush()

    # 7. SAVEPOINT physical room assignment loop
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

    # 8. Add services with date ranges
    for s_info in service_data_for_pricing:
        b_service = BookingService(
            booking_id=booking.id,
            service_id=s_info["service_id"],
            quantity=s_info["quantity"],
            unit_price=s_info["price"],
            start_date=s_info["start_date"],
            end_date=s_info["end_date"]
        )
        db.add(b_service)

    db.commit()
    db.refresh(booking)


    # <--- ADD FORMATTED CHILDREN HERE IF NEEDED FOR LOGGING OR RETURNING --->
    formatted_children = [
        {
            "age": c.age,
            "description": "Infant" if c.age == 0 else f"{c.age} years"
        } 
        for c in children_details or []
    ]
    # (Optional: print or log it, or attach it if your response serializer handles it)

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



# def recompute_booking_total(booking) -> float:
#     """Rebuild total from scratch: rooms + every add-on, priced by pricing_util."""
#     rooms = sum(br.price_per_night * (br.check_out - br.check_in).days
#                 for br in booking.booking_rooms)
#     services = sum(
#         calculate_service_line_total(
#             unit_price=bs.unit_price, quantity=bs.quantity,
#             pricing_unit=bs.service.pricing_unit,
#             stay_check_in=booking.check_in, stay_check_out=booking.check_out,
#             guests=booking.guests, start_date=bs.start_date, end_date=bs.end_date,
#         )["line_total"]
#         for bs in booking.booking_services
#     )
#     return round(rooms + services, 2)