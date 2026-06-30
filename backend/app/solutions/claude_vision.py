"""Claude Vision structured extraction (quality ceiling)."""

from app.config import settings
from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.doc_format import DocFormatStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.ocr.tesseract import TesseractOCR
from app.stages.pii.presidio import PresidioPII
from app.stages.vision.claude_vision import ClaudeVision


SOLUTION = register(
    Solution(
        name="claude_vision",
        display_name="Claude Vision (structured)",
        description=(
            "Tesseract first (cheap, supplies text for PII detection), Presidio pre-masks "
            "the image, then Claude Vision returns structured regions + tables."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            TesseractOCR(use_preprocessed=False),
            PresidioPII(redact_image=True),
            ClaudeVision(use_redacted=True),
            DocFormatStage(),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
        enabled=bool(settings.anthropic_api_key),
        model=settings.anthropic_model if settings.anthropic_api_key else None,
    )
)
