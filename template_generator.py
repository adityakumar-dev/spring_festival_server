from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import os
import qrcode
from io import BytesIO
import base64

class VisitorCardGenerator:
    def __init__(self):
        self.template_path = "template/template.jpeg"
        self.font_path = "fonts/arial.ttf"
        self.card_size = (720, 1280)  # Updated to specified size
        
    def create_visitor_card(self, user_data):
        """
        Generate a visitor card for a user
        user_data should contain: name, email, profile_image_path, qr_code_path
        """
        try:
            # Load template
            template = Image.open(self.template_path)
            template = template.resize(self.card_size)
            
            # Load user profile image
            profile_img = Image.open(user_data["profile_image_path"])
            profile_img = self._resize_image(profile_img, (150, 150))  # Adjusted profile image size
            
            # Load QR code
            qr_img = Image.open(user_data["qr_code_path"])
            qr_img = self._resize_image(qr_img, (450, 450))  # Increased QR code size
            
            # Create a copy of template to work on
            card = template.copy()
            profile_pos = (80, 380)  # Adjusted profile image position
            qr_pos = (135, 700)  # Adjusted QR code position (taking space from the bottom)
            name_pos = (283, 380)
            email_pos = (283, 440)
            id_pos = (283, 480)  # Adjusted position for ID
            valid_pos = (153, 600)  # Position for "Valid Upto" below the image and text section
            
            # Paste images with transparency
            if profile_img.mode == 'RGBA':
                card.paste(profile_img, profile_pos, profile_img)
            else:
                card.paste(profile_img, profile_pos)
                
            if qr_img.mode == 'RGBA':
                card.paste(qr_img, qr_pos, qr_img)
            else:
                card.paste(qr_img, qr_pos)
            
            # Add text
            draw = ImageDraw.Draw(card)
            font_name = ImageFont.truetype(self.font_path, 48)
            font_email = ImageFont.truetype(self.font_path, 20)
            font_id = ImageFont.truetype(self.font_path, 30)
            
            draw.text(name_pos, user_data["name"], fill="black", font=font_name, stroke_width=2, stroke_fill="black")
            draw.text(email_pos, user_data["email"], fill="black", font=font_email)
            draw.text(id_pos, user_data["user_id"], fill="black", font=font_id, stroke_width=1, stroke_fill="black")
            draw.text(valid_pos, "Valid Upto: 02-03-2025 --- 05-03-2025", fill="black", font=font_id)
            
            # Save the card
            os.makedirs("generated_cards", exist_ok=True)
            output_path = f"generated_cards/{user_data['name'].replace(' ', '_')}_visitor_card_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.png"
            card.save(output_path, "PNG", quality=95)
            
            return output_path
        
        except Exception as e:
            print(f"Error generating visitor card: {str(e)}")
            raise
    
    def _resize_image(self, image, box_size):
        """Resize and crop image to exactly fit the given box size, maintaining aspect ratio."""
        img_width, img_height = image.size
        box_width, box_height = box_size
        img_ratio = img_width / img_height
        box_ratio = box_width / box_height
        
        if img_ratio > box_ratio:
            new_height = box_height
            new_width = int(new_height * img_ratio)
        else:
            new_width = box_width
            new_height = int(new_width / img_ratio)
        
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        left = (new_width - box_width) // 2
        top = (new_height - box_height) // 2
        right = left + box_width
        bottom = top + box_height
        
        return image.crop((left, top, right, bottom))

def generate_qr_code(data, output_path):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill='black', back_color='white')
    qr_img.save(output_path)

def main():
    os.makedirs("template", exist_ok=True)
    os.makedirs("fonts", exist_ok=True)
    os.makedirs("generated_cards", exist_ok=True)
    
    user = {"name": "John Doe", "email": "johndoe@example.com", "user_id": "12345", "valid_upto": "31-12-2025"}
    
    generator = VisitorCardGenerator()
    
    profile_img_path = "template/john_doe_profile.jpg"
    qr_code_path = "template/john_doe_qrcode.png"
    
    generate_qr_code(f"https://example.com/{user['user_id']}", qr_code_path)
    
    user_data = {
        "name": user["name"],
        "email": user["email"],
        "profile_image_path": profile_img_path,
        "qr_code_path": qr_code_path,
        "user_id": user["user_id"],
        "valid_upto": user["valid_upto"]
    }
    
    output = generator.create_visitor_card(user_data)
    print(f"Visitor card generated for {user['name']}: {output}")

if __name__ == "__main__":
    main()
