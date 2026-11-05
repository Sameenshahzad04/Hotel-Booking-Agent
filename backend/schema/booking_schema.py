
from datetime import date, timedelta
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, EmailStr,Field

class BookingHoldRequest(BaseModel):
    check_in: date = Field(
        default_factory=date.today,
        description="Check-in date in YYYY-MM-DD format",
        json_schema_extra={"example": "2026-11-05"}
    )
    check_out: date = Field(
        default_factory=lambda: date.today() + timedelta(days=1),
        description="Check-out date in YYYY-MM-DD format",
        json_schema_extra={"example": "2026-11-07"}
    )
    
    guests: int = 1
    rooms: Dict[int, int] = {1: 1}  # room_type_id -> quantity
    services: List[Dict[str, Any]]|None = [{"service_id": 1, "quantity": 1}]

class PaymentRequest(BaseModel):
    idempotency_key: Optional[str] = None

class CreateChatThreadRequest(BaseModel):
    title: Optional[str] = "New Chat"

class SendChatMessageRequest(BaseModel):
    content: str

class RoomAvailabilityQuery(BaseModel):
    check_in: date = Field(..., json_schema_extra={"example": "2026-11-05"})
    check_out: date = Field(..., json_schema_extra={"example": "2026-11-07"})
    guests: int = Field(default=1, ge=1, json_schema_extra={"example": 1})