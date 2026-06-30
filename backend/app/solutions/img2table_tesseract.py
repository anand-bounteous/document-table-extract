"""img2table with Tesseract OCR backend."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.ocr.tesseract import TesseractOCR
from app.stages.pii.presidio import PresidioPII
from app.stages.tables_img2table import Img2TableStage


SOLUTION = register(
    Solution(
        name="img2table_tesseract",
        display_name="img2table · Tesseract",
        description=(
            "Tesseract OCR for word-level text; img2table detects bordered and "
            "borderless tables on the rasterized image. Subprocess-isolated."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            TesseractOCR(use_preprocessed=False),
            Img2TableStage(name="tables_img2table_tesseract", ocr_backend="tesseract"),
            PresidioPII(redact_image=False),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
