import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from dependencies import get_db
import models
from firebase_controller import firebase_controller
from sqlalchemy import func
from datetime import datetime
from fastapi import Form
router = APIRouter()

@router.post("/scan_qr")
def scan_qr(
    user_id: int = Form(...),
    app_user_id: int = Form(None),
    app_user_email: str = Form(None),
    is_group_entry: bool = Form(False),
    is_bypass: bool = Form(False),
    bypass_reason: str = Form(None),
    db: Session = Depends(get_db)
):
    try:
        # Validate user
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Validate app user
        if not app_user_id and not app_user_email:
            raise HTTPException(status_code=400, detail="App user email or id is required")
        
        app_user = db.query(models.AppUsers).filter(
            models.AppUsers.user_id == app_user_id if app_user_id 
            else models.AppUsers.email == app_user_email
        ).first()
        if not app_user:
            raise HTTPException(status_code=404, detail="App user not found")

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
                    raise HTTPException(status_code=400, detail="Previous entry not closed. Please record departure first.")
            
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
    app_user_id: int = Form(None),
    app_user_email: str = Form(None),
    db: Session = Depends(get_db)
):
    try:
        # Validate app user
        if not app_user_id and not app_user_email:
            raise HTTPException(status_code=400, detail="App user email or id is required")
        
        app_user = db.query(models.AppUsers).filter(
            models.AppUsers.user_id == app_user_id if app_user_id 
            else models.AppUsers.email == app_user_email
        ).first()
        if not app_user:
            raise HTTPException(status_code=404, detail="App user not found")

        # Validate user
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

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
        firebase_controller.log_server_activity("INFO", f"Departure recorded for user_id: {user_id}")
        
        return {
            "message": "Check-out successful",
            "user_id": user_id,
            "departure_time": departure_time.isoformat(),
            "duration": str(duration),
            "entry_type": latest_entry.get('entry_type', 'normal')
        }
        
    except Exception as e:
        db.rollback()
        firebase_controller.log_server_activity("ERROR", f"Error processing departure for user_id: {user_id} - {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# # Scan QR Code (Insert Entry)
# @router.post("/qr_scans/verify")
# def scan_qr(user_id: int, db: Session = Depends(get_db)):
#     try:
#         user = db.query(models.User).filter(models.User.user_id == user_id).first()
#         if user is None:
#             return {"error": "User not found"}
        
#         # Check if user already has an arrival time for today
#         from datetime import datetime
#         today = datetime.now().date()
#         existing_scan = db.query(models.QRScan).filter(
#             models.QRScan.user_id == user_id,
#             db.func.date(models.QRScan.arrival_time) == today
#         ).first()
        
#         if existing_scan:
#             return {"error": "User already checked in today"}
        
#         # Create new scan entry
#         scan = models.QRScan(user_id=user_id)
#         db.add(scan)
#         db.commit()
        
#         # Return before refresh to avoid potential issues
#         return {
#             "message": "Check-in successful",
#             "user_id": user_id,
#             "arrival_time": scan.arrival_time
#         }
#     except Exception as e:
#         db.rollback()  # Rollback any failed transaction
#         print(f"Error in scan_qr: {str(e)}")  # Log the error
#         return {"error": f"Internal server error: {str(e)}"}

# Get QR Scan History
# @router.get("/qr_scans/{user_id}")
# def get_qr_history(user_id: int, db: Session = Depends(get_db)):
#     return db.query(models.QRScan).filter(models.QRScan.user_id == user_id).all()

