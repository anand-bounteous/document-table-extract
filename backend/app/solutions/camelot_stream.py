"""Camelot stream-only — tuned for whitespace-separated tables."""

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
        name="camelot_stream",
        display_name="Camelot · Stream (whitespace tables)",
        description=(
            "Camelot stream flavor only: detects tables using whitespace gaps between columns. "
            "Tuned edge_tol and row_tol for tightly-spaced documents. Best on vector PDFs "
            "where column alignment is consistent but no visible grid lines exist."
        ),
        supported_kinds={"vector", "mixed"},
        stages=[
            TesseractOCR(use_preprocessed=False),
            CamelotStage(
                name="tables_camelot_stream",
                flavors=["stream"],
                flavor_kwargs={
                    "stream": {
                        "edge_tol": 50,
                        "row_tol": 2,
                        "column_tol": 0,
                    }
                },
            ),
            PresidioPII(redact_image=False),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
