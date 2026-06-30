"""Tabula stream-only with guess=True — JVM-backed, whitespace tables."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.pii.presidio import PresidioPII
from app.stages.tables_tabula import TabulaStage


SOLUTION = register(
    Solution(
        name="tabula_stream",
        display_name="Tabula · Stream (whitespace, guess columns)",
        description=(
            "Tabula stream mode with guess=True: uses whitespace analysis + column-boundary "
            "heuristics to find tables in PDFs without visible ruling lines. Best on financial "
            "statements and reports. Requires a JVM (openjdk)."
        ),
        supported_kinds={"vector", "mixed"},
        stages=[
            TabulaStage(name="tables_tabula_stream", flavors=["stream"], guess=True),
            PresidioPII(redact_image=False),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
