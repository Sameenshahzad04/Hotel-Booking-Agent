from sqlalchemy.orm import Session
from models.db_models import GuestSession
from util.security_util import generate_session_token, hash_session_token

def get_or_create_guest_session(db: Session, raw_token: str | None = None) -> tuple[GuestSession, str]:
    """
    Validates an existing guest session token or provisions a new anonymous session.
    """
    if raw_token:
        token_hash = hash_session_token(raw_token)
        session = db.query(GuestSession).filter_by(session_token_hash=token_hash).first()
        if session:
            return session, raw_token

    new_raw_token = generate_session_token()
    token_hash = hash_session_token(new_raw_token)
    new_session = GuestSession(session_token_hash=token_hash)
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return new_session, new_raw_token
