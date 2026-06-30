"""Layout-Parser (Detectron2 PubLayNet) — layout detection + doc-format label."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.doc_format import DocFormatStage
from app.stages.layout.layout_parser_stage import LayoutParserStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.pii.presidio import PresidioPII


SOLUTION = register(
    Solution(
        name="layout_parser",
        display_name="Layout-Parser (PubLayNet)",
        description=(
            "Layout detection via Layout-Parser's Detectron2 backbone trained "
            "on PubLayNet — emits Text / Title / List / Table / Figure regions. "
            "Authoritatively populates the page-level `doc_format` label "
            "(tabular-heavy / form-like / narrative / image-heavy / mixed). "
            "Subprocess-isolated; first-run model download from layoutparser's "
            "Dropbox mirror (~250 MB)."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            LayoutParserStage(),
            PresidioPII(redact_image=False),
            DocFormatStage(),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
