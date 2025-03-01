import face_recognition

def is_face_match(stored_image_path, test_image_path):
    """Compare a stored face with a test image and return True/False."""
    # Load and encode stored image

    
    # Load the images into numpy arrays
    image1 = face_recognition.load_image_file(stored_image_path)
    image2 = face_recognition.load_image_file(test_image_path)
    
    # Get the face encodings for the faces in each image
    image1_encoding = face_recognition.face_encodings(image1)
    image2_encoding = face_recognition.face_encodings(image2)
    
    # If there are no faces detected in either image
    if len(image1_encoding) == 0:
        print("No faces found in the first image.")
        return False
    if len(image2_encoding) == 0:
        print("No faces found in the second image.")
        return False

  
    # Compare faces and return the result
    return face_recognition.compare_faces([image1_encoding[0]], image2_encoding[0])

# Example Usage:
# print(is_face_match("user_face.jpg", "test_face.jpg"))
