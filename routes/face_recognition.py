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
import json

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
                            "verified_by": app_user.user_id
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
                            "verified_by": app_user.user_id
                        }]
                    )
                    db.add(new_record)
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
            # Clean up temporary file
           
            print("face recognition route finished")
                
    except Exception as e:
        # Only log if we haven't already logged the verification
        if 'user' in locals() and user:
            firebase_controller.log_face_verification(user_id, user.name, False)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/face_recognition/group_entry")
async def group_entry(
    user_id: int = Form(...),
    api_key: str = Header(...),
    student_ids: str = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    try:
        app_user = SecurityHandler().verify_api_key(db, api_key)
        
        # Parse the JSON string to get list of student IDs
        try:
            student_ids = json.loads(student_ids)  # Parse the JSON string
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid student_ids format")

        # Rest of validation
        if not isinstance(student_ids, list):
            raise HTTPException(status_code=400, detail="student_ids must be an array")
        
        # Verify instructor
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if not user.is_instructor:
            raise HTTPException(status_code=403, detail="Only instructors can perform group entry")
        
        if not user.institution_id:
            raise HTTPException(status_code=400, detail="Instructor must be associated with an institution")
        
        # Validate student IDs - Remove this line since student_ids are already integers
        # student_ids = [int(id) for id in student_ids]
        students = []
        for student_id in student_ids:
            student = db.query(models.User).filter(
                models.User.user_id == student_id,
                models.User.institution_id == user.institution_id
            ).first()
            if not student:
                raise HTTPException(status_code=404, detail=f"Student with ID {student_id} not found or not in same institution")
            students.append(student)

        # Save temporary image for face verification
        os.makedirs("temp_images", exist_ok=True)
        temp_image_path = os.path.join("temp_images", f"temp_{uuid4().hex}_{image.filename}")
        await image.seek(0)
        with open(temp_image_path, "wb") as buffer:
            content = await image.read()
            buffer.write(content)
            
        # Process instructor face verification
        is_match = is_face_match(user.image_path, temp_image_path)
        if not is_match:
            firebase_controller.log_error(user_id, user.name, "Instructor face did not match")
            raise HTTPException(status_code=400, detail="Instructor face did not match")
        
        current_time = datetime.utcnow()
        
        # Create instructor record
        instructor_record = models.FinalRecords(
            user_id=user_id,
            entry_date=current_time.date(),
            face_image_path=temp_image_path,
            app_user_id=app_user.user_id,
            time_logs=[{
                "arrival": current_time.isoformat(),
                "departure": None,
                "duration": None,
                "entry_type": "group_entry",
                "face_verified": True,
                "face_verification_time": current_time.isoformat(),
                "face_image_path": temp_image_path
            }]
        )
        db.add(instructor_record)

        # Create records for all students
        for student in students:
            student_record = models.FinalRecords(
                user_id=student.user_id,
                entry_date=current_time.date(),
                app_user_id=app_user.user_id,
                time_logs=[{
                    "arrival": current_time.isoformat(),
                    "departure": None,
                    "duration": None,
                    "entry_type": "group_entry",
                    "face_verified": True,
                    "face_verification_time": current_time.isoformat(),
                    "verified_by_instructor": user.user_id
                }]
            )
            db.add(student_record)

        db.commit()
        firebase_controller.log_success(user_id, user.name, f"Group entry successful for {len(students)} students")
        
        return {
            "status": True,
            "message": "Group entry successful",
            "instructor_verified": True,
            "students_count": len(students),
            "verification_time": current_time.isoformat()
        }
                
    except Exception as e:
        firebase_controller.log_error(user_id, user.name if user else "Unknown", str(e))
        raise HTTPException(status_code=500, detail=str(e))

    # Add this debug print
    print(f"Setting entry_type in time_logs: {time_logs}")   