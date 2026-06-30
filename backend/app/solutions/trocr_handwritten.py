"""TrOCR — handwriting + signature recognition baseline."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.ocr.trocr_stage import TrOCRStage
from app.stages.pii.presidio import PresidioPII


SOLUTION = register(
    Solution(
        name="trocr_handwritten",
        display_name="TrOCR (handwritten)",
        description=(
            "Microsoft TrOCR (`microsoft/trocr-base-handwritten`) for "
            "handwritten text + signatures. EasyOCR's line detector is reused "
            "to find regions; TrOCR transcribes each crop. Output regions are "
            "tagged HANDWRITING_SIGNATURE so they surface under the Signatures "
            "panel of the card. Subprocess-isolated; first-run downloads "
            "~600 MB of HuggingFace weights."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            TrOCRStage(
                params={
                    "model_id": "microsoft/trocr-base-handwritten",
                    "mode": "handwritten",
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
