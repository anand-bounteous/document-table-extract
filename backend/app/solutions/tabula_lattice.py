"""Tabula lattice-only — JVM-backed, ruled/bordered tables."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.pii.presidio import PresidioPII
from app.stages.tables_tabula import TabulaStage


SOLUTION = register(
    Solution(
        name="tabula_lattice",
        display_name="Tabula · Lattice (ruled tables)",
        description=(
            "Tabula lattice mode only: uses PDF vector lines to detect table boundaries. "
            "High accuracy on documents with visible ruling lines. Requires a JVM (openjdk)."
        ),
        supported_kinds={"vector", "mixed"},
        stages=[
            TabulaStage(name="tables_tabula_lattice", flavors=["lattice"]),
            PresidioPII(redact_image=False),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
