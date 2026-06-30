"""Camelot lattice-only — tuned for ruled/bordered tables."""

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
        name="camelot_lattice",
        display_name="Camelot · Lattice (ruled tables)",
        description=(
            "Camelot lattice flavor only: uses line segments to detect table boundaries. "
            "Tuned with line_scale=40 for dense ruled tables and copy_text/shift_text for "
            "vertical spans. Best on PDFs with clearly drawn grid lines."
        ),
        supported_kinds={"vector", "mixed"},
        stages=[
            TesseractOCR(use_preprocessed=False),
            CamelotStage(
                name="tables_camelot_lattice",
                flavors=["lattice"],
                flavor_kwargs={
                    "lattice": {
                        "line_scale": 40,
                        "copy_text": ["v"],
                        "shift_text": ["l", "t"],
                        "joint_tol": 2,
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
