
"""Chat endpoint for the HotelAgent LangGraph chatbot.

This module provides the FastAPI router for the /chat and /chat/new endpoints 
that integrate with the LangGraph agent. It handles authenticated user session validation, 
thread tracking, message processing, and starting fresh chat sessions.

DESIGN PRINCIPLE: The chatbot uses authenticated user accounts and thread-based 
chat management. All data is isolated by user_id.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models.connection import get_db
from models.db_models import UserAccount, ChatThread
from router.auth_router import get_current_user
from handler.chat_handler import (
    save_chat_message_handler, 
    get_or_create_active_thread_handler,
    close_active_thread_handler
)
from typing import Optional
from pydantic import BaseModel
from chatbot.customer_agent import process_message

router = APIRouter(prefix="/chat", tags=["Chatbot"])

class Request(BaseModel):
    message: str
    thread_id: Optional[int] = None
    conversation_id: Optional[str] = None

@router.post("")
async def chat_endpoint(
    req: Request,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Handle a chat message from an authenticated user.
    """
    message = req.message
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    # 1. Get or create active chat thread for the authenticated user
    thread = get_or_create_active_thread_handler(
        db=db,
        user_id=current_user.id
    )

    # If specific thread_id was requested, validate and use it
    if req.thread_id:
        target_thread = db.query(ChatThread).filter_by(id=req.thread_id, user_id=current_user.id).first()
        if target_thread:
            thread = target_thread

    # 2. Save incoming user message to database
    save_chat_message_handler(
        db=db,
        user_id=current_user.id,
        sender="user",
        message_text=message,
        thread_id=thread.id
    )

    # 3. Process the message through the agent
    response = process_message(
        message=message,
        user_id=current_user.id,
        thread_id=thread.id
    )

    # 4. Save assistant response to database
    save_chat_message_handler(
        db=db,
        user_id=current_user.id,
        sender="assistant",
        message_text=response,
        thread_id=thread.id
    )
    
    return {
        "success": True,
        "response": response,
        "thread_id": thread.id,
        "user_id": current_user.id
    }


@router.post("/new")
async def new_chat_endpoint(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Closes the user's current ACTIVE chat thread (the '+ New Chat' action) 
    so they can start a clean conversation next time.
    """
    closed_thread_id = close_active_thread_handler(db=db, user_id=current_user.id)
    
    return {
        "success": True,
        "message": "Active chat thread closed successfully.",
        "closed_thread_id": closed_thread_id
    }

