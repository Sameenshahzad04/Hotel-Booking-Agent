# #!chatbot/router.py
# """Chat endpoint for the HotelAgent LangGraph chatbot.

# This module provides the FastAPI router for the /chat, /chat/history and /chat/new
# endpoints that integrate with the LangGraph agent. It handles authenticated user
# session validation, thread tracking, message processing, and starting fresh chat sessions.

# DESIGN PRINCIPLE: The chatbot uses authenticated user accounts and thread-based
# chat management. All data is isolated by user_id.
# """

# from fastapi import APIRouter, Depends, HTTPException
# from sqlalchemy.orm import Session
# from models.connection import get_db
# from models.db_models import UserAccount, ChatThread
# from router.auth_router import get_current_user
# from handler.chat_handler import (
#     save_chat_message_handler,
#     get_or_create_active_thread_handler,
#     close_active_thread_handler,
#     get_thread_transcript_handler,   # <-- ADDED (needed by /history)
# )
# from typing import Optional
# from pydantic import BaseModel
# from chatbot.customer_agent import process_message
# # from chatbot.bot import process_messages

# router = APIRouter(prefix="/chat", tags=["Chatbot"])

# class Request(BaseModel):
#     message: str
#     thread_id: Optional[int] = None
#     conversation_id: Optional[str] = None

# @router.post("")
# async def chat_endpoint(
#     req: Request,
#     current_user: UserAccount = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Handle a chat message from an authenticated user.
#     """
#     message = req.message
#     if not message:
#         raise HTTPException(status_code=400, detail="Message is required")

#     if req.thread_id:
#         thread = (
#             db.query(ChatThread)
#             .filter_by(id=req.thread_id, user_id=current_user.id)
#             .first()
#         )
#         if not thread:
#             raise HTTPException(status_code=404, detail="Chat thread not found")
#     else:
#     # 1. Get or create active chat thread for the authenticated user
#          thread = get_or_create_active_thread_handler(
#         db=db,
#         user_id=current_user.id
#     )

#     # If specific thread_id was requested, validate and use it
#     if req.thread_id:
#         target_thread = db.query(ChatThread).filter_by(id=req.thread_id, user_id=current_user.id).first()
#         if target_thread:
#             thread = target_thread

#     # 2. Save incoming user message to database
#     save_chat_message_handler(
#         db=db,
#         user_id=current_user.id,
#         sender="user",
#         message_text=message,
#         thread_id=thread.id
#     )

#     # 3. Process the message through the agent
#     response = process_message(
#         message=message,
#         user_id=current_user.id,
#         thread_id=thread.id
#     )

#     # 4. Save assistant response to database
#     save_chat_message_handler(
#         db=db,
#         user_id=current_user.id,
#         sender="assistant",
#         message_text=response,
#         thread_id=thread.id
#     )

#     return {
#         "success": True,
#         "response": response,
#         "thread_id": thread.id,
#         "user_id": current_user.id
#     }


# # ---------------------------------------------------------------------------
# # ADDED: history endpoint used by the frontend chat widget
# # ---------------------------------------------------------------------------
# @router.get("/history")
# async def chat_history(
#      thread_id: Optional[int] = None,
#     current_user: UserAccount = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Messages of the CURRENT user's active thread only (filtered by user_id)."""
#     if thread_id:
#         thread = (
#             db.query(ChatThread)
#             .filter_by(id=thread_id, user_id=current_user.id)  # user_id keeps data isolated
#             .first()
#         )
#         if not thread or thread_id == "undefined":
#             raise HTTPException(status_code=404, detail="Chat thread not foun   d")
#     else:
#          thread = (
#         db.query(ChatThread)
#         .filter_by(user_id=current_user.id, status="ACTIVE")
#         .order_by(ChatThread.id.desc())
#         .first()
#     )
#          if not thread:
#                  return {"thread_id": None, "messages": []}
#     return {
#         "thread_id": thread.id,
#         "messages": get_thread_transcript_handler(db, current_user.id, thread.id),
#     }


# @router.post("/new")
# async def new_chat_endpoint(
#     current_user: UserAccount = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Closes the user's current ACTIVE chat thread (the '+ New Chat' action)
#     so they can start a clean conversation next time.
#     """
#     closed_thread_id = close_active_thread_handler(db=db, user_id=current_user.id)
    
#     new_thread = get_or_create_active_thread_handler(db=db, user_id=current_user.id)

    
#     return {
#         "success": True,
#         "message": "Active chat thread closed successfully.",
#         "closed_thread_id": closed_thread_id
#   }

# @router.get("/threads")
# async def get_user_threads(
#     current_user: UserAccount = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """Retrieve all chat threads for the authenticated user."""
#     threads = (
#         db.query(ChatThread)
#         .filter_by(user_id=current_user.id)
#         .order_by(ChatThread.updated_at.desc())
#         .all()
#     )
#     return [
#         {
#             "id": t.id,
#             "title": t.title,
#             "status": t.status,
#             "updated_at": t.updated_at
#         }
#         for t in threads
#     ]\




#!chatbot/router.py
"""Chat endpoints: /chat, /chat/history, /chat/new, /chat/threads (all isolated by user_id)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models.connection import get_db
from models.db_models import UserAccount, ChatThread
from router.auth_router import get_current_user
from handler.chat_handler import (
    save_chat_message_handler,
    get_or_create_active_thread_handler,
    close_active_thread_handler,
    get_thread_transcript_handler,
)
from chatbot.customer_agent import process_message

router = APIRouter(prefix="/chat", tags=["Chatbot"])


class ChatRequest(BaseModel):              # renamed: "Request" clashes with fastapi.Request
    message: str
    thread_id: Optional[int] = None
    conversation_id: Optional[str] = None


def _own_thread(db: Session, thread_id: int, user_id: int):
    return db.query(ChatThread).filter_by(id=thread_id, user_id=user_id).first()


# NOTE: plain `def`, not `async def`. process_message() blocks for seconds (LLM call);
# FastAPI runs plain `def` endpoints in a thread pool so other requests keep working.
@router.post("")
def chat_endpoint(
    req: ChatRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    if req.thread_id:
        thread = _own_thread(db, req.thread_id, current_user.id)
        if not thread:
            raise HTTPException(status_code=404, detail="Chat thread not found")
    else:
        thread = get_or_create_active_thread_handler(db=db, user_id=current_user.id)

    save_chat_message_handler(db=db, user_id=current_user.id, sender="user",
                              message_text=message, thread_id=thread.id)

    response = process_message(message=message, user_id=current_user.id, thread_id=thread.id)

    save_chat_message_handler(db=db, user_id=current_user.id, sender="assistant",
                              message_text=response, thread_id=thread.id)

    return {"success": True, "response": response,
            "thread_id": thread.id, "user_id": current_user.id}


@router.get("/history")
def chat_history(
    thread_id: Optional[int] = None,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if thread_id:
        thread = _own_thread(db, thread_id, current_user.id)
        if not thread:
            raise HTTPException(status_code=404, detail="Chat thread not found")
    else:
        thread = (
            db.query(ChatThread)
            .filter_by(user_id=current_user.id, status="ACTIVE")
            .order_by(ChatThread.updated_at.desc())      # same ordering as get_or_create
            .first()
        )
        if not thread:
            return {"thread_id": None, "messages": []}

    return {"thread_id": thread.id,
            "messages": get_thread_transcript_handler(db, current_user.id, thread.id)}


@router.post("/new")
def new_chat_endpoint(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Closes the active thread. The next message creates a fresh one (no empty threads)."""
    closed_id = close_active_thread_handler(db=db, user_id=current_user.id)
    return {"success": True, "closed_thread_id": closed_id}


@router.get("/threads")
def get_user_threads(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    threads = (
        db.query(ChatThread)
        .filter(ChatThread.user_id == current_user.id, ChatThread.messages.any())  # hide empty ones
        .order_by(ChatThread.updated_at.desc())
        .all()
    )
    return [{"id": t.id, "title": t.title, "status": t.status, "updated_at": t.updated_at}
            for t in threads]