#!chatbot/tools/guest_service_tools.py
"""
Guest Service Tools for Pearl Continental (PC) Hotel Concierge Agent.

All tools here use LangChain's `@tool` decorator so that LLMs can inspect
their schemas, parameter types, and docstrings for native tool calling.
"""

import json 

from datetime import date
from typing import Optional, List
from contextlib import contextmanager
import sys
import logging
from pathlib import Path
from langchain_core.tools import tool

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from handler.booking_handler import (
    create_booking_hold_handler,
    cancel_unpaid_booking_handler,
    get_booking_services_handler
)
from handler.policy_handler import get_all_policies
from handler.availability_handler import query_live_availability
from handler.refund_handler import get_refund_quote_handler
from models.connection import get_db
from models.db_models import Booking, Service, BookingService, UserAccount,RoomType,HotelPolicy
from util.status_util import compute_display_status
from util.pricing_util import calculate_stay_pricing # (or import from util.pricing_util)


from pydantic import ValidationError

from schema.booking_schema import ChildInfo, ServiceItem 



logger = logging.getLogger("pc_agent.tools")
if not logger.handlers:
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
    Search PC Lahore policies, SOPs, and knowledge base.
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
    Returns live available rooms per room type for requested dates.
    Args:
        check_in: Check-in date in YYYY-MM-DD format (e.g. '2026-11-05')
        check_out: Check-out date in YYYY-MM-DD format (e.g. '2026-11-07')
        guests: Number of guests (default 1)
    """
    try:
        d_in = date.fromisoformat(check_in)
        d_out = date.fromisoformat(check_out)
    except ValueError:
        return "Error: Dates must be in YYYY-MM-DD format."

    if d_out <= d_in:
        return "Error: Check-out date must be strictly after check-in date."

    with _get_db_context() as db:
        availability = query_live_availability(db, check_in=d_in, check_out=d_out, guests=guests)
        if not availability:
            return f"No rooms available between {check_in} and {check_out} for {guests} guest(s)."

        results = [
            f"Available options from {check_in} to {check_out}:",
            "*(Tip: We also offer fantastic add-on services like Breakfast Buffets, Airport Transfers, and Spa access that can be added to your booking either now or later while your hold is pending!)*"
        ]
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
def search_services_tool() -> str:
    """
    Lists all available hotel add-on services (breakfast, transport, etc.).
    """
    with _get_db_context() as db:
        services = db.query(Service).all()
        if not services:
            return "No additional services currently available."

        output = ["Available Add-On Services:"]
        for s in services:
            output.append(
                f"- Service ID: {s.id} | Name: {s.name} | Price: PKR {s.price:,.2f} "
                f"({s.pricing_unit.replace('_', ' ')}) | Description: {s.description or 'N/A'}"
            )
        return "\n".join(output)


@tool
def get_booking_services_tool(booking_ref: str, user_id: int = 0) -> str:
    """
    Retrieve all add-on services attached to a specific booking reference for the authenticated user.
    Args:
        booking_ref: The booking reference code (e.g. 'HB-...')
        user_id: Authenticated user ID (automatically assigned)
    """
    if not user_id or user_id == 0:
        return "Authentication required. Please log in to view booking services."

    with _get_db_context() as db:
        # Verify user account exists and owns the booking
        booking = db.query(Booking).filter_by(booking_ref=booking_ref).first()
        if not booking:
            return f"Booking reference {booking_ref} not found."
        if booking.user_id != user_id:
            return "Access denied: This booking does not belong to your account."

        try:
            services = get_booking_services_handler(db, booking_ref=booking_ref, user_id=user_id)
            if not services:
                return f"No add-on services are currently attached to booking {booking_ref}."

            output = [f"Add-on services for booking {booking_ref}:"]
            for s in services:
                output.append(
                    f"- {s['name']} (Qty: {s['quantity']}) | Unit Price: PKR {s['unit_price']:,.2f} | "
                    f"Subtotal: PKR {s['subtotal']:,.2f}"
                )
            return "\n".join(output)
        except Exception as e:
            return f"Error retrieving services: {str(e)}"

# @tool
# def create_booking_hold_tool(
#     room_type_id: int,
#     check_in: str,
#     check_out: str,
#     guests: int,
#     special_requests: Optional[str] = None,
#     quantity: int = 1,
#     selected_services: Optional[List[int]] = None,
#     user_id: int = 0
# ) -> str:
#     """
#     Creates a 2-hour unpaid booking hold for the authenticated user with optional add-on services.
#     Args:
#         room_type_id: Numeric ID of the room type chosen by the guest
#         check_in: Check-in date in YYYY-MM-DD format
#         check_out: Check-out date in YYYY-MM-DD format
#         guests: Total number of guests
#         special_requests: Optional notes/requests from the guest
#         quantity: Number of rooms of this type to book (default 1)
#         selected_services: Optional list of numeric service IDs (e.g. [1, 2]) to include right away
#         user_id: Authenticated user ID (automatically assigned)
#     """
#     if not user_id or user_id == 0:
#         return "Error: Authentication required to create a booking hold."

#     try:
#         d_in = date.fromisoformat(check_in)
#         d_out = date.fromisoformat(check_out)
#     except ValueError:
#         return "Error: Dates must be in YYYY-MM-DD format."

#     with _get_db_context() as db:
#         try:
#             booking = create_booking_hold_handler(
#                 db=db,
#                 user_id=user_id,
#                 special_requests=special_requests,
#                 check_in=d_in,
#                 check_out=d_out,
#                 guests=guests,
#                 room_allocations={room_type_id: quantity},
#                 selected_services=selected_services or []
#             )
#             return (
#                 f"Booking hold successfully created with your room and selected add-ons!\n"
#                 f"Booking Reference: {booking.booking_ref}\n"
#                 f"Total Amount: PKR {booking.total_amount:,.2f}\n"
#                 f"Status: PENDING (UNPAID)\n"
#                 f"Hold expires at: {booking.hold_expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
#                 f"You can still add or modify add-on services anytime while this hold is active via our Guest Services or on your [My Bookings & Payments](http://127.0.0.1:8000/bookings.html) page."
#             )
#         except Exception as e:
#             logger.exception("TOOL create_booking_hold -> FAILED")
#             return f"Failed to create booking hold: {str(e)}"

from pydantic import ValidationError   
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




@tool
def calculate_stay_pricing_tool(
    check_in: str,
    check_out: str,
    room_type_id: int,
    quantity: int = 1,
    guests: int = 1,
    children_details: Optional[List[dict]] = None,
    selected_services: Optional[List[dict]] = None
) -> str:
    """
    Calculates the exact, authoritative stay pricing (rooms + add-on services) 
    using the core backend pricing utility. Use this before quoting prices to guests.
    Args:
        check_in: Check-in date in YYYY-MM-DD format
        check_out: Check-out date in YYYY-MM-DD format
        room_type_id: Numeric ID of the room type
        quantity: Number of rooms to book (default 1)
        guests: Number of adults
        children_details: Optional list of children info, e.g. [{'age': 5}]
        selected_services: Optional list of services, e.g. [{'service_id': 1, 'quantity': 1, 'start_date': '...', 'end_date': '...'}]
    """
    try:
        d_in = date.fromisoformat(str(check_in))
        d_out = date.fromisoformat(str(check_out))
    except ValueError:
        return "Error: Dates must be in YYYY-MM-DD format."

    with _get_db_context() as db:
        try:
            rt = db.query(RoomType).filter_by(id=room_type_id).first()
            if not rt:
                return f"Error: Room Type ID {room_type_id} not found."

            room_allocations = [{
                "room_type_id": rt.id,
                "name": rt.name,
                "base_price": float(rt.base_price),
                "quantity": quantity
            }]

            resolved_services = []
            if selected_services:
                for s_item in selected_services:
                    s_id = s_item.get("service_id")
                    srv = db.query(Service).filter_by(id=s_id).first()
                    if srv:
                        resolved_services.append({
                            "service_id": srv.id,
                            "name": srv.name,
                            "price": float(srv.price),
                            "pricing_unit": srv.pricing_unit,
                            "quantity": s_item.get("quantity", 1),
                            "start_date": s_item.get("start_date"),
                            "end_date": s_item.get("end_date")
                        })

            kids = [ChildInfo(**c) for c in (children_details or [])]
            
            # Fetch dynamic child policy
            policy_row = db.query(HotelPolicy).filter_by(key="child").first()
            child_policy = policy_row.data if policy_row else {"max_age": 12, "stay_free": True}

            pricing_result = calculate_stay_pricing(
                check_in=d_in,
                check_out=d_out,
                room_allocations=room_allocations,
                selected_services=resolved_services,
                guests=guests,
                child_policy=child_policy,
                children_details=kids
            )

            output = [
                f"Official Pricing Breakdown ({pricing_result['nights']} nights, {guests} adults, {len(kids)} children):",
                f"- Total Rooms Cost: PKR {pricing_result['total_rooms_cost']:,.2f}",
                f"- Total Services Cost: PKR {pricing_result['total_services_cost']:,.2f}",
                f"- Total Amount: PKR {pricing_result['total_amount']:,.2f}"
            ]
            return "\n".join(output)
        except Exception as e:
            logger.exception("TOOL calculate_stay_pricing -> FAILED")
            return f"Failed to calculate pricing: {str(e)}"


@tool
def create_booking_hold_tool(
    check_in: str,
    check_out: str,
    guests: int,
    room_type_id: int,
    quantity: int = 1,
    children_details: Optional[List[dict]] = None,
    special_requests: Optional[str] = None,
    selected_services: Optional[List[dict]] = None,
    user_id: int = 0
) -> str:
    """
    Creates a 2-hour unpaid booking hold for the authenticated user with optional add-on services.
    Args:
        room_type_id: Numeric ID of the room type chosen by the guest
        check_in: Check-in date in YYYY-MM-DD format
        check_out: Check-out date in YYYY-MM-DD format
        guests: Number of ADULTS only. Never include children in this number.
        children_details: One dict per child with the child's age, e.g. [{'age': 5}, {'age': 14}].
                          Always ask the guest for every child's age.
        special_requests: Optional notes/requests from the guest
        quantity: Number of rooms of this type to book (default 1)
        selected_services: Optional list of dicts, e.g.
                           [{'service_id': 3, 'quantity': 1, 'start_date': '2026-11-20', 'end_date': '2026-11-22'}].
                           Dates are optional and default to the whole stay. They must be inside check-in and check-out.
        user_id: Authenticated user ID (automatically assigned)
    """
    if not user_id or user_id == 0:
        return "Error: Authentication required to create a booking hold."

    try:
        d_in = date.fromisoformat(check_in)
        d_out = date.fromisoformat(check_out)
    except ValueError:
        return "Error: Dates must be in YYYY-MM-DD format."
    
    # room_allocations = _room_allocations(rooms, room_type_id, quantity)
    # if not room_allocations or 0 in room_allocations:
    #     return "Error: Please choose at least one room type and quantity."

    
    with _get_db_context() as db:
        try:
            kids = [ChildInfo(**c) for c in (children_details or [])]
            services = [ServiceItem(**s) for s in (selected_services or [])]
        except ValidationError as e:
            first = e.errors()[0]
            return (f"Invalid details: {first['loc'][-1]}: {first['msg']}. "
                    f"Children must be aged 0-17 (anyone older counts as an adult), "
                    f"and service dates must be YYYY-MM-DD.")

        try:
            booking = create_booking_hold_handler(
                db=db,
                user_id=user_id,
                special_requests=special_requests,
                check_in=d_in,
                check_out=d_out,
                guests=guests,
                children_details=kids,
                room_allocations={room_type_id: quantity},
                selected_services=services,
            )
            return (
                f"Booking hold successfully created!\n"
                f"Booking Reference: {booking.booking_ref}\n"
                f"Total Amount: PKR {booking.total_amount:,.2f}\n"
                f"Status: PENDING (UNPAID)\n"
                f"Hold expires at: {booking.hold_expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                f"You can add or modify add-on services anytime while this hold is active, and complete your payment on your [My Bookings & Payments](http://127.0.0.1:8000/payment.html?ref={booking.booking_ref}) page."
            )
        except Exception as e:
            logger.exception("TOOL create_booking_hold -> FAILED")
            return f"Failed to create booking hold: {str(e)}"



@tool
def update_booking_services_tool(
    booking_ref: str, 
    services: List[dict], 
    user_id: int = 0
) -> str:
    """
    Synchronizes add-on services for a pending booking. Adds new services, 
    updates quantities, or removes unchecked/omitted services entirely, and recalculates the total bill.
    Args:
        booking_ref: The booking reference (e.g., 'BK-...')
        services: List of dicts with service_id and quantity (e.g., [{'service_id': 1, 'quantity': 2}])
        user_id: Authenticated user ID (automatically assigned)
    """
    if not user_id or user_id == 0:
        return "Authentication required to modify booking services."

    with _get_db_context() as db:
        booking = db.query(Booking).filter_by(booking_ref=booking_ref).first()
        if not booking:
            return f"Booking reference {booking_ref} not found."
        if booking.user_id != user_id:
            return "Access denied: You are not authorized to modify this booking."

        if booking.status != "PENDING" or booking.payment_status != "UNPAID":
            return f"Cannot modify services: Booking {booking_ref} is no longer pending/unpaid."

        # Aggregate requested quantities (quantity <= 0 or omitted means removal)
        requested_map = {}
        for item in services:
            s_id = item.get("service_id")
            qty = item.get("quantity", 0)
            if qty > 0:
                requested_map[s_id] = requested_map.get(s_id, 0) + qty

        # Fetch currently attached services for this booking
        existing_services = db.query(BookingService).filter_by(booking_id=booking.id).all()
        existing_map = {bs.service_id: bs for bs in existing_services}

        price_adjustment = 0.0

        # 1. Handle updates and removals of existing attached services
        for s_id, bs in existing_map.items():
            if s_id in requested_map:
                new_qty = requested_map[s_id]
                if bs.quantity != new_qty:
                    old_cost = bs.quantity * bs.unit_price
                    new_cost = new_qty * bs.unit_price
                    price_adjustment += (new_cost - old_cost)
                    bs.quantity = new_qty
            else:
                # Service was unchecked/removed by user/chatbot
                price_adjustment -= (bs.quantity * bs.unit_price)
                db.delete(bs)

        # 2. Handle newly added services
        for s_id, qty in requested_map.items():
            if s_id not in existing_map:
                service = db.query(Service).filter_by(id=s_id).first()
                if not service:
                    return f"Service ID {s_id} not found."
                
                add_cost = qty * service.price
                price_adjustment += add_cost
                
                new_bs = BookingService(
                    booking_id=booking.id,
                    service_id=service.id,
                    quantity=qty,
                    unit_price=service.price
                )
                db.add(new_bs)

        booking.total_amount = round(booking.total_amount + price_adjustment, 2)
        db.commit()
        db.refresh(booking)

        return f"Successfully synchronized services for booking {booking_ref}. New Total Amount: PKR {booking.total_amount:,.2f}"





@tool
def add_service_to_hold_tool(booking_ref: str, service_id: int, quantity: int = 1, user_id: int = 0) -> str:
    """
    Allows adding or updating services on an existing booking as long as the booking belongs to the user and is still unpaid (PENDING/UNPAID).
    Args:
        booking_ref: The booking reference (e.g., 'HB-...')
        service_id: ID of the add-on service
        quantity: Quantity of the service
        user_id: Authenticated user ID (automatically assigned)
    """
    if not user_id or user_id == 0:
        return "Authentication required to modify booking services."

    with _get_db_context() as db:
        booking = db.query(Booking).filter_by(booking_ref=booking_ref).first()
        if not booking:
            return f"Booking reference {booking_ref} not found."
        if booking.user_id != user_id:
            return "Access denied: You are not authorized to modify this booking."

        if booking.status != "PENDING" or booking.payment_status != "UNPAID":
            return f"Cannot add services: Booking {booking_ref} is no longer pending/unpaid."

        service = db.query(Service).filter_by(id=service_id).first()
        if not service:
            return f"Service ID {service_id} not found."

        booking_service = BookingService(
            booking_id=booking.id,
            service_id=service.id,
            quantity=quantity,
            unit_price=service.price
        )
        db.add(booking_service)
        
        subtotal = service.price * quantity
        if service.pricing_unit == "per_night":
            nights = (booking.check_out - booking.check_in).days
            subtotal *= nights
        elif service.pricing_unit == "per_guest":
            subtotal *= booking.guests

        booking.total_amount = round(booking.total_amount + subtotal, 2)
        db.commit()

        return f"Successfully added {quantity}x {service.name} to booking {booking_ref}. New Total: PKR {booking.total_amount:,.2f}"
@tool
def get_user_profile_tool(user_id: int = 0) -> str:
    """
    Retrieves the authenticated user's profile details (Name, Email, Phone, Age, Gender) 
    from their account for booking and personalization.
    Args:
        user_id: Authenticated user ID (automatically assigned)
    """
    if not user_id or user_id == 0:
        return "Authentication required to retrieve user profile."

    with _get_db_context() as db:
        user = db.query(UserAccount).filter_by(id=user_id).first()
        if not user:
            return f"User account ID {user_id} not found."

        return (
            f"User Profile Details:\n"
            f"- Full Name: {user.full_name}\n"
            f"- Email: {user.email}\n"
            f"- Phone: {user.phone or 'Not Provided'}\n"
            f"- Age: {user.age or 'Not Provided'}\n"
            f"- Gender: {user.gender or 'Not Provided'}"
        )

# @tool
# def create_booking_hold_tool(
#     room_type_id: int,
#     check_in: str,
#     check_out: str,
#     guests: int,
#     special_requests: Optional[str] = None,
#     quantity: int = 1,
#     user_id: int = 0
# ) -> str:
#     """
#     Creates a 2-hour unpaid booking hold for the authenticated user.
#     Args:
#         room_type_id: Numeric ID of the room type chosen by the guest
#         check_in: Check-in date in YYYY-MM-DD format
#         check_out: Check-out date in YYYY-MM-DD format
#         guests: Total number of guests
#         special_requests: Optional notes/requests from the guest
#         quantity: Number of rooms of this type to book (default 1)
#         user_id: Authenticated user ID (automatically assigned)
#     """
#     if not user_id or user_id == 0:
#         return "Error: Authentication required to create a booking hold."

#     try:
#         d_in = date.fromisoformat(check_in)
#         d_out = date.fromisoformat(check_out)
#     except ValueError:
#         return "Error: Dates must be in YYYY-MM-DD format."

#     with _get_db_context() as db:
#         try:
#             booking = create_booking_hold_handler(
#                 db=db,
#                 user_id=user_id,
#                 special_requests=special_requests,
#                 check_in=d_in,
#                 check_out=d_out,
#                 guests=guests,
#                 room_allocations={room_type_id: quantity},
#                 selected_services=[]
#             )
#             return (
#                 f"Booking hold successfully created and tied to your account!\n"
#                 f"Booking Reference: {booking.booking_ref}\n"
#                 f"Total Amount: PKR {booking.total_amount:,.2f}\n"
#                 f"Status: PENDING (UNPAID)\n"
#                 f"Hold expires at: {booking.hold_expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
#                 f"You can add extra add-on services anytime while this hold is active.\n"
#                 f"To complete payment, please use endpoint: POST /bookings/{booking.booking_ref}/pay (or contact Front Desk at +92-42-111-505-505)."
#             )
#         except Exception as e:
#             logger.exception("TOOL create_booking_hold -> FAILED")
#             return f"Failed to create booking hold: {str(e)}"


def mask_confirmation_code(code: Optional[str]) -> str:
    """Masks confirmation codes while leaving references fully visible."""
    if not code:
        return "Not Generated Yet"
    if len(code) <= 4:
        return "****"
    return code[:2] + "****" + code[-2:]


@tool
def list_guest_bookings_tool(user_id: int = 0) -> str:
    """
    Lists history of bookings for the authenticated user.
    Args:
        user_id: Authenticated user ID (automatically assigned)
    """
    if not user_id or user_id == 0:
        return "Please log in to view your bookings."

    with _get_db_context() as db:
        bookings = (
            db.query(Booking)
            .filter_by(user_id=user_id)
            .order_by(Booking.created_at.desc())
            .all()
        )
        if not bookings:
            return "You currently have no bookings on your account."

        output = [f"Found {len(bookings)} booking(s):"]
        for b in bookings:
            status_info = compute_display_status(b)
            masked_code = mask_confirmation_code(b.confirmation_code)
            output.append(
                f"- Reference: {b.booking_ref} | Confirmation Code: {masked_code} | "
                f"Status: {status_info.get('display_status', b.status)} | "
                f"Dates: {b.check_in} to {b.check_out} | Total: PKR {b.total_amount:,.2f}"
            )
        return "\n".join(output)


@tool
def cancel_booking_tool(booking_ref: str, user_id: int = 0) -> str:
    """
    Cancels unpaid pending booking.
    Args:
        booking_ref: The booking reference (e.g. 'HB-...')
        user_id: Authenticated user ID (automatically assigned)
    """
    if not user_id or user_id == 0:
        return "Authentication required to cancel a booking."

    with _get_db_context() as db:
        booking = db.query(Booking).filter_by(booking_ref=booking_ref).first()
        if not booking:
            return f"Booking reference {booking_ref} not found."
        if booking.user_id != user_id:
            return "Access denied: You do not own this booking."

        try:
            cancel_unpaid_booking_handler(
                db=db,
                booking_ref=booking_ref,
                user_id=user_id
            )
            return f"Booking {booking_ref} cancelled successfully. Rooms released."
        except Exception as e:
            return f"Cancellation failed: {str(e)}"


@tool
def get_payment_link_info_tool(booking_ref: str, user_id: int = 0) -> str:
    """
    Provides payment endpoint information and instructions for an unpaid booking hold.
    """
    if not user_id or user_id == 0:
        return "Authentication required."

    with _get_db_context() as db:
        booking = db.query(Booking).filter_by(booking_ref=booking_ref).first()
        if not booking:
            return f"Booking reference {booking_ref} not found."
        if booking.user_id != user_id:
            return "Access denied: This booking does not belong to your account."

        if booking.payment_status == "PAID":
            return f"Booking {booking_ref} is already paid and confirmed."

        return (
            f"Your booking hold ({booking.booking_ref}) is ready for payment (Total: PKR {booking.total_amount:,.2f}).\n"
            f"Please proceed to complete your payment securely via your [Secure Payment Page](http://127.0.0.1:8000/payment.html?ref={booking.booking_ref}) "
            f"or contact our Front Desk at +92-42-111-505-505 for further assistance."
        )


@tool
def get_refund_quote_tool(booking_ref: str, user_id: int = 0) -> str:
    """
    Step 1: Preview refund eligibility and amounts without needing confirmation code.
    Args:
        booking_ref: The booking reference code (e.g. 'HB-...')
        user_id: Authenticated user ID (automatically assigned)
    """
    if not user_id or user_id == 0:
        return "Authentication required to check refund quotes."

    with _get_db_context() as db:
        booking = db.query(Booking).filter_by(booking_ref=booking_ref).first()
        if not booking:
            return f"Booking reference {booking_ref} not found."
        if booking.user_id != user_id:
            return "Access denied: You do not own this booking."

        try:
            quote = get_refund_quote_handler(db, booking_ref, user_id)
            return (
                f"Refund Quote Preview for Booking {quote['booking_ref']}:\n"
                f"- Eligible for Refund: {'Yes' if quote['eligible'] else 'No'}\n"
                f"- Refund Percentage: {quote['percent']}%\n"
                f"- Refund Amount: PKR {quote['refund_amount']:,.2f} (Total Paid: PKR {quote['total_amount']:,.2f})\n"
                f"- Policy Context: {quote['reason']}\n"
                f"To proceed with cancellation and execute the refund, please visit your [Refund Portal](http://127.0.0.1:8000/refund.html?ref={quote['booking_ref']})."
            )
        except Exception as e:
            return f"Could not generate refund quote: {str(e)}"

@tool
def get_hotel_policy_tool(policy_key: str = "") -> str:
    """
    Returns the hotel's live policy rules as JSON.
    Args:
        policy_key: One of child, pet, check_in_out, cancellation, payment, smoking, id_requirements.
                    Leave empty to get all policies.
    """
    with _get_db_context() as db:
        policies = get_all_policies(db)          # {key: data} from the hotel_policy table

    if not policies:
        return "No hotel policies have been saved yet. Please contact the Front Desk."

    key = (policy_key or "").strip().lower()
    if key:
        if key in policies:
            return f"Policy [{key}]: {json.dumps(policies[key], indent=2)}"
        return (f"No policy named '{key}'. Available policies: {', '.join(policies)}.\n"
                f"{json.dumps(policies, indent=2)}")

    return json.dumps(policies, indent=2)


# @tool
# def calculate_stay_pricing_tool(
#     check_in: str,
#     check_out: str,
#     room_type_id: int,
#     quantity: int = 1,
#     guests: int = 1,
#     children_details: Optional[List[dict]] = None,
#     selected_services: Optional[List[dict]] = None
# ) -> str:
#     """
#     Calculates the exact, authoritative stay pricing (rooms + add-on services) 
#     using the backend pricing utility rules. Use this before quoting prices to guests.
#     Args:
#         check_in: Check-in date in YYYY-MM-DD format
#         check_out: Check-out date in YYYY-MM-DD format
#         room_type_id: Numeric ID of the room type
#         quantity: Number of rooms to book (default 1)
#         guests: Number of adults
#         children_details: Optional list of children info, e.g. [{'age': 5}]
#         selected_services: Optional list of services, e.g. [{'service_id': 1, 'quantity': 1}]
#     """
#     try:
#         d_in = date.fromisoformat(check_in)
#         d_out = date.fromisoformat(check_out)
#     except ValueError:
#         return "Error: Dates must be in YYYY-MM-DD format."

#     with _get_db_context() as db:
#         try:
#             # Fetch room details to get the base price and name
#             # room_type = db.query(HotelPolicy).filter_by(id=room_type_id).first() # Or your RoomType model query
#             # Assuming you query your room type table:
#             from models.db_models import RoomType
#             rt = db.query(RoomType).filter_by(id=room_type_id).first()
#             if not rt:
#                 return f"Error: Room Type ID {room_type_id} not found."

#             room_allocations = [{
#                 "room_type_id": rt.id,
#                 "name": rt.name,
#                 "quantity": quantity,
#                 "base_price": float(rt.base_price)
#             }]

#             # Resolve service details and prices from DB
#             resolved_services = []
#             if selected_services:
#                 for s_item in selected_services:
#                     s_id = s_item.get("service_id")
#                     srv = db.query(Service).filter_by(id=s_id).first()
#                     if srv:
#                         resolved_services.append({
#                             "service_id": srv.id,
#                             "name": srv.name,
#                             "price": float(srv.price),
#                             "pricing_unit": srv.pricing_unit,
#                             "quantity": s_item.get("quantity", 1),
#                             "start_date": s_item.get("start_date"),
#                             "end_date": s_item.get("end_date")
#                         })

#             kids = [ChildInfo(**c) for c in (children_details or [])]

#             # Execute the precise utility function
#             pricing_result = calculate_stay_pricing(
#                 check_in=d_in,
#                 check_out=d_out,
#                 room_allocations=room_allocations,
#                 selected_services=resolved_services,
#                 guests=guests,
#                 children_details=kids
#             )

#             # Format the output clearly for the LLM
#             output = [
#                 f"Official Pricing Breakdown ({pricing_result['nights']} nights, {guests} adults):",
#                 f"- Total Rooms Cost: PKR {pricing_result['total_rooms_cost']:,.2f}",
#                 f"- Total Services Cost: PKR {pricing_result['total_services_cost']:,.2f}",
#                 f"- **Total Estimated Amount: PKR {pricing_result['total_amount']:,.2f}**"
#             ]
#             return "\n".join(output)

#         except Exception as e:
#             logger.exception("TOOL calculate_stay_pricing -> FAILED")
#             return f"Error calculating pricing: {str(e)}"


# @tool
# def calculate_stay_pricing_tool(
#     check_in: str,
#     check_out: str,
#     room_type_id: int,
#     quantity: int = 1,
#     guests: int = 1,
#     children_details: Optional[List[dict]] = None,
#     selected_services: Optional[List[dict]] = None
# ) -> str:
#     """
#     Calculates the exact, authoritative stay pricing (rooms + add-on services) 
#     using the backend pricing utility rules. Use this before quoting prices to guests.
#     Args:
#         check_in: Check-in date in YYYY-MM-DD format
#         check_out: Check-out date in YYYY-MM-DD format
#         room_type_id: Numeric ID of the room type
#         quantity: Number of rooms to book (default 1)
#         guests: Number of adults
#         children_details: Optional list of children info, e.g. [{'age': 5}]
#         selected_services: Optional list of services, e.g. [{'service_id': 1, 'quantity': 1}]
#     """
#     try:
#         d_in = date.fromisoformat(check_in)
#         d_out = date.fromisoformat(check_out)
#     except ValueError:
#         return "Error: Dates must be in YYYY-MM-DD format."

#     with _get_db_context() as db:
#         try:
#             from models.db_models import RoomType, HotelPolicy
#             rt = db.query(RoomType).filter_by(id=room_type_id).first()
#             if not rt:
#                 return f"Error: Room Type ID {room_type_id} not found."

#             room_allocations = [{
#                 "room_type_id": rt.id,
#                 "name": rt.name,
#                 "quantity": quantity,
#                 "base_price": float(rt.base_price)
#             }]

#             # Resolve service details and prices from DB
#             resolved_services = []
#             if selected_services:
#                 for s_item in selected_services:
#                     s_id = s_item.get("service_id")
#                     srv = db.query(Service).filter_by(id=s_id).first()
#                     if srv:
#                         resolved_services.append({
#                             "service_id": srv.id,
#                             "name": srv.name,
#                             "price": float(srv.price),
#                             "pricing_unit": srv.pricing_unit,
#                             "quantity": s_item.get("quantity", 1),
#                             "start_date": s_item.get("start_date"),
#                             "end_date": s_item.get("end_date")
#                         })

#             kids = [ChildInfo(**c) for c in (children_details or [])]

#             # Fetch dynamic child policy if available in hotel_policy table
#             # child_policy_record = db.query(HotelPolicy).filter_by(key="child").first()
#             # child_policy = child_policy_record.value if child_policy_record else {"max_age": 12, "stay_free": True}

#             child_policy = get_all_policies(db).get("child") or {"max_age": 12, "stay_free": True}
           
#             # Execute the precise utility function
#             pricing_result = calculate_stay_pricing(
#                 check_in=d_in,
#                 check_out=d_out,
#                 room_allocations=room_allocations,
#                 selected_services=resolved_services,
#                 guests=guests,
#                 child_policy=child_policy,
#                 children_details=kids
#             )

#             # Format the output clearly for the LLM
#             output = [
#                 f"Official Pricing Breakdown ({pricing_result['nights']} nights, {guests} adults, {len(kids)} children):",
#                 f"- Total Rooms Cost: PKR {pricing_result['total_rooms_cost']:,.2f}",
#                 f"- Total Services Cost: PKR {pricing_result['total_services_cost']:,.2f}",
#                 f"- **Total Estimated Amount: PKR {pricing_result['total_amount']:,.2f}**"
#             ]
#             return "\n".join(output)

#         except Exception as e:
#             logger.exception("TOOL calculate_stay_pricing -> FAILED")
#             return f"Error calculating pricing: {str(e)}"

ALL_GUEST_TOOLS = [
    search_hotel_policies_tool,
    update_booking_services_tool,
    search_room_availability_tool,
    search_services_tool,
    get_booking_services_tool,
    get_user_profile_tool,
    add_service_to_hold_tool,
    create_booking_hold_tool,
    list_guest_bookings_tool,
    cancel_booking_tool,
    get_payment_link_info_tool,
    get_hotel_policy_tool,
    get_refund_quote_tool,
    calculate_stay_pricing_tool
]
