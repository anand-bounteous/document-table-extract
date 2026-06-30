"""docling: high-level converter with structured output + reading order."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.docling_stage import DoclingStage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.doc_format import DocFormatStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.pii.presidio import PresidioPII


SOLUTION = register(
    Solution(
        name="docling",
        display_name="docling · EasyOCR (default)",
        description=(
            "IBM docling: layout + tables + reading order in one converter. Uses "
            "docling's default EasyOCR backend for any text not embedded in the "
            "PDF. Subprocess-isolated; downloads layout model on first run."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            DoclingStage(params={"ocr_backend": "easyocr"}),
            PresidioPII(redact_image=False),
            DocFormatStage(),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
