
from datetime import date
from typing import Dict, List, Any

def calculate_stay_pricing(
    check_in: date,
    check_out: date,
    room_allocations: List[Dict[str, Any]],  # [{"room_type_id": int, "name": str, "base_price": float, "quantity": int}]
    selected_services: List[Dict[str, Any]], # [{"service_id": int, "name": str, "price": float, "pricing_unit": str, "quantity": int}]
    guests: int
) -> Dict[str, Any]:
    """
    Pure mathematical pricing utility for stays and add-ons in PKR.
    """
    nights = (check_out - check_in).days
    if nights < 1:
        raise ValueError("Stay duration must be at least 1 night.")

    rooms_breakdown = []
    total_rooms_cost = 0.0

    for r in room_allocations:
        qty = r.get("quantity", 0)
        if qty <= 0:
            continue
        base_price = r.get("base_price", 0.0)
        subtotal = round(base_price * nights * qty, 2)
        total_rooms_cost += subtotal
        rooms_breakdown.append({
            "room_type_id": r.get("room_type_id"),
            "name": r.get("name"),
            "quantity": qty,
            "nights": nights,
            "price_per_night": base_price,
            "subtotal": subtotal
        })

    services_breakdown = []
    total_services_cost = 0.0

    for s in selected_services:
        qty = s.get("quantity", 1)
        price = s.get("price", 0.0)
        unit = s.get("pricing_unit", "per_booking")

        if unit == "per_booking":
            subtotal = price * qty
        elif unit == "per_night":
            subtotal = price * nights * qty
        elif unit == "per_guest":
            subtotal = price * guests * qty
        else:
            subtotal = price * qty

        subtotal = round(subtotal, 2)
        total_services_cost += subtotal
        services_breakdown.append({
            "service_id": s.get("service_id"),
            "name": s.get("name"),
            "quantity": qty,
            "unit_price": price,
            "pricing_unit": unit,
            "subtotal": subtotal
        })

    total_amount = round(total_rooms_cost + total_services_cost, 2)

    return {
        "nights": nights,
        "guests": guests,
        "rooms_breakdown": rooms_breakdown,
        "services_breakdown": services_breakdown,
        "total_rooms_cost": round(total_rooms_cost, 2),
        "total_services_cost": round(total_services_cost, 2),
        "total_amount": total_amount
    }