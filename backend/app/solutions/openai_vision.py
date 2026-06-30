"""OpenAI GPT-4o Vision structured extraction."""

from app.config import settings
from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.doc_format import DocFormatStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.ocr.tesseract import TesseractOCR
from app.stages.pii.presidio import PresidioPII
from app.stages.vision.openai_vision import OpenAIVision

SOLUTION = register(
    Solution(
        name="openai_vision",
        display_name="OpenAI GPT-4o Vision",
        description=(
            "Tesseract seeds PII detection, Presidio redacts the image, then GPT-4o Vision "
            "returns structured regions + tables. Requires OPENAI_API_KEY in .env."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            TesseractOCR(use_preprocessed=False),
            PresidioPII(redact_image=True),
            OpenAIVision(use_redacted=True),
            DocFormatStage(),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
        enabled=bool(settings.openai_api_key),
        model=settings.openai_model if settings.openai_api_key else None,
    )
)
