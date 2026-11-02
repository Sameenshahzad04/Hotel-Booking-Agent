from datetime import date, datetime, timezone
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from models.db_models import Booking, RoomType, Room, BookingRoom

def expire_stale_holds(db: Session) -> int:
    """
    Finds PENDING bookings past hold_expires_at and sets:
    status = 'EXPIRED' and blocks_inventory = FALSE.
    Frees rooms immediately without losing historical records.
    """
    now = datetime.now(timezone.utc)
    stale_bookings = (
        db.query(Booking)
        .filter(
            Booking.status == "PENDING",
            Booking.hold_expires_at < now
        )
        .all()
    )

    count = 0
    for b in stale_bookings:
        b.status = "EXPIRED"
        for br in b.booking_rooms:
            br.blocks_inventory = False
        count += 1

    if count > 0:
        db.commit()
    return count

def query_live_availability(
    db: Session,
    check_in: date,
    check_out: date,
    guests: int = 1
) -> List[Dict[str, Any]]:
    """
    Pure SQLAlchemy ORM availability query.
    Finds all active rooms per room type and subtracts overlapping active holds/bookings.
    """
    # 1. First, release any stale holds that passed the 2-hour mark
    expire_stale_holds(db)

    # 2. Subquery: Find room_ids that are occupied during the requested dates
    # Date overlap logic: (check_in < requested_check_out) AND (check_out > requested_check_in)
    occupied_rooms_subquery = (
        db.query(BookingRoom.room_id)
        .filter(
            BookingRoom.blocks_inventory.is_(True),
            BookingRoom.check_in < check_out,
            BookingRoom.check_out > check_in
        )
        .distinct()
        .subquery()
    )

    # 3. Pure ORM query: Join RoomType with active Rooms, outerjoin occupied rooms, and aggregate
    results = (
        db.query(
            RoomType,
            func.count(Room.id).label("total_rooms"),
            func.count(occupied_rooms_subquery.c.room_id).label("occupied_rooms")
        )
        .join(Room, (Room.room_type_id == RoomType.id) & (Room.is_active.is_(True)))
        .outerjoin(occupied_rooms_subquery, Room.id == occupied_rooms_subquery.c.room_id)
        .group_by(RoomType.id)
        .order_by(RoomType.base_price.asc())
        .all()
    )

    # 4. Assemble the result list with availability flags
    availability_list = []
    for rt, total_count, occupied_count in results:
        avail_count = max(0, total_count - occupied_count)
        availability_list.append({
            "room_type_id": rt.id,
            "name": rt.name,
            "description": rt.description,
            "base_price": float(rt.base_price),
            "max_guests": rt.max_guests,
            "bed_type": rt.bed_type,
            "amenities": rt.amenities or [],
            "available_rooms": avail_count,
            "is_available": avail_count > 0 and rt.max_guests >= min(guests, rt.max_guests)
        })

    return availability_list
