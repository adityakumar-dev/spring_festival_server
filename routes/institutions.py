from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from dependencies import get_db
import models

router = APIRouter()

@router.post("/")
def add_institutions(
    name: str = Form(...),
    count: int = Form(...),
    db: Session = Depends(get_db)
):
    # Debug: Print incoming data
    print(f"Adding institution with name: {name} and count: {count}")

    # Check if the institution already exists
    existing_institution = db.query(models.Institution).filter(models.Institution.name == name).first()
    if existing_institution:
        raise HTTPException(status_code=400, detail="Institution already exists")

    # Create a new institution
    new_institution = models.Institution(name=name, count=str(count))
    
    # Add and commit the new institution to the database
    db.add(new_institution)
    try:
        db.commit()
        db.refresh(new_institution)
    except Exception as e:
        db.rollback()  # Rollback in case of error
        print(f"Error adding institution: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to add institution")

    return {
        "message": "Institution added successfully",
        "institution": {
            "id": new_institution.institution_id,
            "name": new_institution.name,
            "count": new_institution.count
        }
    }
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
