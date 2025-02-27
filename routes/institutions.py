from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from dependencies import get_db
import models

router = APIRouter()

@router.post("/")
def add_institutions(name: str = Form(...), admin_name: str = Form(...), admin_password: str = Form(...), db: Session = Depends(get_db)):
    if admin_name != "admin" or admin_password != "admin":
        raise HTTPException(status_code=401, detail="Unauthorized")
    existing_institution = db.query(models.Institution).filter(models.Institution.name == name).first()
    if existing_institution:
        raise HTTPException(status_code=400, detail="Institution already exists")

    new_institution = models.Institution(name=name)
    db.add(new_institution)
    db.commit()
    db.refresh(new_institution)
    
    return {"message": "Institution added successfully", "institution": new_institution}

@router.get("/")
def get_institutions(db: Session = Depends(get_db)):
    print("Getting institutions")
    print(db.query(models.Institution).all())
    response = db.query(models.Institution).all()
    return response

# @router.get("/institutions/{institution_id}/instructors")
# def get_institution_instructors(institution_id: int, db: Session = Depends(get_db)):
#     instructors = db.query(models.User).filter(
#         models.User.institution_id == institution_id,
#         models.User.is_instructor.is_(True)
#     ).all()
#     return instructors
