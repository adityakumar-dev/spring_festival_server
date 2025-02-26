from PIL import Image, ImageDraw, ImageFont
import os
import qrcode
from io import BytesIO
import base64

class VisitorCardGenerator:
    def __init__(self):
        self.template_path = "template/template.jpeg"
        self.font_path = "fonts/arial.ttf"
        self.card_size = (1240, 700)  # Template exact size
        
    def create_visitor_card(self, user_data):
        """
        Generate a visitor card for a user
        user_data should contain: name, email, profile_image_path, qr_code_path
        """
        try:
            # Load template
            template = Image.open(self.template_path)
            template = template.resize(self.card_size)  # Ensure template is correct size
            
            # Load user profile image
            profile_img = Image.open(user_data["profile_image_path"])
            profile_img = self._resize_image(profile_img, (203, 204))  # Small box size
            
            # Load QR code
            qr_img = Image.open(user_data["qr_code_path"])
            qr_img = self._resize_image(qr_img, (439, 442))  # Big box size
            
            # Create a copy of template to work on
            card = template.copy()
            
            # Calculate positions
            profile_pos = (263, 184)  # Small box Top Left
            qr_pos = (632, 196)       # Big box Top Left
            
            # Text positions (below the profile image)
            name_pos = (263, 468)      # Below profile image
            email_pos = (263, 548)     # Below name
            
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
            
            draw.text(name_pos, user_data["name"], fill="black", font=font_name, stroke_width=2, stroke_fill="black")
            draw.text(email_pos, user_data["email"], fill="black", font=font_email)
            
            # Save the card
            os.makedirs("generated_cards", exist_ok=True)
            output_path = f"generated_cards/{user_data['name'].replace(' ', '_')}_visitor_card.png"
            card.save(output_path, "PNG", quality=95)
            
            return output_path
            
        except Exception as e:
            print(f"Error generating visitor card: {str(e)}")
            raise
    def _resize_image(self, image, box_size):
        """Resize and crop image to exactly fit the given box size, maintaining aspect ratio."""
        img_width, img_height = image.size
        box_width, box_height = box_size

        # Determine the new size to maintain aspect ratio while covering the box
        img_ratio = img_width / img_height
        box_ratio = box_width / box_height

        if img_ratio > box_ratio:
            # Image is wider than the box: Fit to height, then crop width
            new_height = box_height
            new_width = int(new_height * img_ratio)
        else:
            # Image is taller than the box: Fit to width, then crop height
            new_width = box_width
            new_height = int(new_width / img_ratio)

        # Resize the image
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Calculate cropping coordinates to center the image
        left = (new_width - box_width) // 2
        top = (new_height - box_height) // 2
        right = left + box_width
        bottom = top + box_height

        # Crop the image to fit the exact box size
        image = image.crop((left, top, right, bottom))

        return image
