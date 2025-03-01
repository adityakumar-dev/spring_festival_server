from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import db, credentials
from typing import Dict, Any
import json

class FirebaseController:
    def __init__(self):
        try:
            # Debugging: Firebase Initialization start
            print("Initializing Firebase...")
            
            # Initialize Firebase Admin SDK if not already initialized
            if not firebase_admin._apps:
                print("Firebase not initialized. Initializing now...")
                cred = credentials.Certificate("firebase_json/visitor-management-bbd7c-firebase-adminsdk-fbsvc-c737c089a5.json")
                firebase_admin.initialize_app(cred, {
                    'databaseURL': 'https://visitor-management-bbd7c-default-rtdb.firebaseio.com/'
                })
                print("Firebase initialized successfully")
            else:
                print("Firebase already initialized")

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
            # Debugging: Event data being pushed to Firebase
            print(f"Logging event: {event_type} with data: {json.dumps(event_data)}")
            self.events_ref.push(event_data)
            print(f"Event logged successfully: {event_type}")
        except Exception as e:
            print(f"Error logging event: {str(e)}")

    def log_server_activity(self, log_type: str, message: str) -> None:
        try:
            log_data = {
                "log_type": log_type,
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
            # Debugging: Server activity log data
            print(f"Logging server activity: {log_type} with message: {message}")
            self.logs_ref.push(log_data)
            print(f"Server activity logged successfully: {log_type}")
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
        print(f"Logging QR scan event: {user_name} ({'Success' if success else 'Failure'})")
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
        print(f"Logging face verification event: {user_name} ({'Matched' if matched else 'Not matched'})")
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
        print(f"Logging user creation event: {user_name} ({user_type})")
        self.log_event("user_creation", event_data)

    def verify_app_user(self, user_name: str, user_password: str) -> Dict[str, Any]:
        """
        Verify user credentials
        """
        print(f"Verifying user credentials for {user_name}...")
        try:
            user_ref = self.ref.child('app_users')
            all_users = user_ref.get()
            print(f"Fetched users from Firebase: {json.dumps(all_users)}")

            if all_users is not None:
                for user_id, user in all_users.items():  # Iterate through the dictionary of users
                    print(f"Checking user {user['name']} against {user_name}")
                    if user['name'] == user_name and user['password'] == user_password:
                        print(f"User found: {user_name}")
                        return {"status": True, "message": "User found", "email": user['email']}
            print(f"User not found: {user_name}")
            return {"status": False, "message": "User not found", "email": None}
        except Exception as e:
            print(f"Error verifying user: {str(e)}")
            return {"status": False, "message": "Verification failed", "email": None}

    def create_app_user(self, user_name: str, user_password: str, user_email: str, unique_id_type: str, unique_id: str) -> Dict[str, Any]:
        """
        Create a new app user
        """
        print(f"Creating user: {user_name}")
        try:
            user_ref = self.ref.child('app_users')
            all_users = user_ref.get()

            if all_users is not None:
                print(f"Users fetched from Firebase: {json.dumps(all_users)}")
                for user_id, user in all_users.items():
                    if user['name'] == user_name:
                        print(f"User {user_name} already exists!")
                        return {"status": False, "message": "User already exists"}
            
            # User does not exist, create new user
            user_ref.push({
                "name": user_name,
                "password": user_password,
                "email": user_email,
                "unique_id_type": unique_id_type,
                "unique_id": unique_id
            })
            print(f"User {user_name} created successfully")
            return {"status": True, "message": "User created successfully"}
        except Exception as e:
            print(f"Error creating user: {str(e)}")
            return {"status": False, "message": "User creation failed"}

    def log_success(self, user_id: int, user_name: str, message: str) -> None:
        """
        Log success events
        """
        event_data = {
            "user_id": user_id,
            "user_name": user_name,
            "message": message
        }
        print(f"Logging success event: {user_name} ({message})")
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
        print(f"Logging error event: {user_name} ({message})")
        self.error_ref.push(event_data)

# Create a single instance
firebase_controller = FirebaseController()
