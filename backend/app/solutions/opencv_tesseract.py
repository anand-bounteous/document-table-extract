"""OpenCV-preprocessed tesseract + ruled-line table reconstruction."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.layout.heuristic import RuledTableFromOpenCV
from app.stages.ocr.tesseract import TesseractOCR
from app.stages.pii.presidio import PresidioPII
from app.stages.preprocess_opencv import PreprocessOpenCV


SOLUTION = register(
    Solution(
        name="opencv_tesseract",
        display_name="OpenCV → Tesseract → ruled tables",
        description=(
            "OpenCV deskew/denoise/threshold + ruled-line detection, tesseract OCR on the "
            "preprocessed image, then build TableModels from detected line grids."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            PreprocessOpenCV(),
            TesseractOCR(use_preprocessed=True),
            RuledTableFromOpenCV(),
            PresidioPII(redact_image=False),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
