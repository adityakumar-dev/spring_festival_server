from fastapi import APIRouter, Depends, HTTPException, File, Form, UploadFile, Query
from sqlalchemy.orm import Session
from dependencies import get_db
import models
from utils.file_handlers import save_upload_file, delete_file
from qr_generation import generate_qr_code
import base64
import os
from typing import Optional
import traceback
from fastapi.responses import JSONResponse, FileResponse
from firebase_controller import firebase_controller

router = APIRouter()

@router.post("/check/aadhar")
async def check_aadhar(aadhar_number: str = Form(...), db: Session = Depends(get_db)):
    try:
        if not aadhar_number or not aadhar_number.strip():
            raise HTTPException(status_code=400, detail="Aadhar number is required")
        user = db.query(models.User).filter(models.User.aadhar_number == aadhar_number).first()
        return {"exists": bool(user)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking Aadhar number: {str(e)}")

@router.post("/check/email/{email}")
def check_email(email: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == email).first()
    return {"exists": bool(user)}

@router.post("/create")
def create_user(
    name: str = Form(...),
    email: str = Form(...),
    aadhar_number: str = Form(None),
    image: UploadFile = File(...),
    user_type: str = Form(...),
    institution_id: int = Form(None),
    db: Session = Depends(get_db)
):
    try:
        # Validation checks...
        existing_user = db.query(models.User).filter(models.User.email == email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="User already exists")

        if aadhar_number:
            existing_aadhar = db.query(models.User).filter(models.User.aadhar_number == aadhar_number).first()
            if existing_aadhar:
                raise HTTPException(status_code=400, detail="Aadhar number already registered")

        # Save image
        image_path = save_upload_file(image)

        # Debugging: Print input values and their types
        print(f"name: {name} (type: {type(name)})")
        print(f"email: {email} (type: {type(email)})")
        print(f"aadhar_number: {aadhar_number} (type: {type(aadhar_number)})")
        print(f"image_path: {image_path} (type: {type(image_path)})")
        print(f"is_student: {user_type == 'student'} (type: {type(user_type == 'student')})")
        print(f"is_instructor: {user_type == 'instructor'} (type: {type(user_type == 'instructor')})")
        print(f"institution_id: {institution_id} (type: {type(institution_id)})")

        # Create user
        new_user = models.User(
            name=name,
            email=email,
            aadhar_number=aadhar_number,
            image_path=image_path,
            is_student=(user_type == "student"),
            is_instructor=(user_type == "instructor"),
            institution_id=institution_id,
        )
        
        db.add(new_user)
        db.flush()

        # Generate QR Code
        qr_path = generate_qr_code(new_user.user_id, new_user.name, new_user.email)
        new_user.qr_code = qr_path
        
        db.commit()
        db.refresh(new_user)
        
        # Log user creation
        firebase_controller.log_user_creation(
            new_user.user_id,
            new_user.name,
            "instructor" if new_user.is_instructor else "student"
        )
        
        return {
            "user_id": new_user.user_id,
            "name": new_user.name,
            "email": new_user.email,
            "aadhar_number": new_user.aadhar_number,
            "qr_code": new_user.qr_code,
            "image_path": new_user.image_path,
            "is_student": new_user.is_student,
            "is_instructor": new_user.is_instructor,
            "institution_id": new_user.institution_id,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating user: {str(e)}")

@router.get("/{user_id}")
def get_user(
    user_id: int, 
    is_quick_register: bool = Query(False),
    db: Session = Depends(get_db)
):
    try:
        print(f"Fetching user with ID: {user_id}, is_quick_register: {is_quick_register}")  # Debug log

        if not is_quick_register:
            # Check regular users
            user = db.query(models.User).filter(models.User.user_id == user_id).first()
            if user:
                response_data = {
                    "user": {
                        "user_id": user.user_id,
                        "name": user.name,
                        "email": user.email,
                        "is_instructor": user.is_instructor,
                        "institution": user.institution.name if user.institution else None,
                        "image_path": f"/user/image/{user.user_id}?is_quick_register=false",
                        "qr_code_path": f"/qr_code/{user.user_id}",
                        "qr_code": user.qr_code,
                        "is_quick_register": False,
                        "created_at": user.created_at.isoformat() if user.created_at else None,
                    },
                    "face_recognition": [
                        {
                            "recognition_id": fr.recognition_id,
                            "timestamp": fr.timestamp.isoformat() if fr.timestamp else None,
                            "face_matched": fr.face_matched
                        } for fr in db.query(models.FaceRecognition).filter(models.FaceRecognition.user_id == user_id).all()
                    ],
                    "qr_scan": [
                        {
                            "scan_id": qs.scan_id,
                            "arrival_time": qs.arrival_time.isoformat() if qs.arrival_time else None
                        } for qs in db.query(models.QRScan).filter(models.QRScan.user_id == user_id).all()
                    ],
                    "image_base64": None,
                    "qr_base64": None
                }

                # Add QR code base64 if exists
                try:
                    if user.qr_code and os.path.exists(user.qr_code):
                        with open(user.qr_code, "rb") as qr_file:
                            qr_data = base64.b64encode(qr_file.read()).decode()
                            response_data["qr_base64"] = f"data:image/png;base64,{qr_data}"
                except Exception as qr_error:
                    print(f"Error processing QR code: {str(qr_error)}")
                    response_data["qr_base64"] = None

            else:
                raise HTTPException(status_code=404, detail="Regular user not found")
        else:
            print(f"Querying QuickRegister table for ID: {user_id}")  # Debug log
            # Check quick register users
            quick_user = db.query(models.QuickRegister).filter(models.QuickRegister.register_id == user_id).first()
            if quick_user:
                print(f"Found quick user: {quick_user.name}")  # Debug log
                response_data = {
                    "user": {
                        "user_id": quick_user.register_id,
                        "name": quick_user.name,
                        "email": quick_user.email,
                        "image_path": f"/user/image/{quick_user.register_id}?is_quick_register=true",
                        "is_quick_register": True,
                        "created_at": quick_user.created_at.isoformat() if quick_user.created_at else None,
                    },
                    "image_base64": None
                }
            else:
                raise HTTPException(status_code=404, detail="Quick register user not found")

        # Add base64 encoded image if exists
        try:
            image_path = user.image_path if not is_quick_register else quick_user.image_path
            if image_path and os.path.exists(image_path):
                with open(image_path, "rb") as img_file:
                    img_data = base64.b64encode(img_file.read()).decode()
                    response_data["image_base64"] = f"data:image/jpeg;base64,{img_data}"
        except Exception as img_error:
            print(f"Error processing image: {str(img_error)}")
            response_data["image_base64"] = None

        return JSONResponse(content=response_data)

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error in get_user: {str(e)}")
        print(f"Error type: {type(e)}")
        print(f"Error traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/all")
def get_all_users(
    user_type: str = Query(None),  # "all", "individual", "instructor", "student", "quick"
    institution_id: int = Query(None),
    # instructor_id: int = Query(None),
    db: Session = Depends(get_db)
):
    result = []
    
    # Get regular users
    query = db.query(models.User)
    
    if user_type == "instructor":
        query = query.filter(models.User.is_instructor.is_(True))
    elif user_type == "student":
        query = query.filter(models.User.is_student.is_(True))
    
    if institution_id:
        query = query.filter(models.User.institution_id == institution_id)
    # if instructor_id:
    #     query = query.filter(models.User.instructor_id == instructor_id)
    
    users = query.all()
    for user in users:
        result.append({
            "id": user.user_id,
            "name": user.name,
            "email": user.email,
            "aadhar_number": user.aadhar_number,
            "image_path": user.image_path,
            "created_at": user.created_at,
            "is_quick_register": False,
            **{k: getattr(user, k) for k in ["is_student", "is_instructor", "institution_id"]}
        })

    # Get quick register users if type is "all" or "quick"
    if user_type in [None, "all", "quick"]:
        quick_users = db.query(models.QuickRegister).all()
        for quick_user in quick_users:
            result.append({
                "id": quick_user.register_id,
                "name": quick_user.name,
                "email": quick_user.email,
                "aadhar_number": quick_user.aadhar_number,
                "image_path": quick_user.image_path,
                "created_at": quick_user.created_at,
                "is_quick_register": True,
                "is_student": False,
                "is_instructor": False,
                "institution_id": None,
            })
    
    return result

