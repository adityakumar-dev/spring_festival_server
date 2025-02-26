from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile    
from sqlalchemy.orm import Session
from dependencies import get_db
from face_auth import is_face_match
import models
import os
from firebase_controller import firebase_controller
from datetime import datetime

router = APIRouter()
UPLOAD_DIR = "uploads"

@router.post("/face_recognition/verify")
async def verify_face(
    user_id: int = Form(...),
    is_group_entry: bool = Form(False),
    app_user_id: int = Form(None),   
    app_user_email: str = Form(None),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    try:
        os.makedirs("temp_images", exist_ok=True)
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user:
            firebase_controller.log_face_verification(user_id, "Unknown", False)
            raise HTTPException(status_code=404, detail="User not found")
        
        if is_group_entry and not user.is_instructor:
            return {"error": "User is not an instructor"}

        if app_user_email is None and app_user_id is None:
            raise HTTPException(status_code=400, detail="App user email or id is required")
        
        if app_user_email:
            app_user = db.query(models.AppUsers).filter(models.AppUsers.email == app_user_email).first()
            if not app_user:
                raise HTTPException(status_code=404, detail="App user not found")
            
        if app_user_id:
            app_user = db.query(models.AppUsers).filter(models.AppUsers.user_id == app_user_id).first()
            if not app_user:
                raise HTTPException(status_code=404, detail="App user not found")
        
        print(f"Found user with image_path: {user.image_path}")
        stored_image_path = user.image_path
        
        if not stored_image_path or not os.path.exists(stored_image_path):
            print(f"Stored image not found at path: {stored_image_path}")
            return {"error": "Stored image not found"}
        
        temp_image_path = os.path.join("temp_images", f"temp_{uuid4().hex}_{image.filename}")
        try:
            print(f"Saving temporary image to: {temp_image_path}")
            await image.seek(0)
            
            with open(temp_image_path, "wb") as buffer:
                content = await image.read()
                buffer.write(content)
            
            print("Calling face_match function")
            is_match = is_face_match(stored_image_path, temp_image_path)
            
            # Log the verification result
            firebase_controller.log_face_verification(user_id, user.name, bool(is_match))
            
            if is_match:
                current_time = datetime.utcnow()
                # Check for existing record for today
                existing_record = db.query(models.FinalRecords).filter(
                    models.FinalRecords.user_id == user_id,
                    models.FinalRecords.entry_date == current_time.date()
                ).first()

                if existing_record:
                    # Update the latest time_log entry with face verification
                    if existing_record.time_logs and existing_record.time_logs[-1].get('departure') is None:
                        latest_entry = existing_record.time_logs[-1]
                        latest_entry.update({
                            "face_verified": True,
                            "face_verification_time": current_time.isoformat(),
                            "face_image_path": temp_image_path
                        })
                        existing_record.time_logs[-1] = latest_entry
                        
                        # Update the database with modified time_logs
                        db.query(models.FinalRecords).filter(
                            models.FinalRecords.user_id == user_id,
                            models.FinalRecords.entry_date == current_time.date()
                        ).update({
                            "time_logs": existing_record.time_logs
                        })
                else:
                    # Create new record with face verification
                    new_record = models.FinalRecords(
                        user_id=user_id,
                        entry_date=current_time.date(),
                        face_image_path=temp_image_path,
                        app_user_id=app_user_id,
                        time_logs=[{
                            "arrival": current_time.isoformat(),
                            "departure": None,
                            "duration": None,
                            "entry_type": "normal",
                            "face_verified": True,
                            "face_verification_time": current_time.isoformat(),
                            "face_image_path": temp_image_path
                        }]
                    )
                    db.add(new_record)

                if is_group_entry and user.is_instructor:
                    # Handle group entry face verification
                    students = db.query(models.User).filter(
                        models.User.is_student == True,
                        models.User.institution_id == user.institution_id
                    ).all()
                    
                    for student in students:
                        student_record = db.query(models.FinalRecords).filter(
                            models.FinalRecords.user_id == student.user_id,
                            models.FinalRecords.entry_date == current_time.date()
                        ).first()
                        
                        if student_record and student_record.time_logs:
                            latest_entry = student_record.time_logs[-1]
                            if latest_entry.get('departure') is None:
                                latest_entry.update({
                                    "face_verified": True,
                                    "face_verification_time": current_time.isoformat(),
                                    "verified_by_instructor": user.user_id
                                })
                                student_record.time_logs[-1] = latest_entry
                                
                                # Update the database with modified time_logs for each student
                                db.query(models.FinalRecords).filter(
                                    models.FinalRecords.user_id == student.user_id,
                                    models.FinalRecords.entry_date == current_time.date()
                                ).update({
                                    "time_logs": student_record.time_logs
                                })

                db.commit()
                firebase_controller.log_success(user_id, user.name, "Face matched")
                return {
                    "status": True, 
                    "message": "Face matched",
                    "verification_time": current_time.isoformat()
                }
            else:
                firebase_controller.log_error(user_id, user.name, "Face did not match")
                raise HTTPException(status_code=400, detail="Face did not match")
        
        finally:
            print("face recognition route finished")
                
    except Exception as e:
        firebase_controller.log_face_verification(user_id, user.name if user else "Unknown", False)
        raise HTTPException(status_code=500, detail=str(e))

