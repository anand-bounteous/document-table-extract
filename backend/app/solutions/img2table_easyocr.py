"""img2table with EasyOCR backend."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.pii.presidio import PresidioPII
from app.stages.tables_img2table import Img2TableStage


SOLUTION = register(
    Solution(
        name="img2table_easyocr",
        display_name="img2table · EasyOCR",
        description=(
            "img2table table detection backed by EasyOCR (deep-learning OCR, "
            "no Tesseract required). Good on scanned documents with varied fonts. "
            "Subprocess-isolated; downloads EasyOCR models (~100 MB) on first run."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            Img2TableStage(name="tables_img2table_easyocr", ocr_backend="easyocr"),
            PresidioPII(redact_image=False),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
