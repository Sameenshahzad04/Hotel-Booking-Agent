#!migrate_db.py
"""One-time, safe migration. Keeps all existing data. Safe to run multiple times."""
import json
import sys
from pathlib import Path

# Ensure backend directory is in python search path
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from sqlalchemy import text
from models.connection import get_db

STATEMENTS = [
    # 1. Booking table: add children and infants
"ALTER TABLE booking_service ADD COLUMN IF NOT EXISTS pricing_unit TEXT;"
"ALTER TABLE booking_service ADD COLUMN IF NOT EXISTS multiplier FLOAT DEFAULT 1.0;"
"ALTER TABLE booking_service ADD COLUMN IF NOT EXISTS line_total FLOAT DEFAULT 0.0;"

'''CREATE TABLE IF NOT EXISTS hotel_policy (
    key TEXT PRIMARY KEY,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);'''
]

DEFAULT_POLICIES = {
    "child": {
        "max_age": 12,
        "stay_free": True,
        "counts_as_guest": False,
        "note": "Children under 12 stay 100% free and do NOT count as guests for room capacity or booking charges."
    },
    "pet": {
        "allowed": False,
        "service_animals_allowed": True,
        "fee_per_night": 0,
        "note": "Pets are strictly not allowed on hotel premises. Certified service animals are welcome with prior documentation."
    },
    "check_in_out": {
        "check_in": "14:00",
        "check_out": "12:00",
        "early_checkin_subject_to_availability": True,
        "note": "Standard check-in starts at 14:00 (2:00 PM). Check-out is by 12:00 PM (Noon). Late check-out is subject to room availability."
    },
    "cancellation": {
        "full_refund_days": 7,
        "partial_refund_days": 2,
        "partial_refund_percent": 50,
        "note": "Full refund if cancelled at least 7 days before check-in. 50% refund if cancelled between 2 and 7 days. Non-refundable within 48 hours."
    },
    "payment": {
        "currency": "PKR",
        "hold_hours": 2,
        "note": "Bookings are held unpaid for 2 hours before rooms are automatically released back to inventory."
    },
    "smoking": {
        "allowed_in_rooms": False,
        "designated_areas_only": True,
        "note": "All guest rooms and indoor public areas are 100% non-smoking. Designated outdoor smoking zones are provided."
    },
    "id_requirements": {
        "accepted_ids": ["CNIC", "Passport"],
        "note": "Valid original CNIC for Pakistani nationals or Passport with valid Pakistani visa for international guests is mandatory upon check-in."
    }
}

def main():
    db = next(get_db())
    try:
        print("--- Running Migration Statements ---")
        for sql in STATEMENTS:
            db.execute(text(sql))
            print("OK:", " ".join(sql.split())[:80])
        db.commit()

        # Seed default policies if empty
        print("\n--- Seeding Default Hotel Policies ---")
        for k, v in DEFAULT_POLICIES.items():
            db.execute(
                text("""
                    INSERT INTO hotel_policy (key, data, updated_at)
                    VALUES (:key, :data, now())
                    ON CONFLICT (key) DO NOTHING
                """),
                {"key": k, "data": json.dumps(v)}
            )
        db.commit()
        print("Hotel policies seeded successfully.")

        print("\nCurrent services (check pricing_unit values):")
        for row in db.execute(text("SELECT id, name, price, pricing_unit FROM service ORDER BY id")):
            print(" ", tuple(row))
    except Exception as e:
        db.rollback()
        print("FAILED, rolled back:", e)
    finally:
        db.close()

if __name__ == "__main__":
    main()
