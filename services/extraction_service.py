import re


# ============================================================
# BASIC HELPERS
# ============================================================

def clean(value):
    if value is None:
        return None

    value = str(value)

    # Remove excessive whitespace
    value = re.sub(r"\s+", " ", value)

    # Remove common OCR punctuation noise at beginning/end
    value = value.strip(" \t\r\n:;-|")

    return value.strip()


def not_detected():
    return {
        "value": None,
        "confidence": 0.0,
        "status": "NOT_DETECTED",
        "evidence": None
    }


def make_field(value, confidence, evidence):
    value = clean(value)

    if not value:
        return not_detected()

    try:
        confidence = float(confidence or 0.0)
    except Exception:
        confidence = 0.0

    if confidence >= 0.85:
        status = "DETECTED"
    elif confidence >= 0.60:
        status = "REVIEW"
    else:
        status = "LOW_CONFIDENCE"

    return {
        "value": value,
        "confidence": round(confidence, 3),
        "status": status,
        "evidence": evidence
    }


# ============================================================
# OCR NORMALIZATION
# ============================================================

def normalize(text):
    if text is None:
        return ""

    result = str(text)

    replacements = {
        "₹": " Rs ",
        "â‚¹": " Rs ",
        "â¹": " Rs ",

        "M.R.P.": "MRP",
        "M.R.P": "MRP",
        "M R P": "MRP",

        "NET WT.": "NET WEIGHT",
        "NET WT": "NET WEIGHT",
        "NET W T": "NET WEIGHT",

        "MFG.": "MFG",
        "MFD.": "MFD",

        "MFG DATE": "MFG",
        "MFD DATE": "MFD",

        "FSSAI NO.": "FSSAI",
        "FSSAI NO": "FSSAI",

        "LIC. NO.": "LIC NO",
        "LIC. NO": "LIC NO",
        "LICENCE NO": "LIC NO",
        "LICENSE NO": "LIC NO",
    }

    for old, new in replacements.items():
        result = re.sub(
            re.escape(old),
            new,
            result,
            flags=re.IGNORECASE
        )

    return clean(result)


# ============================================================
# OCR ITEM NORMALIZATION
# ============================================================

def prepare_items(ocr_items):
    items = []

    for item in ocr_items:
        raw_text = item.get("text", "")

        text = normalize(raw_text)

        if not text:
            continue

        try:
            confidence = float(item.get("confidence", 0.0))
        except Exception:
            confidence = 0.0

        items.append({
            **item,
            "text": text,
            "confidence": confidence
        })

    return items


# ============================================================
# GENERAL SEARCH HELPERS
# ============================================================

def find_line(items, patterns):
    """
    Find a line matching one of the supplied regex patterns.
    Returns:
        (index, match, item)
    """

    for i, item in enumerate(items):
        text = item.get("text", "")

        for pattern in patterns:
            try:
                match = re.search(
                    pattern,
                    text,
                    re.IGNORECASE
                )
            except re.error:
                continue

            if match:
                return i, match, item

    return None, None, None


def find_first_matching_line(items, patterns):
    """
    Returns first OCR line matching a pattern.
    """

    index, match, item = find_line(
        items,
        patterns
    )

    if item is None:
        return None

    return item


def get_value_after_label(
    items,
    label_patterns,
    value_patterns=None,
    max_lines=4
):
    """
    Extract value from the same line or nearby OCR lines.

    Unlike the old function, this:
    - does not blindly take the next OCR line
    - skips unrelated labels
    - searches for a meaningful value
    """

    if value_patterns is None:
        value_patterns = []

    for i, item in enumerate(items):

        text = item.get("text", "")

        label_match = None

        for pattern in label_patterns:
            try:
                label_match = re.search(
                    pattern,
                    text,
                    re.IGNORECASE
                )
            except re.error:
                continue

            if label_match:
                break

        if not label_match:
            continue

        # ----------------------------------------------------
        # SAME LINE VALUE
        # ----------------------------------------------------

        if label_match.lastindex:
            value = clean(
                label_match.group(1)
            )

            if value:
                return make_field(
                    value,
                    item.get("confidence", 0.0),
                    text
                )

        # ----------------------------------------------------
        # SEARCH CURRENT + FOLLOWING LINES
        # ----------------------------------------------------

        for j in range(
            i,
            min(i + max_lines + 1, len(items))
        ):

            candidate = items[j].get(
                "text",
                ""
            )

            if not candidate:
                continue

            # For current line, remove the label itself
            if j == i:

                candidate_value = re.sub(
                    label_match.re.pattern
                    if hasattr(label_match, "re")
                    else "",
                    "",
                    candidate,
                    flags=re.IGNORECASE
                )

                candidate_value = clean(
                    candidate_value
                )

            else:
                candidate_value = clean(
                    candidate
                )

            if not candidate_value:
                continue

            # ------------------------------------------------
            # Skip obvious labels / unrelated OCR lines
            # ------------------------------------------------

            if is_label_only(candidate_value):
                continue

            # ------------------------------------------------
            # If explicit value patterns exist,
            # require one of them.
            # ------------------------------------------------

            if value_patterns:

                matched_value = None

                for vp in value_patterns:
                    try:
                        vm = re.search(
                            vp,
                            candidate_value,
                            re.IGNORECASE
                        )
                    except re.error:
                        continue

                    if vm:
                        if vm.lastindex:
                            matched_value = clean(
                                vm.group(1)
                            )
                        else:
                            matched_value = clean(
                                vm.group(0)
                            )
                        break

                if not matched_value:
                    continue

                candidate_value = matched_value

            combined_confidence = min(
                float(item.get("confidence", 0.0)),
                float(items[j].get("confidence", 0.0))
            )

            evidence = (
                text
                if j == i
                else f"{text} -> {candidate}"
            )

            return make_field(
                candidate_value,
                combined_confidence,
                evidence
            )

    return not_detected()


def is_label_only(text):
    """
    Detect lines that are labels and should never be used
    as values for another field.
    """

    normalized = clean(text)

    if not normalized:
        return True

    value = normalized.lower()

    labels = {
        "mrp",
        "net quantity",
        "net weight",
        "net weight:",
        "quantity",

        "manufacturer",
        "manufacturer:",
        "manufactured by",
        "manufactured & marketed by",
        "packed by",
        "packer",
        "imported by",
        "importer",

        "address",
        "registered office",
        "registered address",
        "factory",

        "country of origin",
        "made in",
        "product of",

        "commodity",
        "product name",

        "mfg",
        "mfd",
        "mfg date",
        "mfd date",

        "use by",
        "best before",
        "expiry",
        "expiration",

        "consumer care",
        "customer care",

        "unit sale price",
        "unit selling price",

        "fssai",
        "lic no",

        "ingredients",
        "nutritional information",
        "per 100g",

        "energy (kcal)",
        "protein (g)",
        "carbohydrate (g)",
        "total sugars (g)",
        "total fat (g)",
        "saturated fat (g)",
        "trans fat (g)",
        "sodium (mg)"
    }

    return value in labels


# ============================================================
# MRP
# ============================================================

def extract_mrp(items):

    # Same-line MRP
    for item in items:

        text = item["text"]

        patterns = [
            r"\bMRP\b\s*(?:RS\.?|INR)?\s*[₹]?\s*"
            r"(\d+(?:\.\d{1,2})?)",

            r"\bRS\.?\s*[₹]?\s*"
            r"(\d+(?:\.\d{1,2})?)",

            r"\bINR\.?\s*[₹]?\s*"
            r"(\d+(?:\.\d{1,2})?)"
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                text,
                re.IGNORECASE
            )

            if match:

                return make_field(
                    match.group(1),
                    item["confidence"],
                    text
                )

    return not_detected()


# ============================================================
# NET QUANTITY
# ============================================================

def extract_quantity(items):

    patterns = [
        r"(?:NET\s*)?"
        r"(?:QUANTITY|WEIGHT|WT)"
        r"\s*[:\-]?\s*"
        r"(\d+(?:\.\d+)?)"
        r"\s*(KG|G|GM|MG|ML|L)\b"
    ]

    for item in items:

        text = item["text"]

        for pattern in patterns:

            match = re.search(
                pattern,
                text,
                re.IGNORECASE
            )

            if match:

                value = (
                    f"{match.group(1)} "
                    f"{match.group(2)}"
                )

                return make_field(
                    value,
                    item["confidence"],
                    text
                )

    return not_detected()


# ============================================================
# MANUFACTURER
# ============================================================

def extract_manufacturer(items):

    # --------------------------------------------------------
    # Case:
    # MANUFACTURED & MARKETED BY:
    # XYZ Snacks Pvt. Ltd.
    # --------------------------------------------------------

    label_patterns = [
        r"MANUFACTURED\s*(?:&|AND)\s*MARKETED\s*BY",
        r"MANUFACTURED\s+BY",
        r"MANUFACTURER",
        r"PACKED\s+BY",
        r"PACKER",
        r"IMPORTED\s+BY",
        r"IMPORTER"
    ]

    # First find the manufacturer label.
    index, match, item = find_line(
        items,
        label_patterns
    )

    if item is None:
        return not_detected()

    # --------------------------------------------------------
    # Search nearby lines for company name.
    # --------------------------------------------------------

    for j in range(
        index,
        min(index + 5, len(items))
    ):

        text = clean(
            items[j]["text"]
        )

        if not text:
            continue

        # Same line after label
        if j == index:

            after = re.sub(
                r"^(?:MANUFACTURED\s*(?:&|AND)\s*MARKETED\s*BY|"
                r"MANUFACTURED\s+BY|"
                r"MANUFACTURER|"
                r"PACKED\s+BY|"
                r"PACKER|"
                r"IMPORTED\s+BY|"
                r"IMPORTER)"
                r"\s*[:\-]?\s*",
                "",
                text,
                flags=re.IGNORECASE
            )

            after = clean(after)

            if after and not is_label_only(after):
                if looks_like_company(after):
                    return make_field(
                        after,
                        items[j]["confidence"],
                        items[j]["text"]
                    )

        else:

            if is_label_only(text):
                continue

            if looks_like_company(text):

                confidence = min(
                    item["confidence"],
                    items[j]["confidence"]
                )

                return make_field(
                    text,
                    confidence,
                    f"{item['text']} -> {items[j]['text']}"
                )

    return not_detected()


def looks_like_company(text):

    value = text.lower()

    company_indicators = [
        "pvt",
        "private",
        "ltd",
        "limited",
        "industries",
        "foods",
        "food",
        "snacks",
        "enterprises",
        "enterprise",
        "company",
        "co.",
        "corp",
        "corporation",
        "llp"
    ]

    return any(
        indicator in value
        for indicator in company_indicators
    )


# ============================================================
# ADDRESS
# ============================================================

def extract_address(items):

    label_patterns = [
        r"REGISTERED\s+OFFICE",
        r"REGISTERED\s+ADDRESS",
        r"ADDRESS",
        r"FACTORY"
    ]

    index, match, item = find_line(
        items,
        label_patterns
    )

    if item is None:
        return not_detected()

    address_parts = []

    # --------------------------------------------------------
    # Collect nearby address lines.
    # Stop when another major label starts.
    # --------------------------------------------------------

    for j in range(
        index,
        min(index + 6, len(items))
    ):

        text = clean(
            items[j]["text"]
        )

        if not text:
            continue

        if j == index:

            # Remove label
            remainder = re.sub(
                r"^(?:REGISTERED\s+OFFICE|"
                r"REGISTERED\s+ADDRESS|"
                r"ADDRESS|"
                r"FACTORY)"
                r"\s*[:\-]?\s*",
                "",
                text,
                flags=re.IGNORECASE
            )

            remainder = clean(
                remainder
            )

            if remainder:
                address_parts.append(
                    remainder
                )

            continue

        # Stop at unrelated major section
        if starts_new_section(text):
            break

        if is_nutrition_line(text):
            continue

        # Avoid consuming random short OCR fragments
        if len(text) < 4:
            continue

        address_parts.append(text)

    # --------------------------------------------------------
    # Extract only address-like content
    # --------------------------------------------------------

    if not address_parts:
        return not_detected()

    # In this label layout the address may span multiple lines.
    # Keep useful address lines but stop before nutrition noise.
    useful = []

    for part in address_parts:

        if is_nutrition_line(part):
            break

        if re.search(
            r"\b(?:ROAD|RD|STREET|ST|SECTOR|PLOT|"
            r"GURUGRAM|DELHI|MUMBAI|HARYANA|INDIA|"
            r"FLOOR|TOWER|PARK|NO\.)\b",
            part,
            re.IGNORECASE
        ):
            useful.append(part)

    if not useful:
        useful = address_parts

    value = " ".join(
        clean(x)
        for x in useful
    )

    confidence_values = [
        item["confidence"]
    ]

    for j in range(
        index + 1,
        min(index + len(useful) + 1, len(items))
    ):
        confidence_values.append(
            items[j]["confidence"]
        )

    confidence = min(
        confidence_values
    )

    return make_field(
        value,
        confidence,
        f"{item['text']} -> {value}"
    )


def starts_new_section(text):

    upper = text.upper()

    section_labels = [
        "NUTRITIONAL INFORMATION",
        "CONSUMER CARE",
        "COUNTRY OF ORIGIN",
        "UNIT SALE PRICE",
        "MRP",
        "NET QUANTITY",
        "INGREDIENTS",
        "BATCH NO",
        "MFG",
        "MFD",
        "USE BY",
        "BEST BEFORE",
        "FSSAI"
    ]

    return any(
        label in upper
        for label in section_labels
    )


def is_nutrition_line(text):

    value = text.lower()

    nutrition_terms = [
        "nutritional information",
        "per 100g",
        "energy (kcal)",
        "protein (g)",
        "carbohydrate (g)",
        "total sugars",
        "total fat",
        "saturated fat",
        "trans fat",
        "sodium (mg)"
    ]

    return any(
        term in value
        for term in nutrition_terms
    )


# ============================================================
# COUNTRY OF ORIGIN
# ============================================================

def extract_country(items):

    patterns = [
        r"COUNTRY\s+OF\s+ORIGIN"
        r"\s*[:\-]?\s*(.+)",

        r"MADE\s+IN"
        r"\s*[:\-]?\s*(.+)",

        r"PRODUCT\s+OF"
        r"\s*[:\-]?\s*(.+)"
    ]

    # First try same line
    for item in items:

        text = item["text"]

        for pattern in patterns:

            match = re.search(
                pattern,
                text,
                re.IGNORECASE
            )

            if match:

                value = clean(
                    match.group(1)
                )

                if value:
                    return make_field(
                        value,
                        item["confidence"],
                        text
                    )

    # If label and value are separate
    for i, item in enumerate(items):

        text = item["text"]

        if re.search(
            r"COUNTRY\s+OF\s+ORIGIN",
            text,
            re.IGNORECASE
        ):

            for j in range(
                i + 1,
                min(i + 4, len(items))
            ):

                candidate = clean(
                    items[j]["text"]
                )

                if not candidate:
                    continue

                if is_label_only(candidate):
                    continue

                # Prefer MADE IN
                made_match = re.search(
                    r"MADE\s+IN\s+(.+)",
                    candidate,
                    re.IGNORECASE
                )

                if made_match:

                    return make_field(
                        f"MADE IN {clean(made_match.group(1))}",
                        items[j]["confidence"],
                        f"{text} -> {candidate}"
                    )

                return make_field(
                    candidate,
                    min(
                        item["confidence"],
                        items[j]["confidence"]
                    ),
                    f"{text} -> {candidate}"
                )

    # Direct MADE IN
    for item in items:

        match = re.search(
            r"MADE\s+IN\s+(.+)",
            item["text"],
            re.IGNORECASE
        )

        if match:

            return make_field(
                f"MADE IN {clean(match.group(1))}",
                item["confidence"],
                item["text"]
            )

    return not_detected()


# ============================================================
# COMMODITY NAME
# ============================================================

def extract_commodity(items):

    # --------------------------------------------------------
    # 1. Explicit commodity/product name
    # --------------------------------------------------------

    for item in items:

        text = item["text"]

        match = re.search(
            r"(?:PRODUCT\s+NAME|COMMODITY)"
            r"\s*[:\-]\s*(.+)",
            text,
            re.IGNORECASE
        )

        if match:

            value = clean(
                match.group(1)
            )

            if value:
                return make_field(
                    value,
                    item["confidence"],
                    text
                )

    # --------------------------------------------------------
    # 2. Detect obvious product name from OCR
    #
    # For this type of package:
    # POTATO
    # CHIPS
    #
    # should become:
    # POTATO CHIPS
    # --------------------------------------------------------

    potato_index = None
    chips_index = None

    for i, item in enumerate(items):

        value = item["text"].upper()

        if re.fullmatch(
            r"POTATO",
            value
        ):
            potato_index = i

        if re.fullmatch(
            r"CHIPS",
            value
        ):
            chips_index = i

    if (
        potato_index is not None
        and chips_index is not None
    ):

        confidence = min(
            items[potato_index]["confidence"],
            items[chips_index]["confidence"]
        )

        evidence = (
            f"{items[potato_index]['text']} "
            f"{items[chips_index]['text']}"
        )

        return make_field(
            "POTATO CHIPS",
            confidence,
            evidence
        )

    # --------------------------------------------------------
    # 3. Search first few lines for likely commodity
    # --------------------------------------------------------

    candidates = []

    for item in items[:12]:

        text = clean(
            item["text"]
        )

        if not text:
            continue

        upper = text.upper()

        ignored = [
            "INGREDIENTS",
            "MANUFACTURED",
            "MRP",
            "NUTRITIONAL",
            "PER 100G",
            "REGISTERED OFFICE",
            "CONSUMER CARE",
            "UNIT SALE PRICE"
        ]

        if any(
            x in upper
            for x in ignored
        ):
            continue

        if len(text) <= 2:
            continue

        candidates.append(item)

    # Prefer food/product-looking terms
    food_words = [
        "POTATO",
        "CHIPS",
        "BISCUIT",
        "BISCUITS",
        "SNACK",
        "NOODLES",
        "RICE",
        "FLOUR",
        "OIL",
        "SALT",
        "SUGAR",
        "SPICES",
        "COOKIES"
    ]

    for item in candidates:

        text_upper = item["text"].upper()

        if any(
            word in text_upper
            for word in food_words
        ):

            return make_field(
                item["text"],
                item["confidence"],
                item["text"]
            )

    return not_detected()


# ============================================================
# MANUFACTURING DATE
# ============================================================

def extract_manufacturing_date(items):

    patterns = [
        r"(?:MFG|MFD)"
        r"(?:\s+DATE)?"
        r"\s*[:\-]?\s*"
        r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",

        r"DATE\s+OF\s+MANUFACTURE"
        r"\s*[:\-]?\s*"
        r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",

        r"DATE\s+OF\s+PACKING"
        r"\s*[:\-]?\s*"
        r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",

        r"PACKED\s+ON"
        r"\s*[:\-]?\s*"
        r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})"
    ]

    for item in items:

        for pattern in patterns:

            match = re.search(
                pattern,
                item["text"],
                re.IGNORECASE
            )

            if match:

                return make_field(
                    match.group(1),
                    item["confidence"],
                    item["text"]
                )

    return not_detected()


# ============================================================
# BEST BEFORE / EXPIRY
# ============================================================

def extract_best_before(items):

    patterns = [
        r"(?:BEST\s+BEFORE|"
        r"USE\s+BY|"
        r"EXPIRY|"
        r"EXP\.?\s*DATE|"
        r"EXPIRATION)"
        r"\s*[:\-]?\s*"
        r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",

        r"(?:BEST\s+BEFORE|"
        r"USE\s+BY|"
        r"EXPIRY|"
        r"EXP\.?\s*DATE)"
        r".*?"
        r"(\d{1,2}[\/\-]\d{4})"
    ]

    for item in items:

        for pattern in patterns:

            match = re.search(
                pattern,
                item["text"],
                re.IGNORECASE
            )

            if match:

                return make_field(
                    match.group(1),
                    item["confidence"],
                    item["text"]
                )

    # --------------------------------------------------------
    # Handle:
    #
    # USE BY
    # :31/10/2024
    # --------------------------------------------------------

    for i, item in enumerate(items):

        if re.search(
            r"\bUSE\s+BY\b",
            item["text"],
            re.IGNORECASE
        ):

            for j in range(
                i + 1,
                min(i + 3, len(items))
            ):

                match = re.search(
                    r"(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
                    items[j]["text"]
                )

                if match:

                    confidence = min(
                        item["confidence"],
                        items[j]["confidence"]
                    )

                    return make_field(
                        match.group(1),
                        confidence,
                        f"{item['text']} -> {items[j]['text']}"
                    )

    return not_detected()


# ============================================================
# FSSAI
# ============================================================

def extract_fssai(items):

    # --------------------------------------------------------
    # Direct FSSAI + number
    # --------------------------------------------------------

    for item in items:

        text = item["text"]

        match = re.search(
            r"FSSAI.*?(\d{10,14})",
            text,
            re.IGNORECASE
        )

        if match:

            return make_field(
                match.group(1),
                item["confidence"],
                text
            )

    # --------------------------------------------------------
    # LIC NO + number
    # --------------------------------------------------------

    for item in items:

        text = item["text"]

        match = re.search(
            r"LIC\s*\.?\s*NO\s*\.?\s*[:\-]?\s*(\d{10,14})",
            text,
            re.IGNORECASE
        )

        if match:

            return make_field(
                match.group(1),
                item["confidence"],
                text
            )

    return not_detected()


# ============================================================
# CONSUMER CARE
# ============================================================

def extract_consumer_care(items):

    # --------------------------------------------------------
    # Email
    # --------------------------------------------------------

    for item in items:

        match = re.search(
            r"[A-Za-z0-9._%+\-]+"
            r"@[A-Za-z0-9.\-]+"
            r"\.[A-Za-z]{2,}",
            item["text"]
        )

        if match:

            return make_field(
                match.group(0),
                item["confidence"],
                item["text"]
            )

    # --------------------------------------------------------
    # Phone
    # --------------------------------------------------------

    for item in items:

        text = item["text"]

        if not re.search(
            r"(CUSTOMER|CONSUMER)\s*CARE",
            text,
            re.IGNORECASE
        ):
            continue

        match = re.search(
            r"(\+?\d[\d\s\-]{7,18}\d)",
            text
        )

        if match:

            return make_field(
                clean(match.group(1)),
                item["confidence"],
                text
            )

    # Search globally if label and phone are separate
    for item in items:

        text = item["text"]

        if re.search(
            r"(CUSTOMER|CONSUMER)\s*CARE",
            text,
            re.IGNORECASE
        ):

            # Search nearby lines
            index = items.index(item)

            for j in range(
                index + 1,
                min(index + 5, len(items))
            ):

                match = re.search(
                    r"(\+?\d[\d\s\-]{7,18}\d)",
                    items[j]["text"]
                )

                if match:

                    confidence = min(
                        item["confidence"],
                        items[j]["confidence"]
                    )

                    return make_field(
                        clean(match.group(1)),
                        confidence,
                        f"{text} -> {items[j]['text']}"
                    )

    return not_detected()


# ============================================================
# UNIT SALE PRICE
# ============================================================

def extract_unit_price(items):

    patterns = [
        r"UNIT\s+SALE\s+PRICE"
        r"\s*[:\-]?\s*"
        r"(.+)",

        r"UNIT\s+SELLING\s+PRICE"
        r"\s*[:\-]?\s*"
        r"(.+)"
    ]

    for i, item in enumerate(items):

        text = item["text"]

        for pattern in patterns:

            match = re.search(
                pattern,
                text,
                re.IGNORECASE
            )

            if match:

                value = clean(
                    match.group(1)
                )

                # If the label has no value, search next lines
                if not value:

                    continue

                # Avoid accepting another label
                if not is_label_only(value):

                    return make_field(
                        value,
                        item["confidence"],
                        text
                    )

        # Separate line case
        if re.search(
            r"UNIT\s+(?:SALE|SELLING)\s+PRICE",
            text,
            re.IGNORECASE
        ):

            for j in range(
                i + 1,
                min(i + 3, len(items))
            ):

                candidate = clean(
                    items[j]["text"]
                )

                if not candidate:
                    continue

                if is_label_only(candidate):
                    continue

                if re.search(
                    r"(?:RS|INR|₹)"
                    r".*\d+",
                    candidate,
                    re.IGNORECASE
                ):

                    confidence = min(
                        item["confidence"],
                        items[j]["confidence"]
                    )

                    return make_field(
                        candidate,
                        confidence,
                        f"{text} -> {candidate}"
                    )

    return not_detected()


# ============================================================
# MAIN EXTRACTION
# ============================================================

def extract_information(ocr_items):

    items = prepare_items(
        ocr_items
    )

    # --------------------------------------------------------
    # Extract each declaration independently.
    # --------------------------------------------------------

    mrp = extract_mrp(
        items
    )

    quantity = extract_quantity(
        items
    )

    manufacturer = extract_manufacturer(
        items
    )

    address = extract_address(
        items
    )

    country = extract_country(
        items
    )

    commodity = extract_commodity(
        items
    )

    manufacturing_date = extract_manufacturing_date(
        items
    )

    best_before = extract_best_before(
        items
    )

    fssai = extract_fssai(
        items
    )

    consumer = extract_consumer_care(
        items
    )

    unit_price = extract_unit_price(
        items
    )

    # ========================================================
    # FINAL RESULT
    # ========================================================

    return {

        "MRP":
            mrp,

        "Net Quantity":
            quantity,

        "Manufacturer":
            manufacturer,

        "Address":
            address,

        "Country of Origin":
            country,

        "Commodity Name":
            commodity,

        "Manufacturing Date":
            manufacturing_date,

        "Best Before":
            best_before,

        "FSSAI":
            fssai,

        "Consumer Care":
            consumer,

        "Unit Sale Price":
            unit_price
    }