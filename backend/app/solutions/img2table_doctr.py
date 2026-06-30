"""img2table with DocTR backend."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.pii.presidio import PresidioPII
from app.stages.tables_img2table import Img2TableStage


SOLUTION = register(
    Solution(
        name="img2table_doctr",
        display_name="img2table · DocTR",
        description=(
            "img2table table detection backed by DocTR (mindee's deep-learning OCR). "
            "Strong two-stage architecture: detection model + recognition model. "
            "Subprocess-isolated; downloads DocTR models (~100 MB) on first run."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            Img2TableStage(name="tables_img2table_doctr", ocr_backend="doctr"),
            PresidioPII(redact_image=False),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
