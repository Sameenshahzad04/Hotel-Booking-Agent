from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models.connection import get_db
from handler.availability_handler import query_live_availability

router = APIRouter(prefix="/rooms", tags=["Rooms & Availability"])

@router.get("/availability")
def get_room_availability(
    check_in: date,
    check_out: date,
    guests: int = 1,
    db: Session = Depends(get_db)
):
    """Returns live available rooms per room type for requested dates."""
    if check_out <= check_in:
        raise HTTPException(status_code=400, detail="Check-out date must be strictly after check-in date.")

    availability = query_live_availability(db, check_in=check_in, check_out=check_out, guests=guests)
    return {
        "check_in": check_in,
        "check_out": check_out,
        "guests": guests,
        "availability": availability
    }
