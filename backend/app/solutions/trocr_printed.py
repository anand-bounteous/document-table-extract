"""TrOCR — printed-text OCR baseline."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.ocr.trocr_stage import TrOCRStage
from app.stages.pii.presidio import PresidioPII


SOLUTION = register(
    Solution(
        name="trocr_printed",
        display_name="TrOCR (printed)",
        description=(
            "Microsoft TrOCR (`microsoft/trocr-base-printed`) for printed-text "
            "OCR. EasyOCR's line detector is reused to find regions; TrOCR "
            "transcribes each crop. Output regions are NORMAL_TEXT so they're "
            "directly comparable to the tesseract / easyocr / doctr / paddleocr "
            "baselines. Subprocess-isolated; first-run downloads ~600 MB of "
            "HuggingFace weights."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            TrOCRStage(
                params={
                    "model_id": "microsoft/trocr-base-printed",
                    "mode": "printed",
                    "lang": "en",
                }
            ),
            PresidioPII(redact_image=False),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
