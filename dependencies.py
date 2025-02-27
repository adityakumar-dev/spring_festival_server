from database import SessionLocal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi import Depends, HTTPException, status, Header

# from jose import JWTError, jwt
from datetime import datetime, timezone
# from config import settings
from typing import Optional
import models
from utils.security import security_handler



def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def verify_app_user(
    api_key: str = Header(..., description="API key for authentication"),
    db: Session = Depends(get_db)
):
    return security_handler.verify_api_key(db, api_key)

async def get_current_app_user(
    api_key: str = Header(None, description="API key required for authentication"),
    db: Session = Depends(get_db)
):
    if not api_key:
        raise HTTPException(status_code=401, detail="API key is required")
    return security_handler.verify_api_key(db, api_key)