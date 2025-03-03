from facenet_pytorch import InceptionResnetV1
from PIL import Image
import torch
import numpy as np
import torchvision.transforms as transforms
import time

# Check if GPU is available and use it
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# Load model once
model = InceptionResnetV1(pretrained='vggface2').eval().to(device)

def get_embeddings(image_paths):
    imgs = []
    for image_path in image_paths:
        start_time = time.time()  # Start timing for image loading
        img = Image.open(image_path).convert('RGB')
        load_time = time.time() - start_time  # Calculate time taken to load the image
        print(f"Loading {image_path} time: {load_time:.2f} seconds")
        
        start_time = time.time()  # Start timing for resizing
        img = transforms.Resize((160, 160))(img)
        resize_time = time.time() - start_time  # Calculate time taken to resize the image
        print(f"Resizing {image_path} time: {resize_time:.2f} seconds")
        
        imgs.append(img)

    start_time = time.time()  # Start timing for tensor conversion and model inference
    img_tensor = torch.stack([transforms.ToTensor()(img) for img in imgs]).to(device)  # Batch tensor
    embeddings = model(img_tensor).detach().cpu().numpy()  # Move output back to CPU
    inference_time = time.time() - start_time  # Calculate time taken for inference
    print(f"Model inference time: {inference_time:.2f} seconds")
    
    return embeddings

def is_face_match(stored_image_path, test_image_path):
    """Compare a stored face with a test image and return True/False."""
    # Get embeddings for both images
    embeddings = get_embeddings([stored_image_path, test_image_path])
    
    # If embeddings are not found, return False
    if embeddings is None or len(embeddings) < 2:
        print("Could not extract embeddings for one or both images.")
        return False

    # Calculate cosine similarity
    similarity = np.dot(embeddings[0], embeddings[1].T) / (np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1]))
    
    # Define a threshold for face matching (you may need to adjust this)
    threshold = 0.6  # Example threshold
    print(f"Similarity Score: {similarity:.4f}")
    
    return similarity >= threshold

# Example Usage:
# print(is_face_match("user_face.jpg", "test_face.jpg"))
