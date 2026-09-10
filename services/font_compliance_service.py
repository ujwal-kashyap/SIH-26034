import math
import re


# ============================================================
# BASIC GEOMETRY
# ============================================================

def _box_dimensions(box):
    """
    Get approximate width/height of a PaddleOCR polygon.

    PaddleOCR returns a 4-point polygon:
        [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]

    Returns:
        {
            "width_px": ...,
            "height_px": ...,
            "x_min": ...,
            "x_max": ...,
            "y_min": ...,
            "y_max": ...
        }

    Returns None if the box is invalid.
    """

    if not box or len(box) < 4:
        return None

    try:
        xs = [
            float(point[0])
            for point in box
        ]

        ys = [
            float(point[1])
            for point in box
        ]

    except (TypeError, ValueError, IndexError):
        return None

    if not xs or not ys:
        return None
                                                                                                                
    x_min = min(xs)
    x_max = max(xs)

    y_min = min(ys)
    y_max = max(ys)

    width = x_max - x_min
    height = y_max - y_min

    if width <= 0 or height <= 0:
        return None

    return {
        "width_px": width,
        "height_px": height,
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max
    }


# ============================================================
# OCR ITEM MEASUREMENT
# ============================================================

def measure_ocr_item(item):
    """
    Measure one OCR text region.

    Important:
    This measures the detected text-region height, NOT yet
    the legally defined physical character height in mm.

    That distinction is important because the image currently
    has no physical scale.
    """

    if not item:
        return None

    box = item.get("box")

    dimensions = _box_dimensions(box)

    if dimensions is None:
        return None

    return {
        "text": item.get("text", ""),
        "confidence": float(
            item.get("confidence", 0.0)
        ),
        "width_px": round(
            dimensions["width_px"],
            2
        ),
        "height_px": round(
            dimensions["height_px"],
            2
        ),
        "x_min": round(
            dimensions["x_min"],
            2
        ),
        "x_max": round(
            dimensions["x_max"],
            2
        ),
        "y_min": round(
            dimensions["y_min"],
            2
        ),
        "y_max": round(
            dimensions["y_max"],
            2
        )
    }


# ============================================================
# FIND OCR ITEM FOR A DECLARATION
# ============================================================

def _normalize_text(text):
    if text is None:
        return ""

    text = str(text).upper()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def _text_matches(field_name, ocr_text):
    """
    Determine whether an OCR line is likely associated with
    a particular declaration.

    This is deliberately conservative.
    """

    text = _normalize_text(
        ocr_text
    )

    if not text:
        return False

    patterns = {

        "MRP": [
            r"\bMRP\b"
        ],

        "Net Quantity": [
            r"\bNET\s+(?:QUANTITY|WEIGHT|WT)\b",
            r"\bQUANTITY\b",
            r"\bNET\s+WT\b"
        ],

        "Manufacturer": [
            r"\bMANUFACTUR(?:ER|ED)\b",
            r"\bMANUFACTURED\s+BY\b",
            r"\bMARKETED\s+BY\b",
            r"\bPACKED\s+BY\b",
            r"\bPACKER\b",
            r"\bIMPORTED\s+BY\b",
            r"\bIMPORTER\b"
        ],

        "Address": [
            r"\bREGISTERED\s+OFFICE\b",
            r"\bREGISTERED\s+ADDRESS\b",
            r"\bADDRESS\b"
        ],

        "Manufacturing Date": [
            r"\bMFG\b",
            r"\bMFD\b",
            r"\bDATE\s+OF\s+MANUFACTURE\b",
            r"\bDATE\s+OF\s+PACKING\b",
            r"\bPACKED\s+ON\b"
        ],

        "Best Before": [
            r"\bBEST\s+BEFORE\b",
            r"\bUSE\s+BY\b",
            r"\bEXPIRY\b",
            r"\bEXP\.?\s*DATE\b",
            r"\bEXPIRATION\b"
        ],

        "Consumer Care": [
            r"\bCONSUMER\s+CARE\b",
            r"\bCUSTOMER\s+CARE\b",
            r"\bCONSUMER\s+COMPLAINT\b",
            r"\bCONSUMER\s+HELPLINE\b",
            r"\bTOLL[\s\-]*FREE\b"
        ],

        "Unit Sale Price": [
            r"\bUNIT\s+(?:SALE|SELLING)\s+PRICE\b"
        ],

        "FSSAI": [
            r"\b[A-Z]SSAI\b",
            r"\bLIC\s*\.?\s*NO\b"
        ],

        "Country of Origin": [
            r"\bCOUNTRY\s+OF\s+ORIGIN\b",
            r"\bMADE\s+IN\b",
            r"\bPRODUCT\s+OF\b"
        ],

        "Commodity Name": [
            r"\bPRODUCT\s+NAME\b",
            r"\bITEM\s+NAME\b",
            r"\bCOMMODITY\s+NAME\b"
        ]
    }

    field_patterns = patterns.get(
        field_name,
        []
    )

    return any(
        re.search(
            pattern,
            text,
            re.IGNORECASE
        )
        for pattern in field_patterns
    )


def find_declaration_items(
    ocr_items,
    field_name
):
    """
    Find OCR boxes associated with a declaration.

    First looks for the declaration label itself.
    If found, nearby OCR boxes can later be incorporated.

    Returns measured OCR items.
    """

    results = []

    for item in ocr_items:

        text = item.get(
            "text",
            ""
        )

        if _text_matches(
            field_name,
            text
        ):

            measured = measure_ocr_item(
                item
            )

            if measured:
                results.append(
                    measured
                )

    return results


# ============================================================
# PIXEL CHARACTER HEIGHT
# ============================================================

def estimate_text_height_px(
    ocr_items,
    field_name
):
    """
    Estimate representative text-region height in pixels.

    Median is used instead of maximum/minimum because OCR
    boxes can vary due to punctuation, digits, and noise.
    """

    items = find_declaration_items(
        ocr_items,
        field_name
    )

    if not items:
        return {
            "status": "REVIEW",
            "field": field_name,
            "height_px": None,
            "confidence": 0.0,
            "evidence": None
        }

    heights = [
        item["height_px"]
        for item in items
        if item["height_px"] > 0
    ]

    if not heights:
        return {
            "status": "REVIEW",
            "field": field_name,
            "height_px": None,
            "confidence": 0.0,
            "evidence": None
        }

    heights.sort()

    middle = len(heights) // 2

    if len(heights) % 2:
        median_height = heights[middle]
    else:
        median_height = (
            heights[middle - 1]
            + heights[middle]
        ) / 2

    confidence = min(
        item["confidence"]
        for item in items
    )

    evidence = [
        {
            "text": item["text"],
            "height_px": item["height_px"],
            "width_px": item["width_px"],
            "confidence": item["confidence"]
        }
        for item in items
    ]

    return {
        "status": "MEASURED",
        "field": field_name,
        "height_px": round(
            median_height,
            2
        ),
        "confidence": round(
            confidence,
            3
        ),
        "evidence": evidence
    }


# ============================================================
# PIXELS → MILLIMETRES
# ============================================================

def pixels_to_mm(
    pixels,
    pixels_per_mm
):
    """
    Convert pixel measurement to millimetres.

    pixels_per_mm must come from a reliable scale estimation
    method.
    """

    if pixels is None:
        return None

    if pixels_per_mm is None:
        return None

    try:
        pixels_per_mm = float(
            pixels_per_mm
        )

        pixels = float(
            pixels
        )

    except (TypeError, ValueError):
        return None

    if pixels_per_mm <= 0:
        return None

    return round(
        pixels / pixels_per_mm,
        2
    )


# ============================================================
# WIDTH / HEIGHT RATIO
# ============================================================

def width_height_ratio(
    width_px,
    height_px
):
    """
    Rule 7 also specifies a minimum width relative to height.

    Returns width / height.
    """

    try:
        width_px = float(
            width_px
        )

        height_px = float(
            height_px
        )

    except (TypeError, ValueError):
        return None

    if height_px <= 0:
        return None

    return round(
        width_px / height_px,
        3
    )


# ============================================================
# FONT RULE TABLE
# ============================================================

# Rule 7 Table-I after the 2017 amendment:
#
# Principal display panel area:
#
# A <= 50 cm²       → 1.0 mm
# 50 < A <= 100     → 1.5 mm
# 100 < A <= 500    → 2.5 mm
# 500 < A <= 2500   → 4.0 mm
# A > 2500          → 6.0 mm
#
# When blown, formed or molded:
#
# 1.5 / 3 / 4 / 6 / 6 mm
#
# The table is derived from Rule 7 and should be treated as
# configuration data rather than scattered throughout code.

FONT_RULE_TABLE = [

    {
        "max_area_cm2": 50,
        "normal_mm": 1.0,
        "formed_mm": 1.5
    },

    {
        "max_area_cm2": 100,
        "normal_mm": 1.5,
        "formed_mm": 3.0
    },

    {
        "max_area_cm2": 500,
        "normal_mm": 2.5,
        "formed_mm": 4.0
    },

    {
        "max_area_cm2": 2500,
        "normal_mm": 4.0,
        "formed_mm": 6.0
    },

    {
        "max_area_cm2": math.inf,
        "normal_mm": 6.0,
        "formed_mm": 6.0
    }
]


def required_height_mm(
    pdp_area_cm2,
    formed=False
):
    """
    Return the applicable minimum height in mm.

    pdp_area_cm2:
        Principal Display Panel area in cm².

    formed:
        True for the relevant blown/formed/molded condition.
    """

    if pdp_area_cm2 is None:
        return None

    try:
        area = float(
            pdp_area_cm2
        )

    except (TypeError, ValueError):
        return None

    if area <= 0:
        return None

    for row in FONT_RULE_TABLE:

        if area <= row["max_area_cm2"]:

            if formed:
                return row["formed_mm"]

            return row["normal_mm"]

    return None


# ============================================================
# WIDTH REQUIREMENT
# ============================================================

def check_width_requirement(
    width_px,
    height_px
):
    """
    Rule 7(3):
    width should not be less than one-third of height,
    subject to the stated exceptions.
    """

    ratio = width_height_ratio(
        width_px,
        height_px
    )

    if ratio is None:
        return {
            "status": "REVIEW",
            "ratio": None,
            "message":
                "Text geometry could not be measured."
        }

    minimum_ratio = 1 / 3

    if ratio >= minimum_ratio:

        return {
            "status": "PASS",
            "ratio": ratio,
            "message":
                "Measured width is at least one-third "
                "of measured height."
        }

    return {
        "status": "REVIEW",
        "ratio": ratio,
        "message":
            "Measured width is below one-third of "
            "measured height. Verify character-level "
            "measurement because OCR bounding boxes "
            "can represent an entire word rather than "
            "an individual character."
    }


# ============================================================
# SINGLE DECLARATION CHECK
# ============================================================

def check_declaration_font(
    ocr_items,
    field_name,
    pdp_area_cm2=None,
    pixels_per_mm=None,
    formed=False
):
    """
    Complete font screening for one declaration.

    At this stage the system deliberately returns REVIEW when
    physical scale or PDP area is unavailable.
    """

    measurement = estimate_text_height_px(
        ocr_items,
        field_name
    )

    if measurement["height_px"] is None:

        return {
            "field": field_name,
            "status": "REVIEW",
            "height_px": None,
            "height_mm": None,
            "required_mm": None,
            "confidence": 0.0,
            "message":
                "Declaration text could not be located "
                "with a usable OCR bounding box.",
            "evidence": None
        }

    height_px = measurement[
        "height_px"
    ]

    height_mm = pixels_to_mm(
        height_px,
        pixels_per_mm
    )

    required_mm = required_height_mm(
        pdp_area_cm2,
        formed
    )

    # --------------------------------------------------------
    # No physical scale yet
    # --------------------------------------------------------

    if height_mm is None:

        return {
            "field": field_name,
            "status": "REVIEW",
            "height_px": height_px,
            "height_mm": None,
            "required_mm": required_mm,
            "confidence": measurement["confidence"],
            "message":
                "Text region was measured in pixels, but "
                "physical scale could not yet be established.",
            "evidence":
                measurement["evidence"]
        }

    # --------------------------------------------------------
    # No PDP area
    # --------------------------------------------------------

    if required_mm is None:

        return {
            "field": field_name,
            "status": "REVIEW",
            "height_px": height_px,
            "height_mm": height_mm,
            "required_mm": None,
            "confidence": measurement["confidence"],
            "message":
                "Physical text height was estimated, but "
                "the applicable principal display panel "
                "area is not available.",
            "evidence":
                measurement["evidence"]
        }

    # --------------------------------------------------------
    # Compare
    # --------------------------------------------------------

    tolerance = 0.10

    if height_mm >= required_mm:

        status = "COMPLIANT"

        message = (
            f"Estimated character height "
            f"{height_mm:.2f} mm meets the "
            f"minimum requirement of "
            f"{required_mm:.2f} mm."
        )

    elif height_mm >= (
        required_mm - tolerance
    ):

        status = "REVIEW"

        message = (
            f"Estimated character height "
            f"{height_mm:.2f} mm is very close "
            f"to the minimum requirement of "
            f"{required_mm:.2f} mm. Image-based "
            f"measurement should be verified."
        )

    else:

        status = "NON_COMPLIANT"

        message = (
            f"Estimated character height "
            f"{height_mm:.2f} mm is below the "
            f"minimum requirement of "
            f"{required_mm:.2f} mm."
        )

    return {
        "field": field_name,
        "status": status,
        "height_px": height_px,
        "height_mm": height_mm,
        "required_mm": required_mm,
        "confidence": measurement["confidence"],
        "message": message,
        "evidence": measurement["evidence"]
    }


# ============================================================
# ALL DECLARATIONS
# ============================================================

FONT_FIELDS = [
    "MRP",
    "Net Quantity",
    "Manufacturer",
    "Address",
    "Manufacturing Date",
    "Best Before",
    "Consumer Care",
    "Unit Sale Price",
    "FSSAI",
    "Country of Origin",
    "Commodity Name"
]


def run_font_screening(
    ocr_items,
    pdp_area_cm2=None,
    pixels_per_mm=None,
    formed=False,
    fields=None
):
    """
    Run font screening for all applicable declarations.

    IMPORTANT:
    fields can be supplied later based on the actual
    mandatory declarations for the selected product category.

    For now all supported fields can be screened.
    """

    if fields is None:
        fields = FONT_FIELDS

    results = []

    for field_name in fields:

        result = check_declaration_font(
            ocr_items=ocr_items,
            field_name=field_name,
            pdp_area_cm2=pdp_area_cm2,
            pixels_per_mm=pixels_per_mm,
            formed=formed
        )

        results.append(
            result
        )

    return results
