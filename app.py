import os
import uuid

from flask import (
    Flask,
    render_template,
    request
)

from werkzeug.utils import (
    secure_filename
)

from config import (
    UPLOAD_FOLDER,
    ALLOWED_EXTENSIONS,
    MAX_CONTENT_LENGTH
)

from services.image_service import (
    load_and_prepare_image,
    save_prepared_image
)

from services.ocr_service import (
    ocr_service
)

from services.extraction_service import (
    extract_information
)

from services.compliance_service import (
    run_compliance,
    summary
)


app = Flask(__name__)

app.config[
    "MAX_CONTENT_LENGTH"
] = MAX_CONTENT_LENGTH

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


CATEGORIES = {

    "general":
        "General Packaged Commodity",

    "packaged_food":
        "Packaged Food",

    "snacks":
        "Snacks",

    "edible_oil":
        "Edible Oil",

    "cosmetics":
        "Cosmetics"
}


def allowed_file(filename):

    if "." not in filename:

        return False

    extension = (
        filename
        .rsplit(
            ".",
            1
        )[1]
        .lower()
    )

    return extension in ALLOWED_EXTENSIONS


@app.route(
    "/",
    methods=[
        "GET",
        "POST"
    ]
)
def index():

    result = None

    error = None


    if request.method == "POST":

        category = request.form.get(
            "category",
            "general"
        )


        file = request.files.get(
            "image"
        )


        if not file:

            error = (
                "Please upload a product image."
            )

        elif not file.filename:

            error = (
                "Please select an image."
            )

        elif not allowed_file(
            file.filename
        ):

            error = (
                "Unsupported image format."
            )

        else:

            try:

                # ----------------------------------
                # Unique filename
                # ----------------------------------

                original_name = secure_filename(
                    file.filename
                )

                extension = (
                    original_name
                    .rsplit(
                        ".",
                        1
                    )[1]
                    .lower()
                )

                scan_id = uuid.uuid4().hex

                raw_path = os.path.join(

                    UPLOAD_FOLDER,

                    f"{scan_id}_raw."
                    f"{extension}"
                )

                processed_path = os.path.join(

                    UPLOAD_FOLDER,

                    f"{scan_id}_processed.jpg"
                )


                file.save(
                    raw_path
                )


                # ----------------------------------
                # Image preprocessing
                # ----------------------------------

                image = (
                    load_and_prepare_image(
                        raw_path
                    )
                )

                save_prepared_image(

                    image,

                    processed_path
                )


                # ----------------------------------
                # OCR
                # ----------------------------------

                ocr_items = (
                    ocr_service.process(
                        processed_path
                    )
                )


                if not ocr_items:

                    raise ValueError(
                        "No readable text was "
                        "detected in the image."
                    )


                # ----------------------------------
                # Extract fields
                # ----------------------------------

                detected = (
                    extract_information(
                        ocr_items
                    )
                )


                # ----------------------------------
                # Rule screening
                # ----------------------------------

                compliance = (
                    run_compliance(
                        detected,
                        category
                    )
                )


                result_summary = (
                    summary(
                        compliance
                    )
                )


                result = {

                    "scan_id":
                        scan_id,

                    "category":
                        CATEGORIES.get(
                            category,
                            category
                        ),

                    "ocr_items":
                        ocr_items,

                    "detected":
                        detected,

                    "compliance":
                        compliance,

                    "summary":
                        result_summary,

                    "raw_text":
                        "\n".join(
                            item["text"]
                            for item
                            in ocr_items
                        )
                }


            except Exception as exc:

                app.logger.exception(
                    "Scan failed"
                )

                error = str(
                    exc
                )


    return render_template(

        "index.html",

        categories=
            CATEGORIES,

        result=
            result,

        error=
            error
    )


@app.errorhandler(
    413
)
def too_large(error):

    return render_template(

        "index.html",

        categories=
            CATEGORIES,

        result=
            None,

        error=
            "Image is too large. "
            "Maximum size is 10 MB."
    ), 413


if __name__ == "__main__":

    app.run(

        host="127.0.0.1",

        port=2323,

        debug=True
    )
