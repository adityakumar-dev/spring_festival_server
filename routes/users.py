from datetime import datetime
from email.header import Header
from fastapi import APIRouter, Depends, HTTPException, File, Form, UploadFile, Query, Header
from sqlalchemy.orm import Session
from dependencies import get_db, get_current_app_user
import models
from utils.file_handlers import save_upload_file, delete_file
from qr_generation import generate_qr_code
import base64
import os
from typing import Optional
import traceback
from fastapi.responses import JSONResponse, FileResponse
from firebase_controller import firebase_controller
from uuid import uuid4
from template_generator import VisitorCardGenerator
from utils.security import SecurityHandler
from fastapi import BackgroundTasks
from pathlib import Path
import mimetypes  # Add this import
from utils.email_handler import send_welcome_email_background

router = APIRouter()


@router.post("/check/email/{email}")
def check_email(email: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == email).first()
    return {"exists": bool(user)}

@router.post("/create")
def create_user(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    email: str = Form(...),
    image: UploadFile = File(...),
    user_type: str = Form(...),
    is_quick_register: bool = Form(False),
    unique_id_type: str = Form(...),
    unique_id: str = Form(...),
    api_key: str = Header(None),
    institution_id: int = Form(None),
    db: Session = Depends(get_db)
):
    try:
        if is_quick_register:
            if not api_key:
                raise HTTPException(status_code=401, detail="API key required for quick register")
            app_user = SecurityHandler().verify_api_key(db, api_key)
            if not app_user:
                raise HTTPException(status_code=401, detail="Invalid API key")
        # Structured logging of input parameters
        request_data = {
            "name": name,
            "email": email,
            "user_type": user_type,
            "is_quick_register": is_quick_register,
            "unique_id_type": unique_id_type,
            "unique_id": unique_id,
            "institution_id": institution_id,
            "image_filename": image.filename
        }
        print(f"Creating new user with data: {request_data}")
        if image.filename.split(".")[-1] not in ["jpg", "jpeg", "png", "webp"]:
            raise HTTPException(status_code=400, detail="Image must be a jpg, jpeg, png, or webp file")
        # Validation checks...
        existing_user = db.query(models.User).filter(
            (models.User.email == email) 
        ).first()
        
        if existing_user:
            firebase_controller.log_server_activity("ERROR", f"User already exists: {email}")
            raise HTTPException(status_code=400, detail="User already exists with this email")
        
        # Institution validation
        if user_type in ["student", "instructor"]:
            if institution_id is None:
                firebase_controller.log_server_activity("ERROR", "Institution ID is required for student/instructor")
                raise HTTPException(status_code=400, detail="Institution ID is required for student/instructor")
            
            institution = db.query(models.Institution).filter(models.Institution.institution_id == institution_id).first()
            if not institution:
                firebase_controller.log_server_activity("ERROR", f"Institution with ID {institution_id} does not exist")
                raise HTTPException(status_code=400, detail=f"Institution with ID {institution_id} does not exist")

        # Validate unique ID type
        if unique_id_type not in ["aadhar", "pan", "driving_license", "passport", "voter_id"]:
            raise HTTPException(status_code=400, detail="Invalid unique ID type")

        # Save image
        image_path = save_upload_file(image)
        print(f"Saved image at: {image_path}")

        # Create user
        new_user = models.User(
            name=name,
            email=email,
            image_path=image_path,
            is_student=(user_type == "student"),
            is_instructor=(user_type == "instructor"),
            institution_id=institution_id,
            is_quick_register=is_quick_register,
            unique_id_type=unique_id_type,
            unique_id=unique_id
        )
        
        db.add(new_user)
        db.flush()
        
        print(f"Generated user with ID: {new_user.user_id}")
        
        # Generate QR Code
        qr_path = generate_qr_code(new_user.user_id, new_user.name, new_user.email)
        new_user.qr_code = qr_path
        print(f"Generated QR code at: {qr_path}")
        
        db.commit()
        db.refresh(new_user)
        
        # Log user creation
        firebase_controller.log_user_creation(
            new_user.user_id,
            new_user.name,
            "instructor" if new_user.is_instructor else "student"
        )
        
        # After successful user creation, generate visitor card
        visitor_card_generator = VisitorCardGenerator()
        card_path = visitor_card_generator.create_visitor_card({
            "name": new_user.name,
            "email": new_user.email,
            "profile_image_path": str(Path(new_user.image_path)),
            "qr_code_path": new_user.qr_code,
            "user_id": str(new_user.user_id)
        })

        print(f"Successfully created user: {new_user.user_id}")

        # After successful user creation and visitor card generation
        send_welcome_email_background(
            background_tasks=background_tasks,
            user_email=new_user.email,
            user_name=new_user.name,
            qr_code_path=new_user.qr_code,
            visitor_card_path=card_path
        )

        return {
            "user_id": new_user.user_id,
            "name": new_user.name,
            "email": new_user.email,
            "qr_code": new_user.qr_code,
            "image_path": new_user.image_path,
            "visitor_card_path": card_path,
            "visitor_card": {
                "path": card_path,
                "url": f"/static/visitor_cards/{card_path.split('/')[-1]}" if card_path else None,
                "generated_at": str(datetime.now())
            },
            "is_student": new_user.is_student,
            "is_instructor": new_user.is_instructor,
            "institution_id": new_user.institution_id,
            "unique_id_type": new_user.unique_id_type,
            "unique_id": new_user.unique_id,
            "email_status": "sending_in_background"
        }

    except Exception as e:
        db.rollback()
        print(f"Error creating user: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error creating user: {str(e)}")

@router.get("/{user_id}")
def get_user(
    user_id: int,
    api_key: str = Header(None),
    db: Session = Depends(get_db)
):
    try:
        user = db.query(models.User).filter(
            models.User.user_id == user_id
        ).first()

        if user:
            # Get all records for the user
            records = db.query(models.FinalRecords).filter(
                models.FinalRecords.user_id == user_id
            ).order_by(models.FinalRecords.entry_date.desc()).all()

            # Process records into a more organized structure
            processed_records = []
            for record in records:
                entry_data = {
                    "record_id": record.record_id,
                    "entry_date": record.entry_date.isoformat(),
                    "face_image_path": record.face_image_path,
                    "app_user_id": record.app_user_id,
                    "entries": []
                }

                if record.time_logs:
                    for log in record.time_logs:
                        entry = {
                            "arrival": log.get("arrival"),
                            "departure": log.get("departure"),
                            "duration": log.get("duration"),
                            "entry_type": log.get("entry_type", "normal"),
                            "face_verified": log.get("face_verified", False),
                            "face_verification_time": log.get("face_verification_time"),
                            "face_image_path": log.get("face_image_path")
                        }

                        # Add bypass details if present
                        if log.get("bypass_details"):
                            entry["bypass_details"] = log["bypass_details"]

                        # Add instructor verification if present
                        if log.get("verified_by_instructor"):
                            entry["verified_by_instructor"] = log["verified_by_instructor"]

                        entry_data["entries"].append(entry)

                processed_records.append(entry_data)

            response_data = {
                "user": {
                    "user_id": user.user_id,
                    "name": user.name,
                    "email": user.email,
                    "is_instructor": user.is_instructor,
                    "institution": user.institution.name if user.institution else None,
                    "image_path": f"{user.image_path}",
                    "qr_code_path": f"{user.qr_code}",
                    "is_quick_register": user.is_quick_register,
                    "unique_id_type": user.unique_id_type,
                    "unique_id": user.unique_id,
                    "created_at": user.created_at.isoformat() if user.created_at else None,
                },
                "entry_records": processed_records,
                "summary": {
                    "total_days": len(processed_records),
                    "total_entries": sum(len(record["entries"]) for record in processed_records),
                    "normal_entries": sum(
                        len([e for e in record["entries"] if e["entry_type"] == "normal"])
                        for record in processed_records
                    ),
                    "bypass_entries": sum(
                        len([e for e in record["entries"] if e["entry_type"] == "bypass"])
                        for record in processed_records
                    ),
                    "face_verified_entries": sum(
                        len([e for e in record["entries"] if e["face_verified"]])
                        for record in processed_records
                    )
                },
                "image_base64": None,
                "qr_base64": None
            }

            # Add base64 encoded images
            try:
                if user.qr_code and os.path.exists(user.qr_code):
                    with open(user.qr_code, "rb") as qr_file:
                        qr_data = base64.b64encode(qr_file.read()).decode()
                        response_data["qr_base64"] = f"data:image/png;base64,{qr_data}"
            except Exception as qr_error:
                print(f"Error processing QR code: {str(qr_error)}")

            try:
                if user.image_path and os.path.exists(user.image_path):
                    with open(user.image_path, "rb") as img_file:
                        img_data = base64.b64encode(img_file.read()).decode()
                        response_data["image_base64"] = f"data:image/jpeg;base64,{img_data}"
            except Exception as img_error:
                print(f"Error processing image: {str(img_error)}")

            return response_data
        else:
            raise HTTPException(status_code=404, detail="User not found")

    except Exception as e:
        print(f"Error in get_user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/all")
def get_all_users(
    user_type: str = Query(None),  # "all", "individual", "instructor", "student", "quick"
    institution_id: int = Query(None),
    db: Session = Depends(get_db)
):
    result = []
    
    # Get completed entries from FinalRecords
    # completed_entries = db.query(models.FinalRecords).filter(
    #     models.FinalRecords.entry_completed == True
    # ).all().coun
    
    # Get regular users
    query = db.query(models.User)
    
    if user_type == "instructor":
        query = query.filter(models.User.is_instructor.is_(True))
    elif user_type == "student":
        query = query.filter(models.User.is_student.is_(True))
    
    if institution_id:
        query = query.filter(models.User.institution_id == institution_id)

    users = query.all()
    for user in users:
        # Check if user has completed entry
        count_of_entries = db.query(models.FinalRecords).count()
        result.append({
            "id": user.user_id,
            "name": user.name,
            "email": user.email,
            "unique_id_type": user.unique_id_type,
            "unique_id": user.unique_id,
            "image_path": user.image_path,
            "created_at": user.created_at,
            "is_quick_register": user.is_quick_register,
            "count_of_entries": count_of_entries,  # Add whether user has completed entry
            **{k: getattr(user, k) for k in ["is_student", "is_instructor", "institution_id"]}
        })

    return result

# from fastapi import Query

@router.get("/download-visitor-card/")
async def download_visitor_card(
    card_path: str = Query(..., description="Path of the visitor card file"),
):

    try:
        # Print debug info
        print(f"Requested card path: {card_path}")
        print(f"File exists check: {os.path.exists(card_path)}")
        
        if not os.path.exists(card_path):
            raise HTTPException(
                status_code=404, 
                detail=f"File not found at path: {card_path}"
            )
        
        return FileResponse(
            path=card_path,
            filename=os.path.basename(card_path),
            media_type='image/png'  # Set specific media type for PNG
        )
    except Exception as e:
        print(f"Error serving file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

