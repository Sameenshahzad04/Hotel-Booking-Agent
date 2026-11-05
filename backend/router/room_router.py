
from datetime import date
from fastapi import APIRouter, Depends, HTTPException,Query
from sqlalchemy.orm import Session
from models.connection import get_db
from handler.availability_handler import query_live_availability

router = APIRouter(prefix="/rooms", tags=["Rooms & Availability"])


def validate_not_past(v: date) -> date:
    if v < date.today():
        raise HTTPException(status_code=422, detail="Date cannot be in the past.")
    return v

@router.get("/availability")
def get_room_availability(
  db: Session = Depends(get_db),
    check_in: date = Query(..., description="Check-in date (YYYY-MM-DD)", examples=["2026-11-05"]),
    check_out: date = Query(..., description="Check-out date (YYYY-MM-DD)", examples=["2026-11-07"]),
    guests: int = Query(1, ge=1, description="Number of guests")
):
    """Returns live available rooms per room type for requested dates."""
    validate_not_past(check_in)
    validate_not_past(check_out)

    #
    if check_out <= check_in:
        raise HTTPException(status_code=400, detail="Check-out date must be strictly after check-in date.")

    availability = query_live_availability(db, check_in=check_in, check_out=check_out, guests=guests)
    return {
        "check_in": check_in,
        "check_out": check_out,
        "guests": guests,
        "availability": availability
    }

