from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile    
from sqlalchemy.orm import Session
from dependencies import get_db
from face_auth import is_face_match
import models
import os
from fastapi.responses import FileResponse
from firebase_controller import firebase_controller

router = APIRouter()
UPLOAD_DIR = "uploads"

@router.get('/user/image/{user_id}')
def get_user_image(
    user_id: int, 
    is_quick_register: bool = Query(False),  # Add query parameter
    db: Session = Depends(get_db)
):
    try:
        if not is_quick_register:
            # Check regular users
            user = db.query(models.User).filter(models.User.user_id == user_id).first()
            if user:
                image_path = user.image_path
            else:
                raise HTTPException(status_code=404, detail="Regular user not found")
        else:
            # Check quick register users
            quick_user = db.query(models.QuickRegister).filter(models.QuickRegister.register_id == user_id).first()
            if quick_user:
                image_path = quick_user.image_path
            else:
                raise HTTPException(status_code=404, detail="Quick register user not found")
        
        if not image_path or not os.path.exists(image_path):
            raise HTTPException(status_code=404, detail="Image not found")
        
        return FileResponse(
            image_path,
            media_type="image/jpeg",
            filename=f"user_{user_id}_image.jpg"
        )
    
    except Exception as e:
        print(f"Error serving image: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/face_recognition/verify")
async def verify_face(
    user_id: int = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    try:
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user:
            firebase_controller.log_face_verification(user_id, "Unknown", False)
            raise HTTPException(status_code=404, detail="User not found")

        print(f"Found user with image_path: {user.image_path}")
        stored_image_path = user.image_path
        
        if not stored_image_path or not os.path.exists(stored_image_path):
            print(f"Stored image not found at path: {stored_image_path}")
            return {"error": "Stored image not found"}
        
        temp_image_path = os.path.join(UPLOAD_DIR, f"temp_{uuid4().hex}_{image.filename}")
        try:
            print(f"Saving temporary image to: {temp_image_path}")
            await image.seek(0)
            
            with open(temp_image_path, "wb") as buffer:
                content = await image.read()
                buffer.write(content)
            
            print("Calling face_match function")
            is_match = is_face_match(stored_image_path, temp_image_path)
            
            # Log the verification result
            firebase_controller.log_face_verification(user_id, user.name, bool(is_match))
            
            return {"is_match": bool(is_match)}
        
        finally:
            if os.path.exists(temp_image_path):
                os.remove(temp_image_path)
                print("Temporary file removed")
                
    except Exception as e:
        firebase_controller.log_face_verification(user_id, user.name if user else "Unknown", False)
        raise HTTPException(status_code=500, detail=str(e))



# Face Recognition Log
@router.post("/face_recognition/")
def log_face_recognition(user_id: int, image_path: str, face_matched: bool, db: Session = Depends(get_db)):
    reco = models.FaceRecognition(user_id=user_id, image_path=image_path, face_matched=face_matched)
    db.add(reco)
    db.commit()
    db.refresh(reco)
    return reco

# Get Face Recognition History
@router.get("/face_recognition/{user_id}")
def get_face_recognition_history(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.FaceRecognition).filter(models.FaceRecognition.user_id == user_id).all()
