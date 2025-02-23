import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from dependencies import get_db
import models
from firebase_controller import firebase_controller
from sqlalchemy import func
from datetime import datetime
router = APIRouter()

@router.post("/scan_qr")
def scan_qr(user_id: int, db: Session = Depends(get_db)):
    try:
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if user is None:
            return {"error": "User not found"}
        
        # Check if user already has an arrival time for today
        today = datetime.now().date()
        existing_scan = db.query(models.QRScan).filter(
            models.QRScan.user_id == user_id,
            func.date(models.QRScan.arrival_time) == today  # Fix applied here
        ).first()
        
        if existing_scan:
            return {"error": "User already checked in today"}
        
        # Create new scan entry
        scan = models.QRScan(user_id=user_id)
        db.add(scan)
        db.commit()
        firebase_controller.log_qr_scan(user_id, user.name, True, "Successful QR scan")

        # Return before refresh to avoid potential issues
        return {
            "message": "Check-in successful",
            "user_id": user_id,
            "arrival_time": scan.arrival_time
        }
    except Exception as e:
        db.rollback()  # Rollback any failed transaction
        print(f"Error in scan_qr: {str(e)}")  # Log the error
        return {"error": f"Internal server error: {str(e)}"}# Get QR Code Image
@router.get("/{user_id}")
def get_qr_code(user_id: int):
    qr_path = f"qrs/qr_code_{user_id}.png"

    if not os.path.exists(qr_path):
        return {"error": "QR code not found"}

    return FileResponse(qr_path, media_type="image/png")



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
@router.get("/qr_scans/{user_id}")
def get_qr_history(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.QRScan).filter(models.QRScan.user_id == user_id).all()

