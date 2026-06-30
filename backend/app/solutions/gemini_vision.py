"""Google Gemini Vision structured extraction."""

from app.config import settings
from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.doc_format import DocFormatStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.ocr.tesseract import TesseractOCR
from app.stages.pii.presidio import PresidioPII
from app.stages.vision.gemini_vision import GeminiVision

SOLUTION = register(
    Solution(
        name="gemini_vision",
        display_name="Gemini Vision",
        description=(
            "Tesseract seeds PII detection, Presidio redacts the image, then Gemini Vision "
            "returns structured regions + tables. Requires GEMINI_API_KEY in .env."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            TesseractOCR(use_preprocessed=False),
            PresidioPII(redact_image=True),
            GeminiVision(use_redacted=True),
            DocFormatStage(),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
        enabled=bool(settings.gemini_api_key),
        model=settings.gemini_model if settings.gemini_api_key else None,
    )
)
