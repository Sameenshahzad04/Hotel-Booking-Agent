from sqlalchemy.orm import Session
from models.db_models import HotelPolicy
from typing import Dict, Any

def get_all_policies(db: Session) -> Dict[str, Any]:
    policies = db.query(HotelPolicy).all()
    return {p.key: p.data for p in policies}

def upsert_policy(db: Session, key: str, data: Dict[str, Any]) -> Dict[str, Any]:
    policy = db.query(HotelPolicy).filter_by(key=key).first()
    if policy:
        policy.data = data
    else:
        policy = HotelPolicy(key=key, data=data)
        db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy.data