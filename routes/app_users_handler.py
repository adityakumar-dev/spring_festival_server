import os
from fastapi import APIRouter, File, Form, UploadFile, Depends
from sqlalchemy.orm import Session

from dependencies import get_db
from firebase_controller import FirebaseController
from models import AppUsers

router = APIRouter()

@router.post("/verify")
async def verify_app_user_endpoint(user_name : str = Form(...), user_password : str = Form(...)):
    firebase_controller = FirebaseController()

    return firebase_controller.verify_app_user(user_name, user_password)

@router.post("/create")
async def create_app_user_endpoint(
    admin_name : str = Form(...),
    admin_password : str = Form(...),
    user_name : str = Form(...),
    user_password : str = Form(...), 
    user_email : str = Form(...),
    aadhar_number : str = Form(...),
    profile_picture : UploadFile = File(...),
    db: Session = Depends(get_db)
):
    firebase_controller = FirebaseController()
    if admin_name == "admin" and admin_password == "admin":
        app_user = db.query(AppUsers).filter(AppUsers.aadhar_number == aadhar_number).first()
        if app_user is not None:
            return { "status" : False, "message" : "Aadhar number already exists" }
        isCreated = firebase_controller.create_app_user(user_name, user_password, user_email, aadhar_number)
        print(isCreated)
        if isCreated is not None:
            if isCreated['status'] == True:
                profile_picture_path = f"app_users/{user_name}_{profile_picture.filename}"
                os.makedirs(os.path.dirname(profile_picture_path), exist_ok=True)
                with open(profile_picture_path, "wb") as f:
                    f.write(await profile_picture.read())

                app_user = AppUsers(
                    name = user_name,
                    email = user_email,
                    aadhar_number = aadhar_number,
                    image_path = profile_picture_path
                )

                db.add(app_user)
                db.commit()
                db.refresh(app_user)
                return { "status" : True, "message" : "User created successfully", "user" : app_user }
            else:
                return { "status" : False, "message" : "User already exists" }
        else:
            return { "status" : False, "message" : "User creation failed" }
    else:
        return { "status" : False, "message" : "Invalid admin credentials" }

@router.post("/verify_user")
def verify_user(user_name: str = Form(...), user_password: str = Form(...)):
    firebase_controller = FirebaseController()
    result = firebase_controller.verify_app_user(user_name, user_password)
    return result
@router.post("/check/admin")
def check_admin(admin_name: str = Form(...), admin_password: str = Form(...)):
    is_admin = admin_name == "admin" and admin_password == "admin"
    return { "status" : is_admin, "message" : "Admin verified" if is_admin else "Invalid admin credentials" }