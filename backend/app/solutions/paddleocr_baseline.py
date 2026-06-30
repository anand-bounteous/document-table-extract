"""PaddleOCR standalone OCR baseline."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.ocr.paddleocr_stage import PaddleOCRStage
from app.stages.pii.presidio import PresidioPII


SOLUTION = register(
    Solution(
        name="paddleocr_baseline",
        display_name="PaddleOCR baseline",
        description=(
            "Standalone PaddleOCR text detection + recognition (PP-OCRv4). No layout "
            "or table model — outputs line-level text regions. Multilingual; "
            "subprocess-isolated with paddle thread-pin env. Lazy-loads PaddleOCR "
            "models on first run."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            PaddleOCRStage(),
            PresidioPII(redact_image=False),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
