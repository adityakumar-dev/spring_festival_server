from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Header
from sqlalchemy.orm import Session
from dependencies import get_db
from face_auth import is_face_match
import models
import os
from firebase_controller import firebase_controller
from datetime import datetime
from utils.security import SecurityHandler

router = APIRouter()
UPLOAD_DIR = "uploads"
@router.post("/face_recognition/verify")
async def verify_face(
    user_id: int = Form(...),
    # count: int = Form(None),
    api_key: str = Header(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    try:
        app_user = SecurityHandler().verify_api_key(db, api_key)

        os.makedirs("temp_images", exist_ok=True)
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user:
            firebase_controller.log_face_verification(user_id, "Unknown", False)
            raise HTTPException(status_code=404, detail="User not found")
        
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
            # Single face verification check
            is_match = is_face_match(stored_image_path, temp_image_path)
            print(f"Face match result: {is_match}")
            
            # Log the verification result only once
            firebase_controller.log_face_verification(user_id, user.name, is_match)
            
            # If face match is successful
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
                            "face_image_path": temp_image_path,
                            "verified_by": app_user.user_id,
                            # "count": count if user.institute_id != None else None
                        })
                        existing_record.time_logs[-1] = latest_entry
                        
                        # Update the database with modified time_logs
                        db.query(models.FinalRecords).filter(
                            models.FinalRecords.user_id == user_id,
                            models.FinalRecords.entry_date == current_time.date()
                        ).update({
                            "time_logs": existing_record.time_logs,
                            "verified_by": app_user.user_id
                        })
                else:
                    # Create new record with face verification
                    new_record = models.FinalRecords(
                        user_id=user_id,
                        entry_date=current_time.date(),
                        face_image_path=temp_image_path,
                        app_user_id=app_user.user_id,
                        time_logs=[{
                            "arrival": current_time.isoformat(),
                            "departure": None,
                            "duration": None,
                            "entry_type": "normal",
                            "face_verified": True,
                            "face_verification_time": current_time.isoformat(),
                            "face_image_path": temp_image_path,
                            "verified_by": app_user.user_id,
                            # "count": count if user.institute_id != None else None
                        }]
                    )
                    db.add(new_record)

                # Get the count of users associated with the instructor's institution
                # instructor_count = db.query(models.Institution).filter(models.Institution.institution_id == user.institution_id).first().count or 0

                db.commit()
                
                # Return a successful response with instructor count
                return {
                    "status": True, 
                    "message": "Face matched",
                    "verification_time": current_time.isoformat(),
                    # "count": count if user.institute_id != None else None  # Include instructor count
                }

            # If face did not match
            else:
                print("Face not matched")
                raise HTTPException(status_code=400, detail="Face did not match")
        
        finally:
            print("Face recognition route finished")
                
    except Exception as e:
        if is_match:
            return {
                "status": True, 
                "message": "Face matched",
                "verification_time": current_time.isoformat(),
                # "count": count if user.institute_id != None else None  # Include instructor count
            }
        else:   
            db.rollback()
            firebase_controller.log_server_activity("ERROR", f"Error processing face verification for user_id: {user_id} - {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

