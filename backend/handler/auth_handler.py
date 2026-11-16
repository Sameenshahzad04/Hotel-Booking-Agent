#!handler/auth_handler.py
import uuid
from typing import Optional
from sqlalchemy.orm import Session
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from models.db_models import UserAccount, UserSession

# Initialize Argon2 Password Hasher
ph = PasswordHasher()

def register_user_handler(
    db: Session,
    email: str,
    password: str,
    full_name: str,
    phone: Optional[str] = None,
    age: Optional[int] = None,
    gender: Optional[str] = None,
    address: Optional[str] = None
) -> UserAccount:
    """Handles database persistence for new user registration using Argon2."""
    clean_email = email.lower().strip()
    existing = db.query(UserAccount).filter_by(email=clean_email).first()
    if existing:
        raise ValueError("Email is already registered.")
    
    hashed_password = ph.hash(password)
    
    user = UserAccount(
        email=clean_email,
        hashed_password=hashed_password,
        full_name=full_name,
        phone=phone,
        age=age,
        gender=gender,
        address=address
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def authenticate_user_handler(db: Session, email: str, password: str) -> tuple[str, UserAccount]:
    """Authenticates credentials, creates a user session, and returns the session token and user object."""
    clean_email = email.lower().strip()
    user = db.query(UserAccount).filter_by(email=clean_email).first()
    
    if not user:
        raise ValueError("Invalid email or password.")
        
    try:
        ph.verify(user.hashed_password, password)
    except VerifyMismatchError:
        raise ValueError("Invalid email or password.")
    
    token = f"usr-{uuid.uuid4().hex}"
    user_session = UserSession(user_id=user.id, session_token_hash=token)
    db.add(user_session)
    db.commit()
    return token, user

def logout_user_handler(db: Session, session_token: Optional[str]) -> bool:
    """
    Immediately expires/terminates an active user session token 
    by deleting it from the database upon logout.
    """
    if not session_token:
        return False
    
    session = db.query(UserSession).filter_by(session_token_hash=session_token).first()
    if session:
        db.delete(session)
        db.commit()
        return True
    return False

def get_user_by_session_handler(db: Session, session_token: Optional[str]) -> Optional[UserAccount]:
    """Validates session token and returns the corresponding UserAccount."""
    if not session_token:
        return None
    
    session = db.query(UserSession).filter_by(session_token_hash=session_token).first()
    if not session:
        return None
    
    return db.query(UserAccount).filter_by(id=session.user_id).first()

ALLOWED_PROFILE_FIELDS = {"full_name", "phone", "age", "gender", "address"}

def update_user_profile_handler(db: Session, user: UserAccount, fields: dict) -> UserAccount:
    """Updates only the fields the client sent. A value of None clears an optional field."""
    for key, value in fields.items():
        if key not in ALLOWED_PROFILE_FIELDS:
            continue
        if key == "full_name" and (value is None or not str(value).strip()):
            raise ValueError("Full name cannot be empty.")
        if isinstance(value, str):
            value = value.strip() or None if key != "full_name" else value.strip()
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user

def change_user_password_handler(db: Session, user: UserAccount, old_password: str, new_password: str) -> None:
    """Verifies old password and commits the hashed new password."""
    try:
        ph.verify(user.hashed_password, old_password)
    except VerifyMismatchError:
        raise ValueError("Incorrect current password.")
    
    user.hashed_password = ph.hash(new_password)
    db.commit()

