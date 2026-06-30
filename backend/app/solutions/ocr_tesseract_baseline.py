"""Baseline: raw tesseract over rasterized pages, no preprocessing."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.ocr.tesseract import TesseractOCR
from app.stages.pii.presidio import PresidioPII


SOLUTION = register(
    Solution(
        name="ocr_tesseract_baseline",
        display_name="Tesseract baseline",
        description="Raw tesseract OCR over rasterized pages. No preprocessing, no table reconstruction.",
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            TesseractOCR(use_preprocessed=False),
            PresidioPII(redact_image=False),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
