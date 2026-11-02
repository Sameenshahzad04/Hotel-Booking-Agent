from typing import Optional
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from models.connection import get_db
from models.db_models import GuestSession
from handler.session_handler import get_or_create_guest_session

router = APIRouter(prefix="/sessions", tags=["Sessions"])

def get_current_session(
    x_session_token: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> tuple[GuestSession, str]:
    return get_or_create_guest_session(db, raw_token=x_session_token)

@router.post("")
def create_or_restore_session(
    session_data: tuple[GuestSession, str] = Depends(get_current_session)
):
    """Issues or validates an anonymous guest session token."""
    session, token = session_data
    return {
        "session_id": session.id,
        "session_token": token,
        "created_at": session.created_at
    }
