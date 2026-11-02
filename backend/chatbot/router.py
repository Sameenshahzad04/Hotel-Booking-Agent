"""
Chat endpoint for the HotelAgent LangGraph chatbot.

This module provides the FastAPI router for the /chat endpoint that integrates
with the LangGraph agent. It handles session validation, message processing,
and streaming responses.

DESIGN PRINCIPLE: The chatbot uses the same anonymous session system as the rest
of the application. All bookings are isolated by guest_session_id.
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from models.connection import get_db
from models.db_models import GuestSession
from handler.session_handler import get_or_create_guest_session
from datetime import date, timedelta
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, EmailStr
from chatbot.customer_agent import process_message

from util.security_util import hash_session_token

router = APIRouter(prefix="/chat", tags=["Chatbot"])

# schema 
class Request(BaseModel):
    message: str
    session_id: Optional[int] = None
    session_token: Optional[str] = None
    conversation_id: Optional[str] = None


@router.post("")
async def chat_endpoint(
    req: Request,
    x_session_token: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Handle a chat message from a guest.
    
    Request body:
    {
        "message": "I want to book a room",
        "session_id": 1,              # Optional: use existing session ID
        "session_token": "raw-token",  # Optional: use existing session token
        "conversation_id": "optional-id"
    }
    """
    message = req.message
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    session = None
    raw_token = req.session_token or x_session_token

    # 1. If an explicit session_id is provided, try looking it up
    if req.session_id:
        session = db.query(GuestSession).filter_by(id=req.session_id).first()

    # 2. If session wasn't found by ID but a token was provided, look it up by token hash
    if not session and raw_token:
        token_hash = hash_session_token(raw_token)
        session = db.query(GuestSession).filter_by(session_token_hash=token_hash).first()

    # 3. Only create a brand new session if neither ID nor token matched an existing session
    if not session:
        session, raw_token = get_or_create_guest_session(db, raw_token=raw_token)
    elif not raw_token:
        raw_token = "active-session"

    # Process the message through the agent
    response = process_message(
        message=message,
        session_id=session.id,
        session_token=raw_token
    )
    
    return {
        "success": True,
        "response": response,
        "session_id": session.id,
        "session_token": raw_token
    }