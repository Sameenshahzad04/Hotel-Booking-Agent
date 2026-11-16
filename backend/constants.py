"""Shared constants module - single source of truth for DEFAULT_POLICIES."""
from typing import Any, Dict

DEFAULT_POLICIES: Dict[str, Dict[str, Any]] = {
    "child": {
        "max_age": 12,
        "stay_free": True,
        "counts_as_guest": False,
        "note": "Children under 12 stay 100% free and do NOT count as guests for room capacity or booking charges.",
    },
    "pet": {
        "allowed": False,
        "service_animals_allowed": True,
        "fee_per_night": 0,
        "note": "Pets are strictly not allowed on hotel premises. Certified service animals are welcome with prior documentation.",
    },
    "check_in_out": {
        "check_in": "14:00",
        "check_out": "12:00",
        "early_checkin_subject_to_availability": True,
        "note": "Standard check-in starts at 14:00 (2:00 PM). Check-out is by 12:00 PM (Noon). Late check-out is subject to room availability.",
    },
    "cancellation": {
        "full_refund_days": 7,
        "partial_refund_days": 2,
        "partial_refund_percent": 50,
        "note": "Full refund if cancelled at least 7 days before check-in. 50% refund if cancelled between 2 and 7 days. Non-refundable within 48 hours.",
    },
    "payment": {
        "currency": "PKR",
        "hold_hours": 2,
        "note": "Bookings are held unpaid for 2 hours before rooms are automatically released back to inventory.",
    },
    "smoking": {
        "allowed_in_rooms": False,
        "designated_areas_only": True,
        "note": "All guest rooms and indoor public areas are 100% non-smoking. Designated outdoor smoking zones are provided.",
    },
    "id_requirements": {
        "accepted_ids": ["CNIC", "Passport"],
        "note": "Valid original CNIC for Pakistani nationals or Passport with valid Pakistani visa for international guests is mandatory upon check-in.",
    },
}