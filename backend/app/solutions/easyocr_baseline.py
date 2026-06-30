"""EasyOCR standalone OCR baseline."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.ocr.easyocr_stage import EasyOCRStage
from app.stages.pii.presidio import PresidioPII


SOLUTION = register(
    Solution(
        name="easyocr_baseline",
        display_name="EasyOCR baseline",
        description=(
            "Standalone EasyOCR text extraction. Deep-learning OCR with no Tesseract "
            "dependency; good on varied fonts and low-res scans. Subprocess-isolated; "
            "downloads EasyOCR CRAFT + recognition models (~100 MB) on first run."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            EasyOCRStage(),
            PresidioPII(redact_image=False),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
