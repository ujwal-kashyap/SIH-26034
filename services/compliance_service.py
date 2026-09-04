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

        status = field_status(
            field
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
