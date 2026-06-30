"""PyMuPDF native-PDF extraction (vector PDFs only)."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.native_pymupdf import NativePyMuPDFStage
from app.stages.pii.presidio import PresidioPII


SOLUTION = register(
    Solution(
        name="native_pymupdf",
        display_name="PyMuPDF (native text + tables)",
        description=(
            "Native-PDF extraction via PyMuPDF (fitz). Reads the PDF text layer "
            "directly — no rasterization, no OCR — and uses `page.find_tables()` "
            "for ruled / whitespace tables. Vector PDFs only; automatically "
            "skipped when the document is scanned / non-native."
        ),
        supported_kinds={"vector"},
        stages=[
            NativePyMuPDFStage(),
            PresidioPII(redact_image=False),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
