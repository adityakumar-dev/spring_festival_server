import os
import shutil
from uuid import uuid4
from fastapi import UploadFile

UPLOAD_DIR = "uploads"

def save_upload_file(file: UploadFile, prefix: str = "") -> str:
    """Save an uploaded file and return the path"""
    filename = f"{prefix}_{uuid4().hex}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    return file_path

def delete_file(file_path: str) -> bool:
    """Delete a file if it exists"""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            return True
    except Exception as e:
        print(f"Error deleting file: {e}")
    return False 