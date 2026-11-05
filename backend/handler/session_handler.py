#!handler/session_handler.py
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from models.db_models import UserAccount, UserSession

SESSION_EXPIRY_DAYS = 7

def verify_and_clean_user_session(db: Session, session_token: Optional[str]) -> Optional[UserAccount]:
    """
    Validates user session token, checks 7-day expiration inactivity,
    and returns the UserAccount if valid. Purges token if expired.
    """
    if not session_token:
        return None
    
    session = db.query(UserSession).filter_by(session_token_hash=session_token).first()
    if not session:
        return None
    
    now = datetime.now(timezone.utc)
    created_at = session.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
        
    if now - created_at > timedelta(days=SESSION_EXPIRY_DAYS):
        db.delete(session)
        db.commit()
        return None
    
    return db.query(UserAccount).filter_by(id=session.user_id).first()