"""Camelot lattice+stream — vector PDFs only (needs Ghostscript on PATH)."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.ocr.tesseract import TesseractOCR
from app.stages.pii.presidio import PresidioPII
from app.stages.tables_camelot import CamelotStage


SOLUTION = register(
    Solution(
        name="camelot_vector",
        display_name="Camelot (vector tables)",
        description=(
            "Vector-PDF table extraction. Runs Camelot in BOTH lattice (ruled) and "
            "stream (whitespace) flavors. Requires Ghostscript on PATH. Tesseract is "
            "still run to provide text Regions outside tables."
        ),
        supported_kinds={"vector", "mixed"},
        stages=[
            TesseractOCR(use_preprocessed=False),
            CamelotStage(),
            PresidioPII(redact_image=False),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
