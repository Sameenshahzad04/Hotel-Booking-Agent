from datetime import date
from typing import Dict, List, Any, Optional

# def calculate_service_line_total(
#     unit_price: float,
#     quantity: int = 1,
#     stay_nights: int = 1,
#     guests: int = 1,
#     start_date: Optional[date] = None,
#     end_date: Optional[date] = None
# ) -> Dict[str, Any]:
#     """
#     Simple, strict formula for add-on service line totals.
#     Note: Children under 12 stay 100% free and do not count in guest count.

#     Formulas:
#       - per_booking: unit_price * quantity
#       - per_night: unit_price * quantity * nights
#       - per_guest: unit_price * quantity * guests
#       - per_guest_per_night: unit_price * quantity * guests * nights
#     """
#     qty = max(1, int(quantity or 1))
#     price = float(unit_price or 0.0)
#     billable_guests = max(1, int(guests or 1))

#     # Determine service nights/days
#     if start_date and end_date and end_date > start_date:
#         service_nights = (end_date - start_date).days
#     else:
#         service_nights = max(1, int(stay_nights or 1))

#     unit = (pricing_unit or "per_booking").lower().strip()
#     if unit == "per_booking":
#         multiplier = 1.0
#     elif unit == "per_night":
#         multiplier = float(service_nights)
#     elif unit == "per_guest":
#         multiplier = float(billable_guests)
#     elif unit in ("per_guest_per_night", "per_guest_per_day"):
#         multiplier = float(billable_guests) * float(service_nights)
#     else:
#         multiplier = 1.0

#     line_total = round(price * qty * multiplier, 2)

#     return {
#         "unit_price": price,
#         "quantity": qty,
#         "pricing_unit": unit,
#         "service_nights": service_nights,
#         "multiplier": round(multiplier, 2),
#         "line_total": line_total
#     }

# def calculate_stay_pricing(
#     check_in: date,
#     check_out: date,
#     room_allocations: List[Dict[str, Any]],
#     selected_services: List[Dict[str, Any]],
#     guests: int = 1,
#     children: int = 0
# ) -> Dict[str, Any]:
#     """
#     Pure mathematical pricing utility.
#     Stay nights = (check_out - check_in).days
#     Children under 12 are 100% free and do not count in guest charges.
#     """
#     nights = (check_out - check_in).days
#     if nights < 1:
#         raise ValueError("Stay duration must be at least 1 night (check-out must be after check-in).")

#     # Room costs
#     rooms_breakdown = []
#     total_rooms_cost = 0.0

#     for r in room_allocations:
#         qty = r.get("quantity", 0)
#         if qty <= 0:
#             continue
#         base_price = float(r.get("base_price", 0.0))
#         subtotal = round(base_price * nights * qty, 2)
#         total_rooms_cost += subtotal
#         rooms_breakdown.append({
#             "room_type_id": r.get("room_type_id"),
#             "name": r.get("name"),
#             "quantity": qty,
#             "nights": nights,
#             "price_per_night": base_price,
#             "subtotal": subtotal
#         })

#     # Service costs
#     services_breakdown = []
#     total_services_cost = 0.0

#     for s in selected_services:
#         qty = s.get("quantity", 1)
#         price = float(s.get("price", 0.0))
#         unit = s.get("pricing_unit", "per_booking")
#         s_start = s.get("start_date") or check_in
#         s_end = s.get("end_date") or check_out

#         calc = calculate_service_line_total(
#             unit_price=price,
#             quantity=qty,
#             pricing_unit=unit,
#             stay_nights=nights,
#             guests=guests,
#             start_date=s_start,
#             end_date=s_end
#         )

#         subtotal = calc["line_total"]
#         total_services_cost += subtotal
#         services_breakdown.append({
#             "service_id": s.get("service_id"),
#             "name": s.get("name"),
#             "quantity": qty,
#             "unit_price": price,
#             "pricing_unit": calc["pricing_unit"],
#             "multiplier": calc["multiplier"],
#             "service_nights": calc["service_nights"],
#             "start_date": s_start,
#             "end_date": s_end,
#             "subtotal": subtotal
#         })

#     total_amount = round(total_rooms_cost + total_services_cost, 2)

#     return {
#         "nights": nights,
#         "guests": guests,
#         "children": children,
#         "rooms_breakdown": rooms_breakdown,
#         "services_breakdown": services_breakdown,
#         "total_rooms_cost": round(total_rooms_cost, 2),
#         "total_services_cost": round(total_services_cost, 2),
#         "total_amount": total_amount
#     }


def calculate_service_line_total(
    unit_price: float,
    quantity: int = 1,
    pricing_unit: str = "per_booking",
    stay_check_in: date = None,
    stay_check_out: date = None,
    guests: int = 1,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> Dict[str, Any]:
    qty = max(1, int(quantity or 1))
    price = float(unit_price or 0.0)
    billable_guests = max(1, int(guests or 1))

    # Strict date bounds validation for services
    s_start = start_date or stay_check_in
    s_end = end_date or stay_check_out
   

    if stay_check_in and stay_check_out:
        if s_start < stay_check_in or s_end >= stay_check_out or s_end <= s_start:
            raise ValueError("Service dates must be within check-in and check-out bounds.")

    service_nights = (s_end - s_start).days if (s_start and s_end) else (stay_check_out - stay_check_in).days

    unit = (pricing_unit or "per_booking").lower().strip()
    
    if unit == "per_booking":
        multiplier = 1.0
    elif unit == "per_night":
        multiplier = float(max(1, service_nights))
    elif unit == "per_guest":
        multiplier = float(billable_guests)
    elif unit in ("per_guest_per_night", "per_guest_per_day"):
        multiplier = float(billable_guests) * float(max(1, service_nights))
    else:
        multiplier = 1.0

    return {
        "unit_price": price,
        "quantity": qty,
        "pricing_unit": unit,
        "service_nights": service_nights,
        "multiplier": round(multiplier, 2),
        "line_total": round(price * qty * multiplier, 2),
        "start_date": s_start,
        "end_date": s_end
    }

# def calculate_stay_pricing(
#     check_in: date,
#     check_out: date,
#     room_allocations: List[Dict[str, Any]],
#     selected_services: List[Dict[str, Any]],
#     guests: int = 1,
#     child_policy: Optional[Dict[str, Any]] = None,
#     children_details: Optional[List[Any]] = None
# ) -> Dict[str, Any]:
#     nights = (check_out - check_in).days
#     if nights < 1:
#         raise ValueError("Stay duration must be at least 1 night.")

#     # Dynamic Child Policy parsing from hotel_policy table
#     max_free_age = child_policy.get("max_age", 12) if child_policy else 12
#     stay_free = child_policy.get("stay_free", True) if child_policy else True

#     billable_children = 0
#     if children_details:
#         for kid in children_details:
#             age = getattr(kid, "age", kid.age)
#             if stay_free and age < max_free_age:
#                 continue  # Stays 100% free, does not count as adult guest
#             billable_children += 1

#     billable_adults = max(1, guests + billable_children)

#     # Room costs calculation
#     total_rooms_cost = 0.0
#     for r in room_allocations:
#         qty = r.get("quantity", 0)
#         if qty <= 0:
#             continue
#         subtotal = round(float(r.get("base_price", 0.0)) * nights * qty, 2)
#         total_rooms_cost += subtotal

#     # Service costs calculation
#     services_breakdown = []

#     total_services_cost = inner_services = []
#     total_services_cost_val = 0.0
#     for s in selected_services:
#         calc = calculate_service_line_total(
#             unit_price=s.get("price", 0.0),
#             quantity=s.get("quantity", 1),
#             pricing_unit=s.get("pricing_unit", "per_booking"),
#             stay_check_in=check_in,
#             stay_check_out=check_out,
#             guests=billable_adults,
#             start_date=s.get("start_date"),
#             end_date=s.get("end_date")
#         )
#         total_services_cost_val += calc["line_total"]
#         s["start_date"] = calc["start_date"]
#         s["end_date"] = calc["end_date"]

#     return {
#         "nights": nights,
#         "guests": guests,
#         "billable_adults": billable_adults,
#         "total_rooms_cost": round(total_rooms_cost, 2),
#         "total_services_cost": round(total_services_cost_val, 2),
#         "total_amount": round(total_rooms_cost + total_services_cost_val, 2)
#     }

def calculate_stay_pricing(
    check_in: date,
    check_out: date,
    room_allocations: List[Dict[str, Any]],
    selected_services: List[Dict[str, Any]],
    guests: int = 1,
    child_policy: Optional[Dict[str, Any]] = None,
    children_details: Optional[List[Any]] = None
) -> Dict[str, Any]:
    nights = (check_out - check_in).days
    if nights < 1:
        raise ValueError("Stay duration must be at least 1 night.")

    # Dynamic Child Policy parsing from hotel_policy table
    max_free_age = child_policy.get("max_age", 12) if child_policy else 12
    stay_free = child_policy.get("stay_free", True) if child_policy else True

    billable_children = 0
    if children_details:
        for kid in children_details:
            age = kid.age if hasattr(kid, "age") else kid["age"]  
            if stay_free and age < max_free_age:
                continue  # Stays 100% free, does not count as adult guest
            billable_children += 1

    billable_adults = max(1, guests + billable_children)

    # Room costs calculation
    total_rooms_cost = 0.0
    for r in room_allocations:
        qty = r.get("quantity", 0)
        if qty <= 0:
            continue
        subtotal = round(float(r.get("base_price", 0.0)) * nights * qty, 2)
        total_rooms_cost += subtotal

    # Service costs calculation & breakdown collection
    services_breakdown = []
    total_services_cost_val = 0.0
    
    for s in selected_services:
        calc = calculate_service_line_total(
            unit_price=s.get("price", 0.0),
            quantity=s.get("quantity", 1),
            pricing_unit=s.get("pricing_unit", "per_booking"),
            stay_check_in=check_in,
            stay_check_out=check_out,
            guests=billable_adults,  # Uses billable adults (which includes non-free children/extra guests) as multiplier for 'per_guest'
            start_date=s.get("start_date"),
            end_date=s.get("end_date")
        )
        
        subtotal = calc["line_total"]
        total_services_cost_val += subtotal
        
        services_breakdown.append({
            "service_id": s.get("service_id"),
            "name": s.get("name"),
            "quantity": s.get("quantity", 1),
            "unit_price": calc["unit_price"],
            "pricing_unit": calc["pricing_unit"],
            "multiplier": calc["multiplier"],
            "service_nights": calc["service_nights"],
            "start_date": calc["start_date"],
            "end_date": calc["end_date"],
            "line_total": subtotal
        })

    return {
        "nights": nights,
        "guests": guests,
        "billable_adults": billable_adults,
        "rooms_breakdown": room_allocations,
        "services_breakdown": services_breakdown,
        "total_rooms_cost": round(total_rooms_cost, 2),
        "total_services_cost": round(total_services_cost_val, 2),
        "total_amount": round(total_rooms_cost + total_services_cost_val, 2)
    }





def format_child_age(age: int) -> str:
    """Formats child age for display and reporting."""
    if age == 0:
        return "Infant"
    elif age == 1:
        return "1 year old"
    else:
        return f"{age} years old"