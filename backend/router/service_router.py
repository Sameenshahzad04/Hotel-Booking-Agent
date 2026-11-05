#!router/service_router.py
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from models.connection import get_db
from models.db_models import UserAccount, Service, Booking, BookingService
from router.auth_router import get_current_user

router = APIRouter(prefix="/services", tags=["Services & Add-ons"])

class AddServiceRequest(BaseModel):
    service_id: int
    quantity: int = 1

@router.get("")
def list_available_services(db: Session = Depends(get_db)):
    """Lists all available hotel add-on services (breakfast, transport, etc.)."""
    services = db.query(Service).all()
    items = []
    for s in services:
        items.append({
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "price": s.price,
            "pricing_unit": s.pricing_unit
        })
    return {"services": items}

@router.post("/bookings/{ref}/services")
def add_service_to_booking(
    ref: str,
    req: AddServiceRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Allows adding or updating services on an existing booking 
    as long as the booking belongs to the user and is still unpaid (PENDING/UNPAID).
    """
    booking = db.query(Booking).filter_by(booking_ref=ref).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")

    if booking.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this booking.")

    if booking.payment_status != "UNPAID" or booking.status != "PENDING":
        raise HTTPException(
            status_code=400, 
            detail="Cannot modify services: Booking is already paid or completed/cancelled."
        )

    service = db.query(Service).filter_by(id=req.service_id).first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found.")

    if req.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be at least 1.")

    # Check if service already attached to booking, update or create new entry
    existing_bs = (
        db.query(BookingService)
        .filter_by(booking_id=booking.id, service_id=service.id)
        .first()
    )

    # Compute price adjustment
    unit_p = service.price
    if existing_bs:
        # Subtract old cost, add new cost
        old_cost = existing_bs.quantity * existing_bs.unit_price
        new_cost = req.quantity * unit_p
        booking.total_amount = booking.total_amount - old_cost + new_cost
        
        existing_bs.quantity = req.quantity
        existing_bs.unit_price = unit_p
    else:
        new_cost = req.quantity * unit_p
        booking.total_amount += new_cost
        
        new_bs = BookingService(
            booking_id=booking.id,
            service_id=service.id,
            quantity=req.quantity,
            unit_price=unit_p
        )
        db.add(new_bs)

    db.commit()
    db.refresh(booking)

    return {
        "success": True,
        "message": "Booking services updated successfully.",
        "booking_ref": booking.booking_ref,
        "new_total_amount": booking.total_amount
    }
@router.get("/booking/{booking_ref}")
def get_services_for_booking(
    booking_ref: str,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve all add-on services attached to a specific booking reference for the authenticated user.
    """
    # Verify booking belongs to user
    booking = db.query(Booking).filter_by(booking_ref=booking_ref, user_id=current_user.id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found for your account.")

    # Query booking services joined with service details
    booking_services = (
        db.query(BookingService, Service)
        .join(Service, BookingService.service_id == Service.id)
        .filter(BookingService.booking_id == booking.id)
        .all()
    )

    services_list = []
    for bs, service in booking_services:
        services_list.append({
            "booking_service_id": bs.id,
            "service_id": service.id,
            "name": service.name,
            "description": service.description,
            "quantity": bs.quantity,
            "unit_price": bs.unit_price,
            "total_price": bs.quantity * bs.unit_price,
            "pricing_unit": service.pricing_unit
        })

    return {
        "success": True,
        "booking_ref": booking.booking_ref,
        "total_services_count": len(services_list),
        "services": services_list
    }
