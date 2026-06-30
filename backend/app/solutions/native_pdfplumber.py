"""pdfplumber native-PDF extraction (vector PDFs only)."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.native_pdfplumber import NativePdfPlumberStage
from app.stages.pii.presidio import PresidioPII


SOLUTION = register(
    Solution(
        name="native_pdfplumber",
        display_name="pdfplumber (native text + tables)",
        description=(
            "Native-PDF extraction via pdfplumber (pdfminer.six). Reads the PDF "
            "text layer directly and uses geometric heuristics over PDF drawing "
            "operators to detect ruled and whitespace tables. Vector PDFs only; "
            "automatically skipped when the document is scanned / non-native."
        ),
        supported_kinds={"vector"},
        stages=[
            NativePdfPlumberStage(),
            PresidioPII(redact_image=False),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
