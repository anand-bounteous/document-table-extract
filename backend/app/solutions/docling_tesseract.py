"""docling structured pipeline + Tesseract OCR backend."""

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
        name="docling_tesseract",
        display_name="docling · Tesseract",
        description=(
            "docling layout/tables/reading-order with the Tesseract CLI as OCR "
            "backend. Requires `tesseract` on PATH (`brew install tesseract` / "
            "`apt install tesseract-ocr`). Useful when EasyOCR's torch deps "
            "aren't installed or you want classical OCR comparison."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            DoclingStage(params={"ocr_backend": "tesseract"}),
            PresidioPII(redact_image=False),
            DocFormatStage(),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
