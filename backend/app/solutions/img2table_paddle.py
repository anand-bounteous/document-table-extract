"""img2table with PaddleOCR backend."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.pii.presidio import PresidioPII
from app.stages.tables_img2table import Img2TableStage
from app.stages.vision.paddle_structure import _paddle_env  # reuse thread-pin env


SOLUTION = register(
    Solution(
        name="img2table_paddle",
        display_name="img2table · PaddleOCR",
        description=(
            "img2table table detection backed by PaddleOCR. Reuses the already-installed "
            "PaddlePaddle runtime. Subprocess-isolated with PaddlePaddle thread-pin env. "
            "Lazy-loads paddle models on first run."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            Img2TableStage(
                name="tables_img2table_paddle",
                ocr_backend="paddle",
                extra_env=_paddle_env(),
            ),
            PresidioPII(redact_image=False),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
