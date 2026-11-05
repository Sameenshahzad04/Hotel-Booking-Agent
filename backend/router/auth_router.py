#!router/auth_router.py
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field
from models.connection import get_db
from models.db_models import UserAccount
from handler.auth_handler import (
    register_user_handler,
    authenticate_user_handler,
    logout_user_handler,
    get_user_by_session_handler,
    update_user_profile_handler,
    change_user_password_handler
)

router = APIRouter(prefix="/auth", tags=["Authentication & User Management"])

GenderType = Literal["male", "female"]

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=15)
    full_name: str
    phone: Optional[str] = Field(None, pattern=r"^\d{11}$")
    age: Optional[int] = Field(None, ge=12, le=150)
    gender: Optional[GenderType] = None
    address: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = Field(None, pattern=r"^\d{11}$")
    age: Optional[int] = Field(None, ge=12, le=150)
    gender: Optional[GenderType] = None
    address: Optional[str] = None

class PasswordChangeRequest(BaseModel):
    old_password: str = Field(..., min_length=8, max_length=15)
    new_password: str = Field(..., min_length=8, max_length=15)

def get_current_user(
    x_session_token: Optional[str] = Header(None, alias="X-Session-Token"),
    db: Session = Depends(get_db)
) -> UserAccount:
    """Validates session token and returns current authenticated user."""
    if not x_session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication token missing.")
    
    user = get_user_by_session_handler(db, x_session_token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session token.")
    return user

@router.post("/register")
def register_user(req: RegisterRequest, db: Session = Depends(get_db)):
    """Registers a new user account."""
    try:
        user = register_user_handler(
            db=db,
            email=req.email,
            password=req.password,
            full_name=req.full_name,
            phone=req.phone,
            age=req.age,
            gender=req.gender,
            address=req.address
        )
        return {"success": True, "message": "Account registered successfully.", "user_id": user.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login")
def login_user(req: LoginRequest, db: Session = Depends(get_db)):
    """Authenticates user and creates a new multi-device session token."""
    try:
        token, user = authenticate_user_handler(db, req.email, req.password)
        return {
            "success": True,
            "session_token": token,
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
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.post("/logout")
def logout_user(
    x_session_token: Optional[str] = Header(None, alias="X-Session-Token"),
    db: Session = Depends(get_db)
):
    """
    Terminates and completely destroys the active session token in the database, 
    ensuring it is fully expired and cannot be reused.
    """
    logout_user_handler(db, x_session_token)
    return {"success": True, "message": "Logged out successfully. Session expired."}

@router.get("/profile")
def get_profile(current_user: UserAccount = Depends(get_current_user)):
    """Retrieves account details."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "phone": current_user.phone,
        "age": current_user.age,
        "gender": current_user.gender,
        "address": current_user.address
    }

@router.put("/profile")
def update_profile(
    req: ProfileUpdateRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Updates user personal details (phone, age, gender, address, etc.)."""
    update_user_profile_handler(
        db=db,
        user=current_user,
        full_name=req.full_name,
        phone=req.phone,
        age=req.age,
        gender=req.gender,
        address=req.address
    )
    return {"success": True, "message": "Profile updated successfully."}

@router.post("/change-password")
def change_password(
    req: PasswordChangeRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Allows authenticated user to change their password."""
    try:
        change_user_password_handler(db, current_user, req.old_password, req.new_password)
        return {"success": True, "message": "Password changed successfully."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))