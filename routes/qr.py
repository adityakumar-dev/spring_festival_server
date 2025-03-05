import os
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from dependencies import get_db, get_current_app_user
import models
from firebase_controller import firebase_controller
from sqlalchemy import func
from datetime import datetime
from fastapi import Form
from utils.security import SecurityHandler
from typing import List
from fastapi import UploadFile
from uuid import uuid4

router = APIRouter()
security_handler = SecurityHandler()

async def save_image(image: UploadFile) -> str:
    """Save uploaded image and return the path"""
    os.makedirs("temp_images", exist_ok=True)
    temp_image_path = os.path.join("temp_images", f"temp_{uuid4().hex}_{image.filename}")
    
    await image.seek(0)
    with open(temp_image_path, "wb") as buffer:
        content = await image.read()
        buffer.write(content)
    
    return temp_image_path
@router.post("/scan_qr")
def scan_qr(
    user_id: int = Form(...),
    is_group_entry: bool = Form(False),
    is_bypass: bool = Form(False),
    bypass_reason: str = Form(None),
    current_app_user: models.AppUsers = Depends(get_current_app_user),
    db: Session = Depends(get_db)
):
    try:
        # Use current_app_user instead of looking up app_user
        app_user_id = current_app_user.user_id
        app_user_email = current_app_user.email

        # print
        # Validate user
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Validate group entry
        if is_group_entry:
            if not user.is_instructor:
                raise HTTPException(status_code=403, detail="Only instructors can perform group entry")
            if not user.institution_id:
                raise HTTPException(status_code=400, detail="Instructor must be associated with an institution")

        def create_time_log_entry(entry_type="normal"):
            entry = {
                "arrival": datetime.utcnow().isoformat(),
                "departure": None,
                "duration": None,
                "entry_type": entry_type,
                "qr_verified": True,
                "qr_verification_time": datetime.utcnow().isoformat()
            }

            if entry_type == "bypass":
                entry["bypass_details"] = {
                    "reason": bypass_reason or "No reason provided",
                    "approved_by": app_user_id,
                    "approved_at": datetime.utcnow().isoformat()
                }

            return entry

        # Handle existing entry
        existing_entry = db.query(models.FinalRecords).filter(
            models.FinalRecords.user_id == user_id,
            models.FinalRecords.entry_date == datetime.utcnow().date()
        ).first()

        if existing_entry:
            # Initialize time_logs if None
            if existing_entry.time_logs is None:
                existing_entry.time_logs = []

            # Check if last entry has departure time
            should_add_new_entry = True
            if existing_entry.time_logs:
                last_entry = existing_entry.time_logs[-1]
                if last_entry.get('departure') is None:
                    should_add_new_entry = False

                    # Check if face verification is already done
                    if last_entry.get('face_verification_time') is None:
                        # Create a new dictionary instead of updating the existing one
                        updated_entry = {
                            'arrival': datetime.utcnow().isoformat(),
                            'departure': None,
                            'qr_verified': True,
                            'qr_verification_time': datetime.utcnow().isoformat(),
                            'face_verified': last_entry.get('face_verified', False),
                            'face_verification_time': last_entry.get('face_verification_time'),
                            'entry_type': "bypass" if is_bypass else "normal",
                        }

                        # Add bypass details only if it's a bypass entry
                        if is_bypass:
                            updated_entry['bypass_details'] = {
                                "reason": bypass_reason or "No reason provided",
                                "approved_by": app_user_id,
                                "approved_at": datetime.utcnow().isoformat()
                            }
                        else:
                            # Remove bypass details if it's not a bypass entry
                            updated_entry['bypass_details'] = None

                        # Update the database directly
                        new_time_logs = existing_entry.time_logs[:-1] + [updated_entry]
                        db.query(models.FinalRecords).filter(
                            models.FinalRecords.user_id == user_id,
                            models.FinalRecords.entry_date == datetime.utcnow().date()
                        ).update({
                            "time_logs": new_time_logs
                        }, synchronize_session=False)

                        try:
                            db.commit()
                            # Refresh to get updated data
                            db.refresh(existing_entry)
                        except Exception as e:
                            db.rollback()
                            raise HTTPException(
                                status_code=500, 
                                detail=f"Failed to update entry: {str(e)}"
                            )

                        return {
                            "status": "success",
                            "message": "QR verification successful. Arrival time updated.",
                            "entry_type": "bypass" if is_bypass else "normal",
                            "arrival_time": datetime.utcnow().isoformat(),
                            "bypass_reason": bypass_reason if is_bypass else None,
                            "updated_entry": updated_entry
                        }
                    else:
                        raise HTTPException(
                            status_code=400, 
                            detail="Face verification is already completed. Please use departure section."
                        )


            if should_add_new_entry:
                new_log = create_time_log_entry("bypass" if is_bypass else "normal")
                # Create a new list with existing logs plus new log
                updated_logs = existing_entry.time_logs + [new_log]
                # Update the entire time_logs field
                existing_entry.time_logs = updated_logs
                db.flush()  # Ensure the update is processed
        else:
            # Create new record
            new_record = models.FinalRecords(
                user_id=user_id,
                entry_date=datetime.utcnow().date(),
                time_logs=[create_time_log_entry("bypass" if is_bypass else "normal")],
                app_user_id=app_user_id
            )
            db.add(new_record)

            # Handle group entry
            if is_group_entry and not is_bypass:
                students = db.query(models.User).filter(
                    models.User.is_student == True,
                    models.User.institution_id == user.institution_id
                ).all()

                for student in students:
                    if student.user_id != user_id:  # Skip the instructor
                        student_record = models.FinalRecords(
                            user_id=student.user_id,
                            entry_date=datetime.utcnow().date(),
                            time_logs=[{
                                **create_time_log_entry("normal"),
                                "group_entry": True,
                                "instructor_id": user_id
                            }],
                            app_user_id=app_user_id
                        )
                        db.add(student_record)

        db.commit()
        firebase_controller.log_qr_scan(user_id, user.name, True, "Successful QR scan")

        return {
            "message": "Check-in successful",
            "user_id": user_id,
            "arrival_time": datetime.utcnow().isoformat(),
            "entry_type": "bypass" if is_bypass else "group" if is_group_entry else "normal",
            "bypass_reason": bypass_reason if is_bypass else None
        }

    except Exception as e:
        db.rollback()
        firebase_controller.log_server_activity("ERROR", f"Error processing QR scan for user_id: {user_id} - {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    
@router.post("/departure")
def departure(
    user_id: int = Form(...),
    current_app_user: models.AppUsers = Depends(get_current_app_user),
    db: Session = Depends(get_db)
):
    try:
        app_user_id = current_app_user.user_id
        
        # Validate user
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Process departure for instructor only
        if user.is_instructor and user.institution_id:
            # Try to process instructor's departure first
            successful_departures = []
            try:
                result = process_single_departure(user.user_id, app_user_id, db)
                successful_departures.append({
                    "user_id": user.user_id,
                    "name": "Instructor",
                    "departure_time": result["departure_time"]
                })
            except HTTPException as he:
                if he.status_code == 400 and "already has departure time" in str(he.detail):
                    # Instructor already checked out
                    pass
                elif he.status_code == 404:
                    # No active entry for instructor
                    pass
            
            if not successful_departures:
                raise HTTPException(
                    status_code=400, 
                    detail="No departures processed. Instructor has already checked out or has no active entries."
                )
            
            return {
                "message": "Instructor departure processed successfully",
                "instructor_id": user_id,
                "successful_departures": successful_departures
            }
        else:
            # Process single departure for non-instructor
            return process_single_departure(user_id, app_user_id, db)
        
    except Exception as e:
        db.rollback()
        firebase_controller.log_server_activity("ERROR", f"Error processing departure for user_id: {user_id} - {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

def process_single_departure(user_id: int, app_user_id: int, db: Session):
    # Get today's record for the user
    current_date = datetime.utcnow().date()
    user_record = db.query(models.FinalRecords).filter(
        models.FinalRecords.user_id == user_id,
        models.FinalRecords.entry_date == current_date
    ).first()
    
    if not user_record or not user_record.time_logs:
        raise HTTPException(status_code=404, detail="No active entry found for today")
    
    # Get the latest entry
    latest_entry = user_record.time_logs[-1]
    
    # Check if already departed
    if latest_entry.get('departure') is not None:
        raise HTTPException(status_code=400, detail="Latest entry already has departure time")
    
    # Calculate duration
    arrival_time = datetime.fromisoformat(latest_entry['arrival'])
    departure_time = datetime.utcnow()
    duration = departure_time - arrival_time
    
    # Update the latest entry
    latest_entry.update({
        'departure': departure_time.isoformat(),
        'duration': str(duration),
        'departure_verified_by': app_user_id,
        'departure_verification_time': departure_time.isoformat()
    })
    
    # Update the entire time_logs array
    user_record.time_logs[-1] = latest_entry
    
    # Update the record in database
    db.query(models.FinalRecords).filter(
        models.FinalRecords.user_id == user_id,
        models.FinalRecords.entry_date == current_date
    ).update({
        "time_logs": user_record.time_logs
    })
    
    db.commit()
    # firebase_controller.log_server_activity("INFO", f"Departure recorded for user_id: {user_id}")
    
    return {
        "message": "Check-out successful",
        "user_id": user_id,
        "departure_time": departure_time.isoformat(),
        "duration": str(duration),
        "entry_type": latest_entry.get('entry_type', 'normal')
    }
