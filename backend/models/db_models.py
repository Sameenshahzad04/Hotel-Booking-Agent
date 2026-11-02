from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime, 
    ForeignKey, Text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from models.connection import Base

class GuestSession(Base):
    __tablename__ = "guest_session"

    id = Column(Integer, primary_key=True, index=True)
    session_token_hash = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    bookings = relationship("Booking", back_populates="guest_session")
    transactions = relationship("Transaction", back_populates="guest_session")
    tickets = relationship("Ticket", back_populates="guest_session")


class RoomType(Base):
    __tablename__ = "room_type"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    base_price = Column(Float, nullable=False)
    max_guests = Column(Integer, nullable=False)
    bed_type = Column(String, nullable=False)
    amenities = Column(JSONB, default=list)

    rooms = relationship("Room", back_populates="room_type")


class Room(Base):
    __tablename__ = "room"

    id = Column(Integer, primary_key=True, index=True)
    room_type_id = Column(Integer, ForeignKey("room_type.id", ondelete="RESTRICT"), nullable=False)
    room_number = Column(String, unique=True, nullable=False)
    floor = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    room_type = relationship("RoomType", back_populates="rooms")
    booking_rooms = relationship("BookingRoom", back_populates="room")


class Service(Base):
    __tablename__ = "service"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    pricing_unit = Column(String, nullable=False)


class Booking(Base):
    __tablename__ = "booking"

    id = Column(Integer, primary_key=True, index=True)
    booking_ref = Column(String, unique=True, nullable=False, index=True)
    confirmation_code = Column(String, unique=True, nullable=True, index=True)
    guest_session_id = Column(Integer, ForeignKey("guest_session.id", ondelete="RESTRICT"), nullable=False)
    guest_name = Column(String, nullable=False)
    guest_email = Column(String, nullable=False)
    check_in = Column(Date, nullable=False)
    check_out = Column(Date, nullable=False)
    guests = Column(Integer, nullable=False)
    status = Column(String, default="PENDING", nullable=False)
    payment_status = Column(String, default="UNPAID", nullable=False)
    hold_expires_at = Column(DateTime(timezone=True), nullable=False)
    total_amount = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    paid_at = Column(DateTime(timezone=True), nullable=True)

    guest_session = relationship("GuestSession", back_populates="bookings")
    booking_rooms = relationship("BookingRoom", back_populates="booking", cascade="all, delete-orphan")
    booking_services = relationship("BookingService", back_populates="booking", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="booking")
    notifications = relationship("Notification", back_populates="booking", cascade="all, delete-orphan")


class BookingRoom(Base):
    __tablename__ = "booking_room"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("booking.id", ondelete="CASCADE"), nullable=False)
    room_id = Column(Integer, ForeignKey("room.id", ondelete="RESTRICT"), nullable=False)
    check_in = Column(Date, nullable=False)
    check_out = Column(Date, nullable=False)
    price_per_night = Column(Float, nullable=False)
    blocks_inventory = Column(Boolean, default=True, nullable=False)

    booking = relationship("Booking", back_populates="booking_rooms")
    room = relationship("Room", back_populates="booking_rooms")


class BookingService(Base):
    __tablename__ = "booking_service"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("booking.id", ondelete="CASCADE"), nullable=False)
    service_id = Column(Integer, ForeignKey("service.id", ondelete="RESTRICT"), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    unit_price = Column(Float, nullable=False)

    booking = relationship("Booking", back_populates="booking_services")
    service = relationship("Service")


class Transaction(Base):
    __tablename__ = "transaction"

    id = Column(Integer, primary_key=True, index=True)
    guest_session_id = Column(Integer, ForeignKey("guest_session.id", ondelete="RESTRICT"), nullable=False)
    booking_id = Column(Integer, ForeignKey("booking.id", ondelete="RESTRICT"), nullable=False)
    type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    parent_transaction_id = Column(Integer, ForeignKey("transaction.id"), nullable=True)
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    guest_session = relationship("GuestSession", back_populates="transactions")
    booking = relationship("Booking", back_populates="transactions")


class Notification(Base):
    __tablename__ = "notification"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("booking.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String, nullable=False)
    to_email = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    sent_at = Column(DateTime(timezone=True), nullable=True)

    booking = relationship("Booking", back_populates="notifications")


class Ticket(Base):
    __tablename__ = "ticket"

    id = Column(Integer, primary_key=True, index=True)
    guest_session_id = Column(Integer, ForeignKey("guest_session.id", ondelete="RESTRICT"), nullable=False)
    booking_id = Column(Integer, ForeignKey("booking.id", ondelete="SET NULL"), nullable=True)
    category = Column(String, default="GENERAL", nullable=False)
    status = Column(String, default="OPEN", nullable=False)
    messages = Column(JSONB, default=list, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    guest_session = relationship("GuestSession", back_populates="tickets")
    booking = relationship("Booking")


class BookingOTP(Base):
    """
    Temporary One-Time Password for claiming bookings across sessions.
    Guarantees that a user requesting to link a booking actually owns the email inbox.
    """
    __tablename__ = "booking_otp"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("booking.id", ondelete="CASCADE"), nullable=False)
    target_email = Column(String, nullable=False)
    otp_code = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    booking = relationship("Booking")
