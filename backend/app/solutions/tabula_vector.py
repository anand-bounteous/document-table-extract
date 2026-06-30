"""Tabula lattice+stream — vector PDFs only (uses present JVM)."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.ocr.tesseract import TesseractOCR
from app.stages.pii.presidio import PresidioPII
from app.stages.tables_tabula import TabulaStage


SOLUTION = register(
    Solution(
        name="tabula_vector",
        display_name="Tabula (vector tables)",
        description=(
            "Vector-PDF tables via tabula-py (runs on the JVM). Both lattice and stream "
            "modes. Tesseract supplies non-table text Regions."
        ),
        supported_kinds={"vector", "mixed"},
        stages=[
            TesseractOCR(use_preprocessed=False),
            TabulaStage(),
            PresidioPII(redact_image=False),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
