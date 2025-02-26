from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Date, UniqueConstraint
from sqlalchemy.orm import relationship, backref
from datetime import datetime
from database import Base
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

class Institution(Base):
    __tablename__ = "institutions"
    
    institution_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # One-to-many relationship with users
    users = relationship("User", back_populates="institution")

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    unique_id_type = Column(String, unique=False, nullable=False)
    unique_id = Column(String, unique=False, nullable=False)
    image_path = Column(String)
    qr_code = Column(String, nullable=True)
    is_student = Column(Boolean, default=False)
    is_instructor = Column(Boolean, default=False)
    is_quick_register = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    institution_id = Column(Integer, ForeignKey("institutions.institution_id"), nullable=True)
    institution = relationship("Institution", back_populates="users")

    
    # Define the relationship to FinalRecords
    final_records = relationship("FinalRecords", back_populates="user")



class AppUsers(Base):
    __tablename__ = "app_users"

    user_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    email = Column(String, unique=False, index=True)
    
    unique_id_type = Column(String, unique=False, nullable=False)
    unique_id = Column(String, unique=False, nullable=False)
    image_path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class FinalRecords(Base):
    __tablename__ = "final_records"

    record_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), unique=False)
    entry_date = Column(Date, default=datetime.utcnow().date())
    # app_user_id = Column(Integer, ForeignKey("app_users.user_id"), nullable=True)
    
    # Time tracking using JSONB
    time_logs = Column(JSONB, default=list)  # Store array of time entries
    # Example structure:
    # [
    #   {
    #     "arrival": "2024-03-21T09:00:00",
    #     "departure": "2024-03-21T12:00:00",
    #     "duration": "3:00:00",
    #     "entry_type": "normal"  # or "bypass"
    #     "bypass_details": {      # only present if entry_type is "bypass"
    #         "reason": "Face not detected",
    #         "approved_by": "app_user_id"
    #     }
    #   }
    # ]
    
    # Verification timestamps and face image
    face_image_path = Column(String, nullable=True)
    app_user_id = Column(Integer, ForeignKey("app_users.user_id"), nullable=True)
    
    # Relationship
    user = relationship("User", back_populates="final_records")

    __table_args__ = (
        # Ensure unique combination of user_id, entry_date, and attempt_number
        UniqueConstraint('user_id', 'entry_date',  name='unique_daily_attempt'),
    )
