from datetime import date, timedelta
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, EmailStr

class BookingHoldRequest(BaseModel):
    guest_name: str
    guest_email: EmailStr
    check_in: date = date.today()
    check_out: date = date.today() + timedelta(days=1)
    guests: int = 1
    rooms: Dict[int, int] = {1: 1}  # room_type_id -> quantity
    services: List[Dict[str, Any]] = [{"service_id": 1, "quantity": 1}]

class ClaimBookingRequest(BaseModel):
    confirmation_code: str
    email: EmailStr

class RequestClaimOTPRequest(BaseModel):
    booking_ref: str
    email: EmailStr

class VerifyClaimOTPRequest(BaseModel):
    booking_ref: str
    email: EmailStr
    otp_code: str

class PaymentRequest(BaseModel):
    idempotency_key: Optional[str] = None
