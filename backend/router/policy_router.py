from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import Dict, Any
from models.connection import get_db
from handler.policy_handler import get_all_policies, upsert_policy

router = APIRouter(prefix="/policies", tags=["Hotel Policies"])

@router.get("")
def list_policies(db: Session = Depends(get_db)):
    """Retrieve all current hotel policies for agents, UI, and front desk."""
    return {"policies": get_all_policies(db)}

@router.put("/{key}")
def update_policy(
    key: str,
    data: Dict[str, Any] = Body(..., description="JSON policy payload (e.g. child, pet)"),
    db: Session = Depends(get_db)
):
    """Add or update policy JSON for a specific key and make it accessible to RAG/Agents."""
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Policy data must be a JSON object.")
    updated = upsert_policy(db, key, data)
    return {"success": True, "key": key, "policy": updated}