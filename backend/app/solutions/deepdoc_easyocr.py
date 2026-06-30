"""RAGFlow deepdoc layout/TSR + EasyOCR."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.doc_format import DocFormatStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.ocr.deepdoc_stage import DeepdocStage
from app.stages.pii.presidio import PresidioPII


SOLUTION = register(
    Solution(
        name="deepdoc_easyocr",
        display_name="RAGFlow deepdoc · EasyOCR",
        description=(
            "Deepdoc layout + table-structure recognizers feed text from "
            "EasyOCR's deep-learning detector + recognizer. Requires "
            "`[ocr-easy]` extras."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            DeepdocStage(params={"ocr_backend": "easyocr", "layout_score_threshold": 0.4}),
            PresidioPII(redact_image=False),
            DocFormatStage(),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
