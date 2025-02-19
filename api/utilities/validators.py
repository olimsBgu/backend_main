import os
from ninja.files import UploadedFile


def validate_image_file(image: UploadedFile, max_size_mb: int = 5):
    """
    Validate extension and file size of the uploaded image.
    Raises ValueError if invalid.

    :param image: The UploadedFile
    :param max_size_mb: The maximum allowed size in MB
    """
    valid_extensions = {".jpg", ".jpeg", ".png"}
    extension = os.path.splitext(image.name)[1].lower()
    if extension not in valid_extensions:
        raise ValueError("Only .jpg, .jpeg, or .png files are allowed.")

    # Check file size
    max_bytes = max_size_mb * 1024 * 1024
    if image.size > max_bytes:
        raise ValueError(f"File size exceeds {max_size_mb} MB limit.")
