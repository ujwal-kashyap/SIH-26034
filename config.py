import os


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

UPLOAD_FOLDER = os.path.join(
    BASE_DIR,
    "uploads"
)

MAX_CONTENT_LENGTH = 10 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp"
}

# OCR image target.
# Very large phone images are resized before OCR.
OCR_MAX_SIDE = 1800

# Minimum confidence before an OCR item
# is considered reliable.
OCR_CONFIDENCE_REVIEW = 0.60
OCR_CONFIDENCE_GOOD = 0.85
