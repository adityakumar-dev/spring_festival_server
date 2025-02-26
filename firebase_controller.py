from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import db, credentials
from typing import Dict, Any
import json

class FirebaseController:
    def __init__(self):
        try:
            # Initialize Firebase Admin SDK if not already initialized
            if not firebase_admin._apps:
                cred = credentials.Certificate("firebase_json/visitor-management-bbd7c-firebase-adminsdk-fbsvc-c737c089a5.json")
                firebase_admin.initialize_app(cred, {
                    'databaseURL': 'https://visitor-management-bbd7c-default-rtdb.firebaseio.com/'
                })
            
            # Get reference to the root of your Firebase database
            self.ref = db.reference('/')
            self.events_ref = self.ref.child('events')
            self.logs_ref = self.ref.child('logs')
            self.success_ref = self.ref.child('success')
            self.error_ref = self.ref.child('error')
        except Exception as e:
            print(f"Firebase initialization error: {str(e)}")
            raise

    def log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        try:
            timestamp = datetime.now().isoformat()
            event_data = {
                "timestamp": timestamp,
                "type": event_type,
                **data
            }
            self.events_ref.push(event_data)
        except Exception as e:
            print(f"Error logging event: {str(e)}")

    def log_server_activity(self, log_type: str, message: str) -> None:
        try:
            log_data = {
                "log_type": log_type,
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
            self.logs_ref.push(log_data)
        except Exception as e:
            print(f"Error logging server activity: {str(e)}")

    def log_qr_scan(self, user_id: int, user_name: str, success: bool, message: str) -> None:
        """
        Log QR scan events
        """
        event_data = {
            "user_id": user_id,
            "user_name": user_name,
            "success": success,
            "message": message
        }
        self.log_event("qr_scan", event_data)

    def log_face_verification(self, user_id: int, user_name: str, matched: bool) -> None:
        """
        Log face verification events
        """
        event_data = {
            "user_id": user_id,
            "user_name": user_name,
            "matched": matched
        }
        self.log_event("face_verification", event_data)

    def log_user_creation(self, user_id: int, user_name: str, user_type: str) -> None:
        """
        Log new user creation events
        """
        event_data = {
            "user_id": user_id,
            "user_name": user_name,
            "user_type": user_type
        }
        self.log_event("user_creation", event_data)
    def verify_app_user(self, user_name: str, user_password: str) -> bool:
        """
        Verify user credentials
        """
        user_ref = self.ref.child('app_users')

        all_users = user_ref.get()
        if all_users is not None:
            for user_id, user in all_users.items():  # Iterate through the dictionary of users
                if user['name'] == user_name and user['password'] == user_password:
                    return {"status": True, "message": "User found", "email": user['email']}
        return {"status": False, "message": "User not found", "email": None}
    def create_app_user(self, user_name : str, user_password : str, user_email : str, unique_id_type : str, unique_id : str) -> None:
        """
        Create a new app user
        """

        user_ref = self.ref.child('app_users')
        all_users = user_ref.get()
        if all_users is not None :
            for user_id, user in all_users.items():
                print(user)
                # print(user_name == user['name'])
                if user['name'] == user_name:
                    return { "status" : False, "message" : "User already exists" }
            else:
                user_ref.push({"name": user_name, "password": user_password, "email": user_email, "unique_id_type": unique_id_type, "unique_id": unique_id})
                return { "status" : True, "message" : "User created successfully" }
        else:
            print("User not found")
            user_ref.push({"name": user_name, "password": user_password, "email": user_email, "unique_id_type": unique_id_type, "unique_id": unique_id})
            return { "status" : True, "message" : "User created successfully" }

    def log_success(self, user_id: int, user_name: str, message: str) -> None:
        """
        Log success events
        """
        event_data = {
            "user_id": user_id,
            "user_name": user_name,
            "message": message
        }
        self.success_ref.push(event_data)
    def log_error(self, user_id: int, user_name: str, message: str) -> None:
        """
        Log error events
        """
        event_data = {
            "user_id": user_id,
            "user_name": user_name,
            "message": message
        }
        self.error_ref.push(event_data)
    
# Create a single instance
firebase_controller = FirebaseController()
