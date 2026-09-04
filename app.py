import os
import uuid
from xml.sax.saxutils import escape

from flask import (
    Flask,
    render_template,
    request,
    send_file
)

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

from werkzeug.utils import secure_filename

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


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# ============================================================
# CATEGORIES
# ============================================================

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


# ============================================================
# ALLOWED FILE CHECK
# ============================================================

def allowed_file(filename):

    if not filename:
        return False

    if "." not in filename:
        return False

    extension = (
        filename
        .rsplit(".", 1)[1]
        .lower()
    )

    return extension in ALLOWED_EXTENSIONS


# ============================================================
# PDF GENERATION
# ============================================================

def generate_pdf(result):

    scan_id = result["scan_id"]

    pdf_path = os.path.join(
        UPLOAD_FOLDER,
        f"{scan_id}_report.pdf"
    )

    styles = getSampleStyleSheet()

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    elements = []

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    elements.append(
        Paragraph(
            "Packaged Commodity Compliance Scanner",
            styles["Title"]
        )
    )

    elements.append(
        Spacer(1, 12)
    )

    elements.append(
        Paragraph(
            f"<b>Scan ID:</b> "
            f"{escape(str(scan_id))}",
            styles["Normal"]
        )
    )

    elements.append(
        Paragraph(
            f"<b>Category:</b> "
            f"{escape(str(result['category']))}",
            styles["Normal"]
        )
    )

    elements.append(
        Spacer(1, 15)
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    s = result["summary"]

    elements.append(
        Paragraph(
            "Screening Summary",
            styles["Heading2"]
        )
    )

    summary_data = [
        [
            "Total Checks",
            str(s["total"])
        ],
        [
            "Detected",
            str(s["detected"])
        ],
        [
            "Review",
            str(s["review"])
        ],
        [
            "Not Detected",
            str(s["not_detected"])
        ],
        [
            "Detection Score",
            f"{s['detection_score']}%"
        ],
        [
            "Overall",
            str(s["overall"])
        ]
    ]

    table = Table(
        summary_data,
        colWidths=[180, 250]
    )

    table.setStyle(
        TableStyle([
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.5,
                colors.grey
            ),

            (
                "FONTNAME",
                (0, 0),
                (-1, -1),
                "Helvetica"
            ),

            (
                "FONTNAME",
                (0, 0),
                (0, -1),
                "Helvetica-Bold"
            ),

            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP"
            ),

            (
                "PADDING",
                (0, 0),
                (-1, -1),
                6
            )
        ])
    )

    elements.append(table)

    elements.append(
        Spacer(1, 20)
    )

    # --------------------------------------------------------
    # DETECTED DECLARATIONS
    # --------------------------------------------------------

    elements.append(
        Paragraph(
            "Detected Declarations",
            styles["Heading2"]
        )
    )

    declaration_data = [
        [
            "Declaration",
            "Value",
            "Confidence",
            "Status"
        ]
    ]

    for name, field in result["detected"].items():

        if not field:
            continue

        value = field.get(
            "value",
            "N/A"
        )

        confidence = field.get(
            "confidence",
            0
        )

        status = field.get(
            "status",
            "NOT_DETECTED"
        )

        declaration_data.append([
            escape(str(name)),
            escape(str(value or "N/A")),
            f"{float(confidence) * 100:.0f}%",
            escape(str(status))
        ])

    table = Table(
        declaration_data,
        colWidths=[
            120,
            210,
            80,
            80
        ],
        repeatRows=1
    )

    table.setStyle(
        TableStyle([
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.5,
                colors.grey
            ),

            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.lightgrey
            ),

            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold"
            ),

            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP"
            ),

            (
                "PADDING",
                (0, 0),
                (-1, -1),
                5
            )
        ])
    )

    elements.append(table)

    elements.append(
        Spacer(1, 20)
    )

    # --------------------------------------------------------
    # RULE SCREENING
    # --------------------------------------------------------

    elements.append(
        Paragraph(
            "Rule Screening",
            styles["Heading2"]
        )
    )

    for rule in result["compliance"]:

        rule_name = escape(
            str(rule.get("name", ""))
        )

        rule_status = escape(
            str(rule.get("status", ""))
        )

        rule_message = escape(
            str(rule.get("message", ""))
        )

        elements.append(
            Paragraph(
                f"<b>{rule_name}</b> — "
                f"{rule_status}",
                styles["Normal"]
            )
        )

        elements.append(
            Paragraph(
                rule_message,
                styles["Normal"]
            )
        )

        if rule.get("evidence"):

            evidence = escape(
                str(rule["evidence"])
            )

            elements.append(
                Paragraph(
                    f"<b>Evidence:</b> "
                    f"{evidence}",
                    styles["Normal"]
                )
            )

        elements.append(
            Spacer(1, 8)
        )

    # --------------------------------------------------------
    # OCR EVIDENCE
    # --------------------------------------------------------

    elements.append(
        Paragraph(
            "OCR Evidence",
            styles["Heading2"]
        )
    )

    for item in result["ocr_items"]:

        text = str(
            item.get("text", "")
        )

        text = escape(text)

        if text:

            elements.append(
                Paragraph(
                    text,
                    styles["Normal"]
                )
            )

    elements.append(
        Spacer(1, 15)
    )

    # --------------------------------------------------------
    # DISCLAIMER
    # --------------------------------------------------------

    elements.append(
        Paragraph(
            "Automated screening only. Final legal "
            "determination requires verification by "
            "an authorized official.",
            styles["Italic"]
        )
    )

    # --------------------------------------------------------
    # BUILD PDF
    # --------------------------------------------------------

    doc.build(elements)

    return pdf_path


# ============================================================
# PDF DOWNLOAD ROUTE
# ============================================================

@app.route("/report/<scan_id>")
def download_report(scan_id):

    pdf_path = os.path.join(
        UPLOAD_FOLDER,
        f"{scan_id}_report.pdf"
    )

    if not os.path.exists(pdf_path):

        return (
            "Report not found.",
            404
        )

    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=f"{scan_id}_report.pdf",
        mimetype="application/pdf"
    )


# ============================================================
# MAIN PAGE
# ============================================================

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

    # ========================================================
    # POST
    # ========================================================

    if request.method == "POST":

        # ----------------------------------------------------
        # CATEGORY
        # ----------------------------------------------------

        category = request.form.get(
            "category",
            "general"
        )

        # Make sure category is valid
        if category not in CATEGORIES:

            category = "general"

        # ----------------------------------------------------
        # FILE
        # ----------------------------------------------------

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

                # =================================================
                # UNIQUE SCAN ID
                # =================================================

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

                # =================================================
                # FILE PATHS
                # =================================================

                raw_path = os.path.join(
                    UPLOAD_FOLDER,
                    f"{scan_id}_raw.{extension}"
                )

                processed_path = os.path.join(
                    UPLOAD_FOLDER,
                    f"{scan_id}_processed.jpg"
                )

                # =================================================
                # SAVE ORIGINAL IMAGE
                # =================================================

                file.save(
                    raw_path
                )

                # =================================================
                # IMAGE PREPROCESSING
                # =================================================

                image = load_and_prepare_image(
                    raw_path
                )

                save_prepared_image(
                    image,
                    processed_path
                )

                # =================================================
                # OCR
                # =================================================

                ocr_items = ocr_service.process(
                    processed_path
                )

                if not ocr_items:

                    raise ValueError(
                        "No readable text was "
                        "detected in the image."
                    )

                # =================================================
                # EXTRACT INFORMATION
                # =================================================

                detected = extract_information(
                    ocr_items
                )

                # =================================================
                # COMPLIANCE CHECK
                # =================================================

                compliance = run_compliance(
                    detected,
                    category
                )

                # =================================================
                # SUMMARY
                # =================================================

                result_summary = summary(
                    compliance
                )

                # =================================================
                # RAW OCR TEXT
                # =================================================

                raw_text = "\n".join(
                    str(item.get("text", ""))
                    for item in ocr_items
                )

                # =================================================
                # RESULT
                # =================================================

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
                        raw_text
                }

                # =================================================
                # GENERATE PDF
                # =================================================

                pdf_path = generate_pdf(
                    result
                )

                # Add PDF path to result
                result["pdf_path"] = pdf_path

            except Exception as exc:

                app.logger.exception(
                    "Scan failed"
                )

                error = str(
                    exc
                )

    # ========================================================
    # RENDER PAGE
    # ========================================================

    return render_template(
        "index.html",
        categories=CATEGORIES,
        result=result,
        error=error
    )


# ============================================================
# FILE TOO LARGE
# ============================================================

@app.errorhandler(413)
def too_large(error):

    return render_template(

        "index.html",

        categories=CATEGORIES,

        result=None,

        error=(
            "Image is too large. "
            "Maximum size is 10 MB."
        )

    ), 413


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=2323,
        debug=True
    )