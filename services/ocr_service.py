import os
import time

# Disable MKLDNN / oneDNN before importing PaddleOCR
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
os.environ["FLAGS_use_mkldnn"] = "0"

from paddleocr import PaddleOCR


class OCRService:

    def __init__(self):

        print("Loading OCR model...", flush=True)

        self.engine = PaddleOCR(
            lang="en",
            device="cpu",

            # Disable unnecessary modules
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,

            # Small PP-OCRv6 models
            text_detection_model_name="PP-OCRv6_small_det",
            text_recognition_model_name="PP-OCRv6_small_rec",

            # Faster detection
            text_det_limit_side_len=960,

            # Keep reasonably confident results
            text_rec_score_thresh=0.30
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