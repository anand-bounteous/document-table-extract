"""docling structured pipeline + TrOCR (handwritten) OCR backend."""

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
        name="docling_trocr_handwritten",
        display_name="docling · TrOCR (handwritten)",
        description=(
            "docling layout/tables/reading-order with a custom TrOCR-handwritten "
            "post-OCR pass. TrOCR is line-only — the worker uses EasyOCR's "
            "line detector inside each region crop, then runs "
            "`microsoft/trocr-base-handwritten` per line. Best for documents "
            "with handwritten text under a printed-table structure."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            DoclingStage(params={"ocr_backend": "trocr_handwritten"}),
            PresidioPII(redact_image=False),
            DocFormatStage(),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
