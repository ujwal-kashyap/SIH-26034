import cv2
import numpy as np

from config import OCR_MAX_SIDE


def load_and_prepare_image(filepath):
    """
    Loads an image and prepares a reasonably sized
    version for OCR.

    We deliberately avoid aggressive preprocessing
    because excessive thresholding can destroy text.
    """

    image = cv2.imread(filepath)

    if image is None:
        raise ValueError(
            "Unable to read uploaded image."
        )

    height, width = image.shape[:2]

    largest_side = max(
        height,
        width
    )

    if largest_side > OCR_MAX_SIDE:

        scale = (
            OCR_MAX_SIDE /
            float(largest_side)
        )

        new_width = int(
            width * scale
        )

        new_height = int(
            height * scale
        )

        image = cv2.resize(
            image,
            (
                new_width,
                new_height
            ),
            interpolation=cv2.INTER_AREA
        )

    # Mild sharpening.
    # Avoid strong processing because packaging
    # often contains colored/textured backgrounds.

    blurred = cv2.GaussianBlur(
        image,
        (0, 0),
        1.0
    )

    sharpened = cv2.addWeighted(
        image,
        1.15,
        blurred,
        -0.15,
        0
    )

    return sharpened


def save_prepared_image(
    image,
    output_path
):
    success = cv2.imwrite(
        output_path,
        image
    )

    if not success:
        raise IOError(
            "Could not save processed image."
        )
