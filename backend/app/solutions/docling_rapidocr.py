"""docling structured pipeline + RapidOCR backend."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.docling_stage import DoclingStage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.doc_format import DocFormatStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.pii.presidio import PresidioPII


SOLUTION = register(
    Solution(
        name="docling_rapidocr",
        display_name="docling · RapidOCR",
        description=(
            "docling layout/tables/reading-order with RapidOCR (PaddleOCR-derived "
            "ONNX models) as the OCR backend. Lightweight CPU-friendly alternative "
            "to EasyOCR — no torch dependency. Requires `rapidocr_onnxruntime`."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            DoclingStage(params={"ocr_backend": "rapidocr"}),
            PresidioPII(redact_image=False),
            DocFormatStage(),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
