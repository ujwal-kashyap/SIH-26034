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

    if value in labels:
        return True

    # FIX: fuzzy match for the FSSAI logo, which OCR frequently
    # misreads as "Jssai", "Lssai", "Essai", etc. because of its
    # stylised font. Without this, a misread logo line could
    # leak into any field that uses is_label_only() to filter
    # candidate values (MRP, quantity, manufacturer, country...),
    # not just address.
    if re.fullmatch(r"[a-z]ssai\.?", value):
        return True

    # FIX: "LIC NO" / "LIC. NO." / "LICENCE NO" with no number
    # attached is a label, not a value.
    if re.fullmatch(r"lic\.?\s*no\.?|licen[cs]e\s*no\.?", value):
        return True

    return False


# ============================================================
# MRP
# ============================================================

def extract_mrp(items):

    # Same-line MRP.
    #
    # FIX: this previously also matched a bare "RS ..." or
    # "INR ..." pattern with no requirement that the word "MRP"
    # appear anywhere on the line. That's too generic -- it
    # matches the FIRST Rs-prefixed number anywhere in the
    # document, including an unrelated declaration like
    # "Unit Sale Price: Rs 0.50 per g" if that line happens to
    # be scanned before the real MRP fallback below gets a
    # chance to run. Verified this caused a real wrong-field
    # extraction (MRP came back as the unit price) on a layout
    # where MRP's value was split onto its own line ("MRP" /
    # ": 30.00") while Unit Sale Price appeared as a single Rs-
    # prefixed line shortly after. Removed the bare RS/INR
    # patterns entirely; the label-anchored pattern below and
    # the get_value_after_label() fallback are sufficient and
    # can't be confused by an unrelated currency value elsewhere.
    for item in items:

        text = item["text"]

        pattern = (
            r"\bMRP\b\s*(?:RS\.?|INR)?\s*[₹]?\s*"
            r"(\d+(?:\.\d{1,2})?)"
        )

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

    # --------------------------------------------------------
    # FIX: fallback for MRP label and value split across
    # separate OCR boxes, e.g.:
    #   MRP
    #   : 25.00
    # This is common on real packaging where the label and
    # its value are printed with enough horizontal/vertical
    # gap that the OCR text detector groups them as two
    # separate lines even though a human reads them as one
    # declaration. Mirrors the existing fallback pattern
    # already used by extract_manufacturer / extract_address.
    # --------------------------------------------------------

    return get_value_after_label(
        items,
        label_patterns=[r"\bMRP\b"],
        value_patterns=[
            r"((?:RS\.?|INR)?\s*[₹]?\s*\d+(?:\.\d{1,2})?)"
        ]
    )


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

    # --------------------------------------------------------
    # FIX: fallback for Net Quantity label and value split
    # across separate OCR boxes, e.g.:
    #   NET QUANTITY
    #   : 45 g
    # See extract_mrp() above for why this happens.
    # --------------------------------------------------------

    return get_value_after_label(
        items,
        label_patterns=[r"(?:NET\s*)?(?:QUANTITY|WEIGHT|WT)\b"],
        value_patterns=[
            r"(\d+(?:\.\d+)?\s*(?:KG|G|GM|MG|ML|L))\b"
        ]
    )


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
        r"MARKETED\s+BY",
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
                r"MARKETED\s+BY|"
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

# FIX: address extraction is now tried against two label
# groups, in priority order, instead of only ever looking for
# a "Registered Office"-style label. Many real packages (seen
# across different brands/layouts) print only a single
# "Manufactured by:" / "Manufactured & Marketed by:" address
# block with no separate registered-office section at all --
# under the old code, extract_address() returned NOT_DETECTED
# on those packages even though a perfectly good address was
# printed right there under a different label.
ADDRESS_LABEL_GROUPS = [
    # Preferred: an explicit registered-office / address block.
    [
        r"REGISTERED\s+OFFICE",
        r"REGISTERED\s+ADDRESS",
        r"\bADDRESS\b",
        r"FACTORY",
    ],
    # Fallback: no separate registered-office section exists --
    # use the manufacturer's own address block instead.
    [
        r"MANUFACTURED\s*(?:&|AND)\s*MARKETED\s*BY",
        r"MANUFACTURED\s+BY",
        r"MANUFACTURER",
        r"MARKETED\s+BY",
        r"PACKED\s+BY",
        r"PACKER",
        r"IMPORTED\s+BY",
        r"IMPORTER",
    ],
]


def extract_address(items):

    for label_patterns in ADDRESS_LABEL_GROUPS:

        result = _extract_address_for_labels(
            items,
            label_patterns
        )

        if result["status"] != "NOT_DETECTED":
            return result

    return not_detected()


def _extract_address_for_labels(items, label_patterns):

    index, match, item = find_line(
        items,
        label_patterns
    )

    if item is None:
        return not_detected()

    # --------------------------------------------------------
    # Find the actual beginning of the address.
    # Ignore OCR lines belonging to nutrition table.
    # --------------------------------------------------------

    address_start = None

    for j in range(index + 1, min(index + 10, len(items))):

        text = clean(items[j]["text"])

        if not text:
            continue

        # Ignore nutrition labels and their values
        if is_nutrition_line(text):
            continue

        if re.fullmatch(
            r"\d+(?:\.\d+)?",
            text
        ):
            continue

        # Company name immediately after REGISTERED OFFICE
        # is valid, but don't start collecting it until
        # actual address information appears.
        #
        # FIX: this previously also matched bare city/state/
        # country words (INDIA, HARYANA, GURUGRAM, ...), which
        # can appear *inside a company name itself* -- e.g.
        # "PepsiCo India Holdings Pvt. Ltd." contains "India",
        # which wrongly identified the company-name line as the
        # start of the address instead of the actual street
        # address on the next line. Two changes fix this
        # generally, not just for this one company name:
        #   1. Removed bare city/state/country words from the
        #      trigger list -- rely on structural address
        #      vocabulary instead (plot/sector/road/floor/etc,
        #      or a 6-digit PIN code), which genuine address
        #      lines reliably contain and company names don't.
        #   2. Added an explicit company-name guard so that even
        #      if a structural word coincidentally appears in a
        #      company name, that line is still never accepted
        #      as the address start.
        if (
            re.search(
                r"\b(?:PLOT|NO\.?|SECTOR|ROAD|RD|STREET|ST|"
                r"FLOOR|TOWER|BUILDING|PARK|LANE|VILLAGE|"
                r"NAGAR|SURVEY|PIN|"
                r"\d{6})\b",
                text,
                re.IGNORECASE
            )
            and not looks_like_company(text)
        ):
            address_start = j
            break

    if address_start is None:
        return not_detected()

    # --------------------------------------------------------
    # Collect address lines from the actual address start.
    # --------------------------------------------------------

    address_parts = []

    for j in range(
        address_start,
        min(address_start + 6, len(items))
    ):

        text = clean(items[j]["text"])

        if not text:
            continue

        # Stop when another declaration section begins.
        # (This is the single, canonical stop-check -- see the
        # FIX note on starts_new_section() below for why the
        # old second/duplicate regex here was removed.)
        if starts_new_section(text):
            break

        if is_nutrition_line(text):
            continue

        # Never include pure numeric nutrition values
        if re.fullmatch(
            r"\d+(?:\.\d+)?",
            text
        ):
            continue

        address_parts.append({
            "text": text,
            "confidence": items[j]["confidence"]
        })

    if not address_parts:
        return not_detected()

    value = " ".join(
        part["text"]
        for part in address_parts
    )

    confidence = min(
        part["confidence"]
        for part in address_parts
    )

    return make_field(
        value,
        confidence,
        f"{item['text']} -> {value}"
    )
def starts_new_section(text):
    """
    Detects whether a line marks the start of a new
    declaration/section, so multi-line collectors (like
    extract_address) know where to stop.

    FIX: this previously did a plain substring check against a
    fixed label list, which missed two real cases seen in OCR
    output:

    1. "LIC NO" / "LIC. NO." was not in the list at all, so a
       line like "Lic. No. 10018064001234" was treated as more
       address text instead of a new section.

    2. The FSSAI logo is a heavily stylised wordmark, and OCR
       very commonly misreads it as "Jssai", "Lssai", "Essai",
       etc. (a single leading letter + "SSAI"). Matching only
       the literal string "FSSAI" missed these misreads
       entirely, so "Jssai" was being appended to the address
       as if it were ordinary text.

    Now uses regex patterns (including a fuzzy pattern for the
    FSSAI logo) instead of exact substrings.
    """

    upper = text.upper()

    section_patterns = [
        r"NUTRITIONAL\s+INFORMATION",
        r"(?:CONSUMER|CUSTOMER)\s+CARE",
        r"COUNTRY\s+OF\s+ORIGIN",
        r"UNIT\s+(?:SALE|SELLING)\s+PRICE",
        r"\bMRP\b",
        r"NET\s+(?:QUANTITY|WEIGHT|WT)\b",
        r"\bINGREDIENTS\b",
        r"BATCH\s*NO",
        r"\bMFG\b",
        r"\bMFD\b",
        r"USE\s+BY",
        r"BEST\s+BEFORE",
        r"EXPIR(?:Y|ATION)",

        # FIX: "LIC NO" / "LIC. NO." was missing entirely.
        r"LIC\s*\.?\s*NO",
        r"LICEN[CS]E\s+NO",

        # FIX: fuzzy match for the FSSAI logo -- catches common
        # OCR misreads (JSSAI, LSSAI, ESSAI, ...), not just the
        # literal string "FSSAI".
        r"\b[A-Z]SSAI\b",

        r"MADE\s+IN\b",
        r"PRODUCT\s+OF\b",

        # A second "REGISTERED OFFICE" / "ADDRESS" style label
        # showing up mid-collection means we've wandered into an
        # unrelated block -- also treat it as a new section.
        r"REGISTERED\s+OFFICE",
        r"REGISTERED\s+ADDRESS",

        # FIX: a second manufacturer/marketer-style label (e.g.
        # a package that prints "Manufactured by: ... Mkt. by:
        # ..." as two separate address blocks) must also end
        # address collection, otherwise two unrelated addresses
        # get concatenated into one value.
        r"MANUFACTURED\s*(?:&|AND)?\s*MARKETED\s*BY",
        r"MANUFACTURED\s+BY",
        r"\bMARKETED\s+BY\b",
        r"\bMKT\.?\s*BY\b",
        r"PACKED\s+BY",
        r"IMPORTED\s+BY",
    ]

    return any(
        re.search(pattern, upper)
        for pattern in section_patterns
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
    # 1. Explicit commodity/product name label.
    #
    # FIX: broadened slightly to also accept "ITEM NAME" and
    # "COMMODITY NAME" (both seen on real packaging as
    # alternate phrasings), while deliberately NOT matching a
    # bare "PRODUCT" -- that would collide with "PRODUCT OF
    # INDIA" (a country-of-origin declaration, handled by
    # extract_country()), causing this field to wrongly harvest
    # a country name instead of a product name.
    # --------------------------------------------------------

    for item in items:

        text = item["text"]

        match = re.search(
            r"(?:PRODUCT\s+NAME|ITEM\s+NAME|"
            r"COMMODITY\s+NAME|COMMODITY)"
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
    # FIX: this function used to have two further fallback
    # steps:
    #
    #   2. A hardcoded check for standalone "POTATO" and
    #      "CHIPS" OCR lines, returning the literal string
    #      "POTATO CHIPS". This is a one-off rule for a single
    #      product and was removed -- it does not generalize to
    #      any other commodity, and hardcoding product-specific
    #      literals is exactly what this field must not do.
    #
    #   3. A "food word" keyword search across the first 12 OCR
    #      lines (POTATO, OIL, RICE, SALT, SUGAR...), returning
    #      whichever line matched. This had no way to tell a
    #      genuine product-name line apart from an ordinary
    #      sentence inside the INGREDIENTS list -- e.g. "Rice,
    #      Corn Grits, Edible Vegetable Oil" matched on "OIL"
    #      and was returned as the commodity name.
    #
    # Neither step generalizes across different package layouts,
    # and both can return confident-looking wrong answers. Per
    # the requirement that this field must return NOT_DETECTED
    # rather than guess, both are removed rather than patched --
    # only an explicit, unambiguous label (step 1 above) is
    # trusted as evidence of the actual product name.
    # --------------------------------------------------------

    return not_detected()


# ============================================================
# SHARED DATE FALLBACK
# ============================================================

def _find_date_near_label(items, label_pattern, max_lookahead=3):
    """
    Fallback for date declarations where the label and the date
    are detected as separate OCR lines/boxes, e.g.:
        MFG. DATE
        : 20/06/2024

    FIX: previously extract_manufacturing_date() and
    extract_best_before() each hand-rolled their own version of
    this, and each only covered PART of its own label set (the
    manufacturing-date fallback only matched "MFG/MFD", not
    "DATE OF MANUFACTURE"/"PACKED ON"; the best-before fallback
    only matched "USE BY", not "BEST BEFORE"/"EXPIRY"/
    "EXP DATE"). So a package printing e.g. "BEST BEFORE" on
    one line and the date on the next would silently fail even
    though the near-identical "USE BY" case worked. This shared
    helper is used by both functions against their FULL label
    set, so the split-label-and-value layout is handled
    consistently everywhere it can occur.
    """

    for i, item in enumerate(items):

        if re.search(
            label_pattern,
            item["text"],
            re.IGNORECASE
        ):

            for j in range(
                i + 1,
                min(i + 1 + max_lookahead, len(items))
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

    # FIX: fallback now covers the same full label set as the
    # same-line patterns above (MFG/MFD, DATE OF MANUFACTURE,
    # DATE OF PACKING, PACKED ON), not just MFG/MFD.
    return _find_date_near_label(
        items,
        r"\b(?:MFG|MFD|DATE\s+OF\s+MANUFACTURE|"
        r"DATE\s+OF\s+PACKING|PACKED\s+ON)\b"
    )


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

    # FIX: fallback now covers the same full label set as the
    # same-line patterns above (BEST BEFORE, USE BY, EXPIRY,
    # EXP DATE, EXPIRATION), not just USE BY.
    return _find_date_near_label(
        items,
        r"\b(?:BEST\s+BEFORE|USE\s+BY|EXPIRY|"
        r"EXP\.?\s*DATE|EXPIRATION)\b"
    )


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

    # --------------------------------------------------------
    # FIX: fallback for label and licence number split across
    # separate OCR boxes, e.g.:
    #   FSSAI Lic No:
    #   10014064000435
    # Unlike MRP/quantity/dates, this extractor previously had
    # NO fallback at all for this layout variation.
    # --------------------------------------------------------

    return get_value_after_label(
        items,
        label_patterns=[
            r"\b[A-Za-z]SSAI\b",
            r"LIC\s*\.?\s*NO"
        ],
        value_patterns=[
            r"(\d{10,14})"
        ]
    )


# ============================================================
# CONSUMER CARE
# ============================================================

def extract_consumer_care(items):

    # FIX: real packages word this label many different ways --
    # "Consumer Care", "For Consumer Complaints, contact",
    # "For any feedback/complaint", "Consumer Helpline",
    # "Toll Free" -- not just the literal phrase
    # "Consumer/Customer Care". The phone-search branches below
    # previously required that exact phrase, so a package using
    # any of these other common phrasings (with no email
    # present) fell through to NOT_DETECTED even though a phone
    # number was clearly printed under a consumer-contact
    # heading.
    consumer_label_pattern = (
        r"(?:CUSTOMER|CONSUMER)\s*"
        r"(?:CARE|COMPLAINTS?|FEEDBACK|HELPLINE|SERVICES?)"
        r"|TOLL[\s\-]*FREE"
    )

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
            consumer_label_pattern,
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
            consumer_label_pattern,
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

                # FIX: this used to require a currency symbol
                # (RS/INR/₹) somewhere in the candidate line. Real
                # packaging commonly prints unit price as a bare
                # decimal + "per g"/"per ml" with no repeated
                # currency marker (it's already established by the
                # MRP line above). Broadened to also accept a bare
                # number followed by a "per <unit>" or "/<unit>"
                # suffix -- specific enough that it can't be
                # confused with an unrelated number (a batch code
                # or date won't match "per g"/"/ml" etc.).
                has_currency_marker = re.search(
                    r"(?:RS|INR|₹)"
                    r".*\d+",
                    candidate,
                    re.IGNORECASE
                )

                has_bare_per_unit_value = re.search(
                    r"\d+(?:\.\d+)?\s*(?:PER|/)\s*"
                    r"(?:100\s*)?(?:G|GM|KG|ML|L)\b",
                    candidate,
                    re.IGNORECASE
                )

                if has_currency_marker or has_bare_per_unit_value:

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