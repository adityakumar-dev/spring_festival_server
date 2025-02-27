from datetime import datetime
from sqlalchemy.orm import Session
from models import AppUsers

def cleanup_expired_api_keys(db: Session):
    """Cleanup expired API keys periodically"""
    try:
        db.query(AppUsers).filter(
            AppUsers.api_key_expiry < datetime.utcnow()
        ).update({
            AppUsers.api_key: None,
            AppUsers.api_key_expiry: None
        })
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error cleaning up API keys: {str(e)}") 