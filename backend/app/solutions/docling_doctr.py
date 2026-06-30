"""docling structured pipeline + DocTR OCR backend (custom post-OCR)."""

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
        name="docling_doctr",
        display_name="docling · DocTR",
        description=(
            "docling layout/tables/reading-order with a custom DocTR post-OCR "
            "pass. DocTR is not a docling-native backend — the worker runs "
            "docling with `do_ocr=False`, then crops each text region's bbox "
            "from the page raster and recognises it via `doctr.ocr_predictor`. "
            "Requires the `[ocr-doctr]` extras."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            DoclingStage(params={"ocr_backend": "doctr"}),
            PresidioPII(redact_image=False),
            DocFormatStage(),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
