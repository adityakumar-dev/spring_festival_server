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
    api_key: str = Header(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    try:
        app_user = SecurityHandler().verify_api_key(db, api_key)

        os.makedirs("temp_images", exist_ok=True)
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user:
            # firebase_controller.log_face_verification(user_id, "Unknown", False)
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
            # firebase_controller.log_face_verification(user_id, user.name, is_match)
            
            if is_match:
                current_time = datetime.utcnow()
                existing_record = db.query(models.FinalRecords).filter(
                    models.FinalRecords.user_id == user_id,
                    models.FinalRecords.entry_date == current_time.date()
                ).first()

                if existing_record:
                    # Ensure `time_logs` is mutable
                    updated_time_logs = existing_record.time_logs.copy() if existing_record.time_logs else []
                    
                    if updated_time_logs:
                        latest_entry = updated_time_logs[-1]
                    else:
                        latest_entry = {
                            "arrival": current_time.isoformat(),
                            "departure": None,
                            "duration": None,
                            "entry_type": "normal",
                            "face_verified": True,
                            "face_verification_time": current_time.isoformat(),
                            "face_image_path": temp_image_path,
                            "verified_by": app_user.user_id
                        }
                        updated_time_logs.append(latest_entry)

                    # Update latest entry
                    latest_entry["face_verified"] = True
                    latest_entry["face_verification_time"] = current_time.isoformat()
                    latest_entry["face_image_path"] = temp_image_path
                    latest_entry["verified_by"] = app_user.user_id

                    # Apply changes
                    existing_record.time_logs = updated_time_logs
                    existing_record.verified_by = app_user.user_id
                    db.flush()
                    db.commit()
                else:
                    # Create a new record if none exists for today
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
                            "verified_by": app_user.user_id
                        }]
                    )
                    db.add(new_record)
                
                db.commit()
                
                return {
                    "status": True, 
                    "message": "Face matched",
                    "verification_time": current_time.isoformat()
                }
            
            else:
                print("Face not matched")
                raise HTTPException(status_code=400, detail="Face did not match")
        
        finally:
            print("Face recognition route finished")
            # if os.path.exists(temp_image_path):
            #     os.remove(temp_image_path)  # Clean up temporary file
                
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
