#!handler/chat_handler.py
"""Database work for user chat threads and messages.

The chatbot node or API router only calls the functions below, 
so all the SQLAlchemy code stays here and out of the graph/router logic.
"""
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from models.db_models import Booking, UserAccount, ChatThread, ChatMessage

def get_or_create_active_thread_handler(
    db: Session,
    user_id: int,
    title: Optional[str] = "Hotel Inquiry"
) -> ChatThread:
    """
    Retrieves the user's most recent active chat thread or creates a new one 
    if none exists. Links it to the latest booking if available.
    """
    user = db.query(UserAccount).filter_by(id=user_id).first()
    if not user:
        raise ValueError("User account not found.")

    thread = (
        db.query(ChatThread)
        .filter_by(user_id=user_id, status="ACTIVE")
        .order_by(ChatThread.updated_at.desc())
        .first()
    )

    latest_booking = (
        db.query(Booking)
        .filter_by(user_id=user_id)
        .order_by(Booking.created_at.desc())
        .first()
    )

    if not thread:
        thread = ChatThread(
            user_id=user_id,
            title=title,
            booking_id=latest_booking.id if latest_booking else None,
            status="ACTIVE"
        )
        db.add(thread)
        db.commit()
        db.refresh(thread)
    else:
        if latest_booking and not thread.booking_id:
            thread.booking_id = latest_booking.id
            db.commit()

    return thread

def close_active_thread_handler(db: Session, user_id: int) -> Optional[int]:
    active = (
        db.query(ChatThread)
        .filter_by(user_id=user_id, status="ACTIVE")
        .order_by(ChatThread.updated_at.desc())
        .all()
    )
    for t in active:
        t.status = "CLOSED"
    db.commit()
    return active[0].id if active else None

# def close_active_thread_handler(db: Session, user_id: int) -> Optional[int]:
#     """
#     Closes the user's current ACTIVE chat thread by flipping its status to 'CLOSED'.
#     Used when the user clicks '+ New Chat' in the frontend.
#     """
#     active_thread = (
#         db.query(ChatThread)
#         .filter_by(user_id=user_id, status="ACTIVE")
#         .first()
#     )
    
#     if active_thread:
#         active_thread.status = "CLOSED"
#         db.commit()
#         return active_thread.id
    
#     return None


# def save_chat_message_handler(
#     db: Session,
#     user_id: int,
#     sender: str,
#     message_text: str,
#     thread_id: Optional[int] = None
# ) -> dict:
#     """
#     Saves an individual chat message into a chat thread for the authenticated user.
#     """
#     if thread_id:
#         thread = db.query(ChatThread).filter_by(id=thread_id, user_id=user_id).first()
#         if not thread:
#             raise ValueError("Chat thread not found or access denied.")
#     else:
#         thread = get_or_create_active_thread_handler(db, user_id)

#     # FIXED: Use 'role' and 'content' matching db_models.py exactly
#     chat_message = ChatMessage(
#         thread_id=thread.id,
#         role=sender,  # 'user' or 'assistant'
#         content=message_text
#     )
#     db.add(chat_message)
    
#     db.commit()
#     db.refresh(chat_message)

#     return {
#         "success": True,
#         "thread_id": thread.id,
#         "message_id": chat_message.id,
#         "sender": chat_message.role,
#         "created_at": chat_message.created_at
#     }


def save_chat_message_handler(
    db: Session,
    user_id: int,
    sender: str,
    message_text: str,
    thread_id: Optional[int] = None
) -> dict:
    """
    Saves an individual chat message into a chat thread for the authenticated user
    and updates the thread title dynamically based on the first user message.
    """
    if thread_id:
        thread = db.query(ChatThread).filter_by(id=thread_id, user_id=user_id).first()
        if not thread:
            raise ValueError("Chat thread not found or access denied.")
    else:
        thread = get_or_create_active_thread_handler(db, user_id)

    # DYNAMIC TITLE LOGIC: If sender is user and title is default, update title to message snippet
    if sender == "user" and (not thread.title or thread.title == "Hotel Inquiry"):
        clean_title = message_text.strip()
        if len(clean_title) > 35:
            clean_title = clean_title[:32] + "..."
        thread.title = clean_title
        db.commit()

    # Save message
    chat_message = ChatMessage(
        thread_id=thread.id,
        role=sender,  # 'user' or 'assistant'
        content=message_text
    )
    db.add(chat_message)
    thread.updated_at = datetime.now(timezone.utc) 
    db.commit()
    db.refresh(chat_message)

    return {
        "success": True,
        "thread_id": thread.id,
        "message_id": chat_message.id,
        "sender": chat_message.role,
        "created_at": chat_message.created_at
    }
def get_thread_transcript_handler(db: Session, user_id: int, thread_id: int) -> List[Dict[str, Any]]:
    """Retrieves all messages for a specific user chat thread."""
    if thread_id:
        thread = db.query(ChatThread).filter_by(id=thread_id, user_id=user_id).first()
        if not thread:
            raise ValueError("Chat thread not found or access denied.")
    else:
        thread = get_or_create_active_thread_handler(db, user_id)
    messages = (
        db.query(ChatMessage)
        .filter_by(thread_id=thread_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    # FIXED: Map database 'role' and 'content' to response keys
    return [
        {
            "id": msg.id,
            "sender": msg.role,
            "message": msg.content,
            "created_at": msg.created_at
        }
        for msg in messages
    ]