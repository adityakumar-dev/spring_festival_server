import os
import shutil
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from dependencies import get_db
import models

router = APIRouter()
UPLOAD_DIR = "uploads"

@router.post("/quick-register")
def quick_register(
    name: str = Form(...),
    email: str = Form(...),
    aadhar_number: str = Form(None),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # Check if email exists in both tables
    existing_user = db.query(models.User).filter(models.User.email == email).first()
    existing_quick = db.query(models.QuickRegister).filter(models.QuickRegister.email == email).first()
    
    if existing_user or existing_quick:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Check Aadhar if provided
    if aadhar_number:
        existing_aadhar_user = db.query(models.User).filter(models.User.aadhar_number == aadhar_number).first()
        existing_aadhar_quick = db.query(models.QuickRegister).filter(models.QuickRegister.aadhar_number == aadhar_number).first()
        if existing_aadhar_user or existing_aadhar_quick:
            raise HTTPException(status_code=400, detail="Aadhar number already registered")

    # Save image
    image_filename = f"quick_{uuid4().hex}_{image.filename}"
    image_path = os.path.join(UPLOAD_DIR, image_filename)
    
    with open(image_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)

    try:
        # Create quick register entry
        new_quick_register = models.QuickRegister(
            name=name,
            email=email,
            aadhar_number=aadhar_number,
            image_path=image_path
        )
        
        db.add(new_quick_register)
        db.commit()
        db.refresh(new_quick_register)

        return {
            "register_id": new_quick_register.register_id,
            "name": new_quick_register.name,
            "email": new_quick_register.email,
            "aadhar_number": new_quick_register.aadhar_number,
            "image_path": new_quick_register.image_path,
            "created_at": new_quick_register.created_at
        }

    except Exception as e:
        print(f"Error in quick registration: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error in quick registration: {str(e)}")
