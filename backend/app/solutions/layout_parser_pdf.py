"""Layout-Parser (PDF-native) — reads PDF text layer + runs visual model.

Vector-PDF variant of :mod:`app.solutions.layout_parser`. Sends the PDF
directly to ``lp.load_pdf`` for text-layer tokens, then layers the
PaddleDetection visual model on top to catch non-text structural elements
(Figure / Table / Title) that aren't representable in the text stream.

Auto-skipped on scanned PDFs (no text layer).
"""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.doc_format import DocFormatStage
from app.stages.layout.layout_parser_pdf_stage import LayoutParserPdfStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.pii.presidio import PresidioPII


SOLUTION = register(
    Solution(
        name="layout_parser_pdf",
        display_name="Layout-Parser (PDF-native)",
        description=(
            "Vector-PDF variant of layout_parser. Reads the PDF text layer via "
            "`lp.load_pdf` for exact-position text tokens, then runs the "
            "PaddleDetection visual model on the rasterized page to catch "
            "Figure / Table / Title regions that aren't in the text stream. "
            "Vector PDFs only — auto-skipped on scanned documents."
        ),
        supported_kinds={"vector"},
        stages=[
            LayoutParserPdfStage(),
            PresidioPII(redact_image=False),
            DocFormatStage(),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
