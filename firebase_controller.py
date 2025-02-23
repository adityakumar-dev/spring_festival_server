from datetime import datetime
import firebase_admin
from firebase_admin import db
from typing import Dict, Any

class FirebaseController:
    def __init__(self):
        # Get reference to the root of your Firebase database
        self.ref = db.reference('/')
        self.events_ref = self.ref.child('events')

    def log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Log an event to Firebase Realtime Database
        """
        timestamp = datetime.now().isoformat()
        event_data = {
            "timestamp": timestamp,
            "type": event_type,
            **data
        }
        
        # Push the event to Firebase
        self.events_ref.push(event_data)

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
                    return {"status": True, "message": "User found"}
        return {"status": False, "message": "User not found"}
    def create_app_user(self, user_name : str, user_password : str, user_email : str, aadhar_number : str) -> None:
        """
        Create a new app user
        """

        user_ref = self.ref.child('app_users')
        all_users = user_ref.get()
        if all_users is not None :
            for user_id, user in all_users.items():
                print(user)
                print(user_name == user['name'])
                if user['name'] == user_name:
                    return { "status" : False, "message" : "User already exists" }
            else:
                user_ref.push({"name": user_name, "password": user_password, "email": user_email, "aadhar_number": aadhar_number})
                return { "status" : True, "message" : "User created successfully" }
        else:
            print("User not found")
            user_ref.push({"name": user_name, "password": user_password, "email": user_email, "aadhar_number": aadhar_number})
            return { "status" : True, "message" : "User created successfully" }
       
# Create a singleton instance
firebase_controller = FirebaseController()
