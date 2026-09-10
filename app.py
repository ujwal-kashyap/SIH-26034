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
# FONT COMPLIANCE SERVICE
# ============================================================
# IMPORTANT:
# File must be:
#
# services/font_compliance_service.py
#
# ============================================================

from services.font_compliance_service import run_font_screening


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
    "general": "General Packaged Commodity",
    "packaged_food": "Packaged Food",
    "snacks": "Snacks",
    "edible_oil": "Edible Oil",
    "cosmetics": "Cosmetics"
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

    # ========================================================
    # TITLE
    # ========================================================

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

    # ========================================================
    # SUMMARY
    # ========================================================

    s = result["summary"]

    elements.append(
        Paragraph(
            "Screening Summary",
            styles["Heading2"]
        )
    )

    summary_data = [
        ["Total Checks", str(s["total"])],
        ["Detected", str(s["detected"])],
        ["Review", str(s["review"])],
        ["Not Detected", str(s["not_detected"])],
        ["Detection Score", f"{s['detection_score']}%"],
        ["Overall", str(s["overall"])]
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

    # ========================================================
    # DETECTED DECLARATIONS
    # ========================================================

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

        try:
            confidence_percent = (
                float(confidence) * 100
            )
        except (TypeError, ValueError):
            confidence_percent = 0

        declaration_data.append([
            escape(str(name)),
            escape(str(value or "N/A")),
            f"{confidence_percent:.0f}%",
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

    # ========================================================
    # RULE SCREENING
    # ========================================================

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
                f"<b>{rule_name}</b> — {rule_status}",
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
                    f"<b>Evidence:</b> {evidence}",
                    styles["Normal"]
                )
            )

        elements.append(
            Spacer(1, 8)
        )

    # ========================================================
    # FONT SIZE / DIMENSION SCREENING
    # ========================================================

    elements.append(
        Paragraph(
            "Font Size & Dimensions",
            styles["Heading2"]
        )
    )

    elements.append(
        Paragraph(
            "OCR bounding-box measurements are shown below. "
            "Physical millimetre compliance requires a "
            "reliable image scale and principal display "
            "panel area.",
            styles["Normal"]
        )
    )

    elements.append(
        Spacer(1, 10)
    )

    font_screening = result.get(
        "font_screening",
        []
    )

    if not font_screening:

        elements.append(
            Paragraph(
                "No font-size measurements were returned "
                "by the font compliance service.",
                styles["Normal"]
            )
        )

    else:

        font_data = [
            [
                "Declaration",
                "Status",
                "Width",
                "Height",
                "Physical",
                "Required"
            ]
        ]

        for item in font_screening:

            field = str(
                item.get(
                    "field",
                    "Unknown"
                )
            )

            status = str(
                item.get(
                    "status",
                    "REVIEW"
                )
            )

            width_px = item.get(
                "width_px"
            )

            height_px = item.get(
                "height_px"
            )

            height_mm = item.get(
                "height_mm"
            )

            required_mm = item.get(
                "required_mm"
            )

            # ------------------------------------------------
            # If service stores dimensions inside evidence,
            # calculate representative values.
            # ------------------------------------------------

            evidence = item.get(
                "evidence",
                []
            )

            if evidence:

                widths = []
                heights = []

                for evidence_item in evidence:

                    w = evidence_item.get(
                        "width_px"
                    )

                    h = evidence_item.get(
                        "height_px"
                    )

                    if w is not None:

                        try:
                            widths.append(
                                float(w)
                            )
                        except (
                            TypeError,
                            ValueError
                        ):
                            pass

                    if h is not None:

                        try:
                            heights.append(
                                float(h)
                            )
                        except (
                            TypeError,
                            ValueError
                        ):
                            pass

                if width_px is None and widths:

                    width_px = sum(widths) / len(widths)

                if height_px is None and heights:

                    height_px = sum(heights) / len(heights)

            width_text = (
                f"{float(width_px):.2f} px"
                if width_px is not None
                else "N/A"
            )

            height_text = (
                f"{float(height_px):.2f} px"
                if height_px is not None
                else "N/A"
            )

            physical_text = (
                f"{float(height_mm):.2f} mm"
                if height_mm is not None
                else "N/A"
            )

            required_text = (
                f"{float(required_mm):.2f} mm"
                if required_mm is not None
                else "N/A"
            )

            font_data.append([
                escape(field),
                escape(status),
                width_text,
                height_text,
                physical_text,
                required_text
            ])

        font_table = Table(
            font_data,
            colWidths=[
                105,
                70,
                70,
                70,
                75,
                75
            ],
            repeatRows=1
        )

        font_table.setStyle(
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
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    7
                ),
                (
                    "PADDING",
                    (0, 0),
                    (-1, -1),
                    4
                )
            ])
        )

        elements.append(font_table)

        elements.append(
            Spacer(1, 15)
        )

        # ----------------------------------------------------
        # FONT EVIDENCE
        # ----------------------------------------------------

        for item in font_screening:

            field = escape(
                str(
                    item.get(
                        "field",
                        "Unknown"
                    )
                )
            )

            status = escape(
                str(
                    item.get(
                        "status",
                        "REVIEW"
                    )
                )
            )

            message = escape(
                str(
                    item.get(
                        "message",
                        ""
                    )
                )
            )

            elements.append(
                Paragraph(
                    f"<b>{field}</b> — {status}",
                    styles["Normal"]
                )
            )

            if message:

                elements.append(
                    Paragraph(
                        message,
                        styles["Normal"]
                    )
                )

            for evidence_item in item.get(
                "evidence",
                []
            ):

                evidence_text = escape(
                    str(
                        evidence_item.get(
                            "text",
                            ""
                        )
                    )
                )

                width = evidence_item.get(
                    "width_px",
                    "N/A"
                )

                height = evidence_item.get(
                    "height_px",
                    "N/A"
                )

                confidence = evidence_item.get(
                    "confidence",
                    0
                )

                try:

                    confidence_percent = (
                        float(confidence) * 100
                    )

                except (
                    TypeError,
                    ValueError
                ):

                    confidence_percent = 0

                elements.append(
                    Paragraph(
                        f"Evidence: {evidence_text} "
                        f"— {width} × {height} px "
                        f"— Confidence: "
                        f"{confidence_percent:.0f}%",
                        styles["Normal"]
                    )
                )

            elements.append(
                Spacer(1, 7)
            )

    # ========================================================
    # OCR EVIDENCE
    # ========================================================

    elements.append(
        Paragraph(
            "OCR Evidence",
            styles["Heading2"]
        )
    )

    for item in result["ocr_items"]:

        text = escape(
            str(
                item.get(
                    "text",
                    ""
                )
            )
        )

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

    # ========================================================
    # DISCLAIMER
    # ========================================================

    elements.append(
        Paragraph(
            "Automated screening only. Final legal "
            "determination requires verification by "
            "an authorized official.",
            styles["Italic"]
        )
    )

    # ========================================================
    # BUILD
    # ========================================================

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
    methods=["GET", "POST"]
)
def index():

    result = None
    error = None

    if request.method == "POST":

        # ====================================================
        # CATEGORY
        # ====================================================

        category = request.form.get(
            "category",
            "general"
        )

        if category not in CATEGORIES:

            category = "general"

        # ====================================================
        # FILE
        # ====================================================

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
                # ORIGINAL FILE
                # =================================================

                original_name = secure_filename(
                    file.filename
                )

                if "." not in original_name:

                    raise ValueError(
                        "Invalid uploaded file."
                    )

                extension = (
                    original_name
                    .rsplit(
                        ".",
                        1
                    )[1]
                    .lower()
                )

                # =================================================
                # SCAN ID
                # =================================================

                scan_id = uuid.uuid4().hex

                # =================================================
                # PATHS
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
                # SAVE ORIGINAL
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
                        "No readable text was detected "
                        "in the image."
                    )

                # =================================================
                # INFORMATION EXTRACTION
                # =================================================

                detected = extract_information(
                    ocr_items
                )

                # =================================================
                # NORMAL COMPLIANCE
                # =================================================

                compliance = run_compliance(
                    detected,
                    category
                )

                # =================================================
                # FONT COMPLIANCE
                # =================================================
                #
                # The service receives OCR boxes.
                #
                # At this stage:
                #
                # pixels_per_mm = None
                #
                # means physical mm conversion cannot be
                # guaranteed unless your font service itself
                # calculates/calibrates the image scale.
                #
                # =================================================

                font_screening = run_font_screening(
                    ocr_items=ocr_items,
                    pdp_area_cm2=None,
                    pixels_per_mm=None,
                    formed=False
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
                    str(
                        item.get(
                            "text",
                            ""
                        )
                    )
                    for item in ocr_items
                )

                # =================================================
                # FINAL RESULT
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

                    "font_screening":
                        font_screening,

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

                result["pdf_path"] = pdf_path

            except Exception as exc:

                app.logger.exception(
                    "Scan failed"
                )

                error = str(
                    exc
                )

    # ========================================================
    # HTML
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
