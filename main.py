import os
from fastapi import FastAPI, Depends, UploadFile, File, Form, Query
from fastapi.responses import  JSONResponse
from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models
import shutil
from uuid import uuid4
from fastapi import HTTPException
import base64
from fastapi.middleware.cors import CORSMiddleware
import traceback
import firebase_admin
from firebase_admin import credentials
from sqlalchemy import func

# Remove the existing Firebase initialization
# Initialize Firebase Admin SDK with the correct credentials
cred = credentials.Certificate("firebase_json/visitor-management-bbd7c-firebase-adminsdk-fbsvc-c39ae22327.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://visitor-management-bbd7c-default-rtdb.firebaseio.com/'
})

from routes import analytics, app_users_handler, face_recognition, institutions, qr, users

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Create Tables
models.Base.metadata.create_all(bind=engine)
UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(institutions.router, prefix="/institutions", tags=["institutions"])
app.include_router(qr.router, prefix="/qr", tags=["qr"])
app.include_router(face_recognition.router)
# app.include_router(quick_register.router)
app.include_router(app_users_handler.router, prefix="/app_users", tags=["app_users"])
app.include_router(analytics.router, )
@app.get("/")
async def check():
    return {True}
@app.get("/health-check")
async def health_check():
    return {"status": "ok"}

# Face Recognition route
@app.post("/verify_face")
async def verify_face(
    user_id: int = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Save the uploaded verification image
    verify_image_filename = f"verify_{uuid4().hex}_{image.filename}"
    verify_image_path = os.path.join(UPLOAD_DIR, verify_image_filename)
    
    with open(verify_image_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)

    # Perform face verification (implement your face recognition logic here)
    face_matched = True  # Replace with actual face verification logic
    
    # Record the face recognition attempt
    recognition = models.FaceRecognition(
        user_id=user.user_id,
        image_path=verify_image_path,
        face_matched=face_matched
    )
    db.add(recognition)
    db.commit()

    return {
        "user_id": user.user_id,
        "face_matched": face_matched,
        "institution": user.institution,
        "is_instructor": user.is_instructor
    }

# Update user route
@app.put("/users/{user_id}")
def update_user(
    user_id: int,
    name: str = Form(None),
    email: str = Form(None),
    aadhar_number: str = Form(None),  # New parameter
    institution_id: int = Form(None),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    # Debug: Print incoming data
    print(f"Received update request for user {user_id}")
    # print(f"Name: {name}, Email: {email}, Institution: {institution_id})

    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Debug: Print user before update
    print(f"Before update - User data: {user.__dict__}")

    # Track if any changes were made
    changes_made = False

    # Update basic fields if provided
    if name is not None and name.strip():  # Check if name is not None and not empty
        user.name = name
        changes_made = True
        print(f"Updating name to: {name}")

    if email is not None and email.strip():  # Check if email is not None and not empty
        existing_user = db.query(models.User).filter(
            models.User.email == email,
            models.User.user_id != user_id
        ).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already exists")
        user.email = email
        changes_made = True
        print(f"Updating email to: {email}")

    if institution_id is not None and institution_id.strip():
        user.institution_id = institution_id
        changes_made = True
        print(f"Updating institution_id to: {institution_id}")

    # if instructor_id is not None and instructor_id.strip():
    #     user.instructor_id = instructor_id
    #     changes_made = True
    #     print(f"Updating instructor_id to: {instructor_id}")

    if aadhar_number is not None and aadhar_number.strip():
        existing_aadhar = db.query(models.User).filter(
            models.User.aadhar_number == aadhar_number,
            models.User.user_id != user_id
        ).first()
        if existing_aadhar:
            raise HTTPException(status_code=400, detail="Aadhar number already exists")
        user.aadhar_number = aadhar_number
        changes_made = True
        print(f"Updating aadhar_number to: {aadhar_number}")

    if image:
        # Handle image update
        if user.image_path and os.path.exists(user.image_path):
            try:
                os.remove(user.image_path)
            except Exception as e:
                print(f"Error deleting old image: {e}")

        image_filename = f"{uuid4().hex}_{image.filename}"
        image_path = os.path.join(UPLOAD_DIR, image_filename)
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        user.image_path = image_path
        changes_made = True
        print(f"Updating image path to: {image_path}")

    try:
        if not changes_made:
            print("No changes were made to update")
            return {"message": "No changes provided for update"}

        print("Committing changes to database...")
        db.commit()
        db.refresh(user)

        # Debug: Print user after update
        print(f"After update - User data: {user.__dict__}")

        return {
            "user_id": user.user_id,
            "name": user.name,
            "email": user.email,
            "aadhar_number": user.aadhar_number,
            "image_path": user.image_path,
            "is_instructor": user.is_instructor,
            "institution_id": user.institution_id,
            # "instructor_id": user.instructor_id,
            "qr_code": user.qr_code
        }
    except Exception as e:
        print(f"Error during update: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating user: {str(e)}")

# Delete user route
@app.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Delete associated records
    db.query(models.QRScan).filter(models.QRScan.user_id == user_id).delete()
    db.query(models.FaceRecognition).filter(models.FaceRecognition.user_id == user_id).delete()
    
    # Delete user
    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully"}

@app.get("/users/{user_id}")
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
                        "is_quick_register": False
                    },
                    "face_recognition": [
                        {
                            "recognition_id": fr.recognition_id,
                            "timestamp": fr.timestamp,
                            "face_matched": fr.face_matched
                        } for fr in db.query(models.FaceRecognition).filter(models.FaceRecognition.user_id == user_id).all()
                    ],
                    "qr_scan": [
                        {
                            "scan_id": qs.scan_id,
                            "arrival_time": qs.arrival_time
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
                        "created_at": str(quick_user.created_at)
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

# New route to create an institution
# @app.post("/institutions/")
# def create_institution(
#     name: str = Form(...),
#     db: Session = Depends(get_db)
# ):
#     existing_institution = db.query(models.Institution).filter(models.Institution.name == name).first()
#     if existing_institution:
#         raise HTTPException(status_code=400, detail="Institution already exists")
    
#     new_institution = models.Institution(name=name)
#     db.add(new_institution)
#     db.commit()
#     db.refresh(new_institution)
#     return new_institution

# @app.post("/institutions")

