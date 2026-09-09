
import os
import time

# Disable MKLDNN / oneDNN before importing PaddleOCR
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
os.environ["FLAGS_use_mkldnn"] = "0"

from paddleocr import PaddleOCR


def _env_flag(name, default):
    """
    Lets you tune OCR behaviour from the environment without
    touching code, e.g.:
        set OCR_USE_DOC_UNWARPING=false    (Windows)
        export OCR_USE_DOC_UNWARPING=false (Linux/Mac)
    """
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class OCRService:

    def __init__(self):

        print("Loading OCR model...", flush=True)

        self.engine = PaddleOCR(
            lang="en",
            device="cpu",

            # ------------------------------------------------------
            # SPEED: these three were all forced True earlier to
            # fix accuracy on curved/tilted real-world packaging.
            # That's still correct for bottles/jars, but
            # use_doc_unwarping in particular (a full deformable-
            # surface correction model) is by far the most
            # expensive of the three on CPU and is dead weight on
            # the flat pouches/boxes most packaged snacks use --
            # it was the main cause of slow (~26s) scans.
            #
            # Defaults below now prioritize speed:
            #   - use_doc_orientation_classify: kept ON. Cheap
            #     (one whole-image classification pass) and still
            #     catches upside-down/sideways photos.
            #   - use_doc_unwarping: now OFF by default. Re-enable
            #     with OCR_USE_DOC_UNWARPING=true if you're
            #     scanning curved surfaces (bottles, jars) and can
            #     afford the extra time.
            #   - use_textline_orientation: now OFF by default.
            #     Runs a classifier per detected text box, so cost
            #     scales with how much text is on the label. Re-
            #     enable with OCR_USE_TEXTLINE_ORIENTATION=true if
            #     your photos are often tilted.
            # ------------------------------------------------------
            use_doc_orientation_classify=_env_flag(
                "OCR_USE_DOC_ORIENTATION", True
            ),
            use_doc_unwarping=_env_flag(
                "OCR_USE_DOC_UNWARPING", False
            ),
            use_textline_orientation=_env_flag(
                "OCR_USE_TEXTLINE_ORIENTATION", False
            ),

            # Small PP-OCRv6 models (unchanged) -- already the
            # faster/lighter model variant.
            text_detection_model_name="PP-OCRv6_small_det",
            text_recognition_model_name="PP-OCRv6_small_rec",

            # SPEED: lowered from 1536 -> 1280. Still well above
            # the original 960 (so small print like the FSSAI
            # number stays legible), but cheaper to run. Raise via
            # OCR_DET_LIMIT_SIDE_LEN if you see small text being
            # missed again.
            text_det_limit_side_len=int(
                os.environ.get("OCR_DET_LIMIT_SIDE_LEN", "1280")
            ),

            # Keep reasonably confident results
            text_rec_score_thresh=float(
                os.environ.get("OCR_REC_SCORE_THRESH", "0.30")
            )
        )

        print("OCR model loaded.", flush=True)

    def process(self, image_path):

        start = time.time()

        print(
            f"OCR process started: {image_path}",
            flush=True
        )

        try:

            result = self.engine.predict(
                image_path
            )

            print(
                "OCR prediction returned",
                flush=True
            )

        except Exception as exc:

            print(
                f"OCR prediction failed: {exc}",
                flush=True
            )

            raise

        inference_time = (
            time.time() - start
        )

        print(
            f"OCR inference time: "
            f"{inference_time:.2f}s",
            flush=True
        )

        items = []

        for page in result:

            try:

                texts = page["rec_texts"]
                scores = page["rec_scores"]
                boxes = page["rec_polys"]

            except Exception as exc:

                print(
                    f"OCR result parsing warning: {exc}",
                    flush=True
                )

                continue

            for index, text in enumerate(texts):

                if not text:
                    continue

                text = str(
                    text
                ).strip()

                if not text:
                    continue

                # Confidence
                try:

                    confidence = float(
                        scores[index]
                    )

                except Exception:

                    confidence = 0.0

                # Bounding box
                try:

                    box = boxes[index].tolist()

                except Exception:

                    box = None

                items.append({

                    "text": text,

                    "confidence":
                        round(
                            confidence,
                            4
                        ),

                    "box":
                        box
                })

        # ----------------------------------------------------------
        # FIX #3: reconstruct true reading order.
        #
        # extraction_service.py assumes items[i+1] is semantically
        # "the next line" after items[i] (used by
        # get_value_after_label, extract_address,
        # extract_manufacturer, extract_best_before, etc.).
        # PaddleOCR's raw detection order does not guarantee this,
        # and real packaged-commodity labels are very commonly laid
        # out in 2-3 side-by-side print columns (e.g. an
        # ingredients/nutrition panel next to a manufacturer panel
        # next to an MRP/dates panel). Sorting purely top-to-bottom
        # would interleave unrelated columns line-by-line -- so
        # instead we first detect the real vertical gaps ("gutters")
        # that separate print columns, then read each column fully
        # top-to-bottom before moving to the next, the way a person
        # actually reads a multi-column label.
        # ----------------------------------------------------------
        items = self._sort_reading_order(items)

        total_time = (
            time.time() - start
        )

        print(
            f"OCR total time: "
            f"{total_time:.2f}s",
            flush=True
        )

        print(
            f"Detected text items: "
            f"{len(items)}",
            flush=True
        )

        return items

    # ================================================================
    # READING ORDER RECONSTRUCTION
    # ================================================================

    @staticmethod
    def _box_extent(item):
        """
        Returns (x_min, x_max, y_min, y_max, height) for an item's
        box, or None if it has no usable box.
        """

        box = item.get("box")

        if not box:
            return None

        xs = [point[0] for point in box]
        ys = [point[1] for point in box]

        return (
            min(xs),
            max(xs),
            min(ys),
            max(ys),
            max(ys) - min(ys)
        )

    @classmethod
    def _sort_within_column(cls, items):
        """
        Sorts items within a single print column into top-to-bottom
        reading order, grouping boxes into text "rows" first so
        that same-line label/value pairs (e.g. "MRP" then "20.00")
        come out in left-to-right order.
        """

        if not items:
            return items

        enriched = []

        for item in items:

            extent = cls._box_extent(item)

            if extent is None:
                enriched.append((0.0, 0.0, 0.0, item))
                continue

            x_min, x_max, y_min, y_max, height = extent
            y_center = (y_min + y_max) / 2

            enriched.append((y_center, x_min, height, item))

        enriched.sort(key=lambda entry: entry[0])

        heights = [
            entry[2]
            for entry in enriched
            if entry[2] > 0
        ]

        avg_height = (
            sum(heights) / len(heights)
            if heights
            else 20.0
        )

        # Two boxes are treated as being on the same "row" if their
        # vertical centers are within ~60% of the average text
        # height of each other -- tolerant of slight tilt without
        # merging genuinely separate lines.
        row_threshold = max(avg_height * 0.6, 8.0)

        rows = []
        current_row = []
        current_y = None

        for y_center, x_min, height, item in enriched:

            if (
                current_y is None
                or abs(y_center - current_y) <= row_threshold
            ):
                current_row.append((x_min, item))
                current_y = (
                    y_center
                    if current_y is None
                    else (current_y + y_center) / 2
                )
            else:
                rows.append(current_row)
                current_row = [(x_min, item)]
                current_y = y_center

        if current_row:
            rows.append(current_row)

        ordered = []

        for row in rows:
            row.sort(key=lambda entry: entry[0])
            ordered.extend(entry[1] for entry in row)

        return ordered

    @classmethod
    def _detect_columns(
        cls,
        items,
        num_bins=100,
        min_gutter_frac=0.02,
        min_coverage_frac=0.08
    ):
        """
        Splits OCR items into left-to-right print columns by
        finding real vertical "gutters" -- vertical strips with
        almost no text passing through them across the FULL height
        of the label.

        This is deliberately based on full-height coverage rather
        than clustering individual box positions, so it isn't
        confused by ordinary within-column gaps (like the gap
        between a nutrient name and its value in a nutrition
        table), which only span part of a column's height rather
        than the whole label.

        Returns a list of item-lists, one per detected column,
        ordered left to right. If no clear column structure is
        found (a single-column label), returns [items] unchanged.
        """

        extents = []

        for item in items:

            extent = cls._box_extent(item)

            if extent is None:
                continue

            x_min, x_max, y_min, y_max, _ = extent
            extents.append((x_min, x_max, y_min, y_max, item))

        if not extents:
            return [items]

        global_min_x = min(e[0] for e in extents)
        global_max_x = max(e[1] for e in extents)
        global_min_y = min(e[2] for e in extents)
        global_max_y = max(e[3] for e in extents)

        width = global_max_x - global_min_x
        height = global_max_y - global_min_y

        if width <= 0 or height <= 0:
            return [items]

        bin_width = width / num_bins

        # covered[b] = total y-extent of boxes overlapping bin b,
        # summed across every box that touches that vertical strip.
        covered = [0.0] * num_bins

        def bin_index(x):
            idx = int((x - global_min_x) / bin_width)
            return max(0, min(idx, num_bins - 1))

        for x_min, x_max, y_min, y_max, _ in extents:

            start_bin = bin_index(x_min)
            end_bin = bin_index(x_max)

            for b in range(start_bin, end_bin + 1):
                covered[b] += (y_max - y_min)

        is_gutter = [
            (covered[b] / height) < min_coverage_frac
            for b in range(num_bins)
        ]

        min_gutter_bins = max(1, round(num_bins * min_gutter_frac))

        # Find runs of gutter bins that are wide enough to count
        # as a genuine column boundary (filters out incidental
        # single-bin noise).
        boundaries = []
        i = 0

        while i < num_bins:

            if is_gutter[i]:

                j = i

                while j < num_bins and is_gutter[j]:
                    j += 1

                if (j - i) >= min_gutter_bins:
                    boundaries.append((i + j) // 2)

                i = j

            else:
                i += 1

        if not boundaries:
            # No real column structure detected -- single column.
            return [items]

        cut_bins = [0] + boundaries + [num_bins]
        cut_bins = sorted(set(cut_bins))

        column_ranges = [
            (cut_bins[k], cut_bins[k + 1])
            for k in range(len(cut_bins) - 1)
        ]

        columns = [[] for _ in column_ranges]

        for x_min, x_max, y_min, y_max, item in extents:

            x_center = (x_min + x_max) / 2
            b = bin_index(x_center)

            for idx, (start_bin, end_bin) in enumerate(column_ranges):

                is_last = (idx == len(column_ranges) - 1)

                if start_bin <= b < end_bin or (is_last and b >= start_bin):
                    columns[idx].append(item)
                    break

        return [column for column in columns if column]

    @classmethod
    def _sort_reading_order(cls, items):
        """
        Full reading-order reconstruction: detect print columns,
        then sort each column top-to-bottom (with left-to-right
        ordering for same-line label/value pairs), then
        concatenate columns left to right.
        """

        if not items:
            return items

        try:

            columns = cls._detect_columns(items)

            ordered = []

            for column in columns:
                ordered.extend(cls._sort_within_column(column))

            return ordered

        except Exception as exc:

            # Reading-order reconstruction should never be able to
            # crash a scan. If anything unexpected happens, fall
            # back to the original OCR order rather than failing.
            print(
                f"Reading-order sort failed, using raw OCR "
                f"order instead: {exc}",
                flush=True
            )

            return items

    @staticmethod
    def combine_text(items):

        return "\n".join(

            item["text"]

            for item in items

            if item.get("text")
        )


# Create one OCR service instance.
# Model loads once when Flask starts.
ocr_service = OCRService()