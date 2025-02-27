import os
from fastapi import APIRouter, File, Form, UploadFile, Depends, Header
from sqlalchemy.orm import Session
from fastapi import HTTPException

from dependencies import get_db, get_current_app_user
from firebase_controller import FirebaseController
from models import AppUsers
from utils.security import SecurityHandler

router = APIRouter()

@router.post("/verify")
async def verify_app_user_endpoint(
    user_name: str = Form(...), 
    user_password: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        firebase_controller = FirebaseController()
        result = firebase_controller.verify_app_user(user_name, user_password)
        
        if result.get('status'):
            # Get or create app user
            app_user = db.query(AppUsers).filter(
                AppUsers.name == user_name
            ).first()
            
            if app_user:
                # Clear any existing API key first
                if app_user.api_key:
                    SecurityHandler().logout_user(db, app_user)
                
                # Generate new API key
                api_key_data = SecurityHandler().login_user(db, app_user)
                
                return {
                    "status": True,
                    "message": "Login successful",
                    "api_key": api_key_data["api_key"],
                    "expires_at": api_key_data["expires_at"],
                    "user": {
                        "id": app_user.user_id,
                        "name": app_user.name,
                        "email": app_user.email
                    }
                }
        
        return {"status": False, "message": "Invalid credentials"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/logout")
async def logout_endpoint(
    current_app_user: AppUsers = Depends(get_current_app_user),
    db: Session = Depends(get_db)
):
    try:
        SecurityHandler().logout_user(db, current_app_user)
        return {
            "status": True,
            "message": "Logged out successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/create")
async def create_app_user_endpoint(
    admin_name: str = Form(...),
    admin_password: str = Form(...),
    user_name: str = Form(...),
    user_password: str = Form(...), 
    user_email: str = Form(...),
    unique_id_type: str = Form(...),
    unique_id: str = Form(...),
    profile_picture: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    try:
        if admin_name == "admin" and admin_password == "admin":
            firebase_controller = FirebaseController()
            isCreated = firebase_controller.create_app_user(
                user_name, user_password, user_email, unique_id_type, unique_id
            )
            
            if isCreated and isCreated.get('status'):
                profile_picture_path = f"app_users/{user_name}_{profile_picture.filename}"
                os.makedirs(os.path.dirname(profile_picture_path), exist_ok=True)
                with open(profile_picture_path, "wb") as f:
                    f.write(await profile_picture.read())
                
                app_user = AppUsers(
                    name=user_name,
                    email=user_email,
                    unique_id_type=unique_id_type,
                    unique_id=unique_id,
                    image_path=profile_picture_path
                )
                
                db.add(app_user)
                db.commit()
                db.refresh(app_user)
                
                # Generate initial API key
                # api_key_data = SecurityHandler().login_user(db, app_user)
                
                return {
                    "status": True,
                    "message": "User created successfully",
                    "user": {
                        "id": app_user.user_id,
                        "name": app_user.name,
                        "email": app_user.email,
                    }
                }
            
            return {"status": False, "message": "User creation failed"}
        
        return {"status": False, "message": "Invalid admin credentials"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/verify_user")
def verify_user(user_name: str = Form(...), user_password: str = Form(...),api_key: str = Header(...), db: Session = Depends(get_db)):
    firebase_controller = FirebaseController()
    result = firebase_controller.verify_app_user(user_name, user_password)
    if result.get('status'):
        app_user = SecurityHandler().verify_api_key(db, api_key)
        return { "status" : True, "message" : "User verified", "user" : app_user }
    else:
        return { "status" : False, "message" : "Invalid user credentials" }

@router.post("/check/admin")
def check_admin(admin_name: str = Form(...), admin_password: str = Form(...)):
    is_admin = admin_name == "admin" and admin_password == "admin"
    return { "status" : is_admin, "message" : "Admin verified" if is_admin else "Invalid admin credentials" }