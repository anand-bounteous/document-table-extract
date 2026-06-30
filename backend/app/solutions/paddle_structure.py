"""PaddleOCR PP-Structure: layout + tables + OCR (heavy)."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.doc_format import DocFormatStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.pii.presidio import PresidioPII
from app.stages.vision.paddle_structure import PaddleStructureStage


SOLUTION = register(
    Solution(
        name="paddle_structure",
        display_name="PaddleOCR PP-Structure",
        description=(
            "PP-Structure: layout analysis + table extraction + OCR in a single pass. "
            "Strong on whitespace-bordered tables and multiline cells. Subprocess-isolated; "
            "lazy-loads paddlepaddle on first run."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            PaddleStructureStage(),
            PresidioPII(redact_image=False),
            DocFormatStage(),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
