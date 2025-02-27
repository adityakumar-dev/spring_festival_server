from datetime import datetime, timedelta
import secrets
from fastapi import HTTPException, Header
from sqlalchemy.orm import Session
import models

class SecurityHandler:
    def __init__(self):
        self.API_KEY_EXPIRY_HOURS = 24  # API key expires after 24 hours

    def generate_api_key(self) -> str:
        """Generate a unique API key"""
        return secrets.token_urlsafe(32)

    def login_user(self, db: Session, app_user: models.AppUsers) -> dict:
        """Create a new API key on login"""
        api_key = self.generate_api_key()
        expiry = datetime.utcnow() + timedelta(hours=self.API_KEY_EXPIRY_HOURS)
        
        # Update user's API key and expiry
        app_user.api_key = api_key
        app_user.api_key_expiry = expiry
        db.commit()
        
        return {
            "api_key": api_key,
            "expires_at": expiry.isoformat()
        }

    def logout_user(self, db: Session, app_user: models.AppUsers) -> bool:
        """Remove API key on logout"""
        try:
            app_user.api_key = None
            app_user.api_key_expiry = None
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Logout failed: {str(e)}")

    def verify_api_key(self, db: Session, api_key: str) -> models.AppUsers:
        """Verify API key and check expiry"""
        if not api_key:
            raise HTTPException(status_code=401, detail="API key is required")
            
        app_user = db.query(models.AppUsers).filter(
            models.AppUsers.api_key == api_key
        ).first()
        
        if not app_user:
            raise HTTPException(status_code=401, detail="Invalid API key")
            
        if not app_user.api_key_expiry or app_user.api_key_expiry < datetime.utcnow():
            # Clear expired key
            app_user.api_key = None
            app_user.api_key_expiry = None
            db.commit()
            raise HTTPException(status_code=401, detail="API key expired. Please login again")
            
        return app_user

security_handler = SecurityHandler() 