import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication
import os
from typing import List
from fastapi import HTTPException, BackgroundTasks
from pathlib import Path

class EmailConfig:
    # Gmail SMTP Configuration
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 465  # SSL Port
    
    # Gmail Credentials (Use App Password)
    EMAIL_ADDRESS = "rbspringfestival@gmail.com"
    EMAIL_PASSWORD = "dmwmmgemutcequbf"  # App password

class InvitationEmailHandler:
    def __init__(self):
        self.email = EmailConfig.EMAIL_ADDRESS
        self.password = EmailConfig.EMAIL_PASSWORD
        
        if not all([self.email, self.password]):
            raise ValueError("Email credentials not configured")

    def send_welcome_email(
        self,
        to_email: str,
        user_name: str,
        qr_code_path: str,
        visitor_card_path: str
    ) -> bool:
        """Send welcome email with visitor card details and attachments"""
        try:
            msg = MIMEMultipart()
            msg["From"] = self.email
            msg["To"] = to_email
            msg["Subject"] = "Welcome to Spring Festival - Your Visitor Card is Ready"

            # HTML Content
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px;">
                        <h1 style="text-align: center; color: #1a1a1a;">Welcome to Spring Festival</h1>
                        <div style="margin: 20px 0; line-height: 1.6;">
                            <p>Dear {user_name},</p>
                            <p>Welcome to Spring Festival! Your registration has been completed successfully.</p>
                            <p>Your visitor card and QR code are attached to this email.</p>
                            <p>Important Information:</p>
                            <ul>
                                <li>Keep your QR code handy for quick check-in</li>
                                <li>Your visitor card is your identity within the premises</li>
                                <li>Follow all safety guidelines and protocols</li>
                            </ul>
                            <p>Please find your visitor card and QR code attached to this email.</p>
                        </div>
                        <div style="text-align: center; color: #6c757d; font-size: 12px; margin-top: 20px; border-top: 1px solid #dee2e6; padding-top: 20px;">
                            <p>This is an automated message. Please do not reply to this email.</p>
                            <p>Spring Festival Team</p>
                        </div>
                    </div>
                </body>
            </html>
            """

            msg.attach(MIMEText(html_content, "html"))

            # Attach Visitor Card
            if os.path.exists(visitor_card_path):
                with open(visitor_card_path, 'rb') as f:
                    visitor_card = MIMEImage(f.read())
                    visitor_card.add_header(
                        'Content-Disposition',
                        'attachment',
                        filename=f'visitor_card_{user_name}.png'
                    )
                    msg.attach(visitor_card)

            # Attach QR Code
            if os.path.exists(qr_code_path):
                with open(qr_code_path, 'rb') as f:
                    qr_code = MIMEImage(f.read())
                    qr_code.add_header(
                        'Content-Disposition',
                        'attachment',
                        filename=f'qr_code_{user_name}.png'
                    )
                    msg.attach(qr_code)

            try:
                # Connect to Gmail SMTP Server and Send Email
                server = smtplib.SMTP_SSL(EmailConfig.SMTP_SERVER, EmailConfig.SMTP_PORT)
                server.login(self.email, self.password)
                server.send_message(msg)
                server.quit()
                print(f"✅ Welcome email with attachments sent successfully to {to_email}!")
                return True

            except Exception as e:
                print(f"❌ SMTP Error: {str(e)}")
                return False

        except Exception as e:
            print(f"❌ Failed to send welcome email: {str(e)}")
            return False

def send_welcome_email_background(
    background_tasks: BackgroundTasks,
    user_email: str,
    user_name: str,
    qr_code_path: str,
    visitor_card_path: str
):
    """Add email sending to background tasks"""
    def send_email():
        try:
            email_handler = InvitationEmailHandler()
            success = email_handler.send_welcome_email(
                to_email=user_email,
                user_name=user_name,
                qr_code_path=qr_code_path,
                visitor_card_path=visitor_card_path
            )
            if success:
                print(f"✅ Background email with attachments sent successfully to {user_email}")
            else:
                print(f"❌ Failed to send background email to {user_email}")
        except Exception as e:
            print(f"❌ Background email task failed: {str(e)}")

    background_tasks.add_task(send_email) 