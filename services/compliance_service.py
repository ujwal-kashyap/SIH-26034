import re
from rules.rules import (
    RULES,
    CATEGORY_MAP
)


def field_status(field):

    if not field:
        return "NOT_DETECTED"

    return field.get(
        "status",
        "NOT_DETECTED"
    )
def validate_field(field, rule):
    """
    Validate whether a detected field is actually compliant.
    Returns:
        (status, message)
    """

    if not field:
        if rule.get("required", False):
            return (
                "REVIEW",
                f'{rule["name"]} was not reliably detected.'
            )

        return (
            "NOT_DETECTED",
            f'{rule["name"]} was not detected.'
        )

    status = field_status(field)

    if status in ["REVIEW", "LOW_CONFIDENCE"]:
        return (
            "REVIEW",
            f'{rule["name"]} could not be confirmed with sufficient OCR confidence.'
        )

    # ----------------------------------------------------
    # Actual field-specific validation
    # ----------------------------------------------------

    value = str(
        field.get("value", "")
    ).strip()

    # MRP
    if rule["field"] == "MRP":

        try:
            price = float(
                re.sub(
                    r"[^\d.]",
                    "",
                    value
                )
            )

            if price <= 0:
                return (
                    "VIOLATION",
                    "MRP must be greater than zero."
                )

        except ValueError:

            return (
                "VIOLATION",
                "MRP format could not be validated."
            )

    # Net Quantity
    elif rule["field"] == "Net Quantity":

        if not re.search(
            r"\d+(?:\.\d+)?\s*(?:KG|G|GM|MG|ML|L)\b",
            value,
            re.IGNORECASE
        ):
            return (
                "VIOLATION",
                "Net Quantity format could not be validated."
            )

    # Manufacturer
    elif rule["field"] == "Manufacturer":

        if len(value) < 3:
            return (
                "VIOLATION",
                "Manufacturer / Packer / Importer declaration is invalid."
            )

    # Address
    elif rule["field"] == "Address":

        if len(value) < 10:
            return (
                "VIOLATION",
                "Address declaration appears incomplete."
            )

    # Manufacturing Date
    elif rule["field"] == "Manufacturing Date":

        if not re.search(
            r"\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}",
            value
        ):
            return (
                "VIOLATION",
                "Manufacturing date format could not be validated."
            )

    # Consumer Care
    elif rule["field"] == "Consumer Care":

        if not re.search(
            r"@|(?:\+?\d[\d\s\-]{7,18}\d)",
            value,
            re.IGNORECASE
        ):
            return (
                "VIOLATION",
                "Consumer Care details could not be validated."
            )

    # Unit Sale Price
    elif rule["field"] == "Unit Sale Price":

        if not re.search(
            r"\d+(?:\.\d+)?",
            value
        ):
            return (
                "VIOLATION",
                "Unit Sale Price format could not be validated."
            )

    # FSSAI
    elif rule["field"] == "FSSAI":

        if not re.fullmatch(
            r"\d{10,14}",
            value
        ):
            return (
                "VIOLATION",
                "FSSAI licence number format appears invalid."
            )

    return (
        "DETECTED",
        f'{rule["name"]} detected and basic validation passed.'
    )

def run_compliance(
    detected,
    category
):

    results = []

    rules = list(
        RULES["general"]
    )

    category_rule_group = (
        CATEGORY_MAP.get(
            category
        )
    )

    if category_rule_group:

        if category_rule_group != "general":

            rules.extend(
                RULES.get(
                    category_rule_group,
                    []
                )
            )


    for rule in rules:

        field = detected.get(
            rule["field"]
        )

        status, message = validate_field(
    field,
    rule
)


        # ----------------------------------------------
        # Reliable detection
        # ----------------------------------------------

        if status == "DETECTED":

            results.append({

                "id":
                    rule["id"],

                "name":
                    rule["name"],

                "status":
                    "DETECTED",

                "message":
                    f'{rule["name"]} detected.',

                "value":
                    field["value"],

                "confidence":
                    field["confidence"],

                "evidence":
                    field["evidence"],

                "reference":
                    rule["reference"]
            })


        # ----------------------------------------------
        # OCR uncertain
        # ----------------------------------------------

        elif status in [
            "REVIEW",
            "LOW_CONFIDENCE"
        ]:

            results.append({

                "id":
                    rule["id"],

                "name":
                    rule["name"],

                "status":
                    "REVIEW",

                "message":
                    f'{rule["name"]} could not be '
                    f'confirmed with sufficient '
                    f'OCR confidence.',

                "value":
                    field.get(
                        "value"
                    ) if field else None,

                "confidence":
                    field.get(
                        "confidence",
                        0
                    ) if field else 0,

                "evidence":
                    field.get(
                        "evidence"
                    ) if field else None,

                "reference":
                    rule["reference"]
            })


        # ----------------------------------------------
        # Nothing detected
        # ----------------------------------------------

        else:

            if rule.get(
                "required",
                False
            ):

                status = "REVIEW"

            else:

                status = "NOT_DETECTED"


            results.append({

                "id":
                    rule["id"],

                "name":
                    rule["name"],

                "status":
                    status,

                "message":
                    f'{rule["name"]} was not '
                    f'reliably detected.',

                "value":
                    None,

                "confidence":
                    0,

                "evidence":
                    None,

                "reference":
                    rule["reference"]
            })


    return results


def summary(results):

    total = len(results)

    detected = sum(

        1

        for result in results

        if result["status"]
        == "DETECTED"
    )

    review = sum(

        1

        for result in results

        if result["status"]
        == "REVIEW"
    )

    not_detected = sum(

        1

        for result in results

        if result["status"]
        == "NOT_DETECTED"
    )


    # This is deliberately NOT called
    # a legal compliance percentage.

    detection_score = (

        round(
            detected /
            total *
            100
        )

        if total

        else 0
    )


    if review > 0:

        overall = "REVIEW REQUIRED"

    elif not_detected > 0:

        overall = "INCOMPLETE SCREENING"

    else:

        overall = "SCREENING COMPLETE"


    return {

        "total":
            total,

        "detected":
            detected,

        "review":
            review,

        "not_detected":
            not_detected,

        "detection_score":
            detection_score,

        "overall":
            overall
    }
