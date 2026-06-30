"""DocTR standalone OCR baseline."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.ocr.doctr_stage import DocTRStage
from app.stages.pii.presidio import PresidioPII


SOLUTION = register(
    Solution(
        name="doctr_baseline",
        display_name="DocTR baseline",
        description=(
            "Standalone DocTR (mindee) OCR: two-stage detection + recognition pipeline. "
            "Strong on document layout; outputs line-level regions with word confidences. "
            "Subprocess-isolated; downloads DocTR models (~100 MB) on first run."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            DocTRStage(),
            PresidioPII(redact_image=False),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
