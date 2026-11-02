from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from config import config
from models.connection import get_db
from models.db_models import Service, RoomType

router = APIRouter(prefix="/services", tags=["Services & Hotel Info"])

@router.get("")
def list_hotel_services_and_rooms(db: Session = Depends(get_db)):
    """Returns official PC Lahore room categories and add-on services."""
    services = db.query(Service).all()
    room_types = db.query(RoomType).all()

    return {
        "hotel_name": "Pearl Continental Hotel Lahore",
        "currency": "PKR",
        "check_in_time": config.CHECK_IN_TIME,
        "check_out_time": config.CHECK_OUT_TIME,
        "room_types": [
            {
                "id": rt.id,
                "name": rt.name,
                "description": rt.description,
                "base_price": rt.base_price,
                "max_guests": rt.max_guests,
                "bed_type": rt.bed_type,
                "amenities": rt.amenities
            }
            for rt in room_types
        ],
        "services": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "price": s.price,
                "pricing_unit": s.pricing_unit
            }
            for s in services
        ]
    }
