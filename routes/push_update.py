import os
import subprocess
from fastapi import APIRouter, File, Form, UploadFile, Depends, Header
from sqlalchemy.orm import Session
from fastapi import HTTPException

from dependencies import get_db, get_current_app_user
from firebase_controller import FirebaseController
from models import AppUsers
from utils.security import SecurityHandler

router = APIRouter()

@router.post("/update/web")
def update(
    admin_id: str = Form(...),
    admin_password: str = Form(...)
):
    if admin_id != 'linmar':
        return {False}
    if admin_password != "i_am_linmar":
        return {False}
    try:
        result = subprocess.run(['git', '-C', '/home/spring_admin/spring_festival_website', 'pull', 'origin', 'main'], capture_output=True, text=True)
        return {"message": "Updated successfully!", "output": result.stdout}
    except Exception as e:
        return {"error": str(e)}
@router.post("/update/server")
def update_server(    
    admin_id: str = Form(...),
    admin_password: str = Form(...)):
    if admin_id != 'linmar':
        return {False}
    if admin_password != "i_am_linmar":
        return {False}
    try:
        result = subprocess.run(['git', '-C', '/home/spring_admin/spring_festival_server', 'pull', 'origin', 'main'], capture_output=True, text=True)
        return {"message": "Updated successfully!", "output": result.stdout}
    except Exception as e:
        return {"error": str(e)}
