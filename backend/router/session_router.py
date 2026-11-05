from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from models.connection import get_db
from models.db_models import UserAccount, UserSession
from handler.session_handler import verify_and_clean_user_session

router = APIRouter(prefix="/sessions", tags=["Sessions"])

@router.get("/verify")
def verify_session(
    x_session_token: Optional[str] = Header(None, alias="X-Session-Token"),
    db: Session = Depends(get_db)
):
    """
    Verifies if the current user session token is valid and unexpired,
    returning user account details for automatic frontend session restoration.
    """
    if not x_session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Session token missing."
        )
    
    user = verify_and_clean_user_session(db, x_session_token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid or expired session token."
        )
    
    session = db.query(UserSession).filter_by(session_token_hash=x_session_token).first()

    return {
        "success": True,
        "session_id": session.id if session else None,
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "phone": user.phone,
            "age": user.age,
            "gender": user.gender,
            "address": user.address
        }
    }