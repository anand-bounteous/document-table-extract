"""RAGFlow deepdoc — default ONNX OCR (text det + rec)."""

from app.pipeline.base import Solution, register
from app.stages.annotate.render import AnnotatePage
from app.stages.layout.custom_table import CustomTableStage
from app.stages.layout.doc_format import DocFormatStage
from app.stages.layout.table_crop import TableCropStage
from app.stages.layout.table_obfuscate import TableObfuscateStage
from app.stages.ocr.deepdoc_stage import DeepdocStage
from app.stages.pii.presidio import PresidioPII


SOLUTION = register(
    Solution(
        name="deepdoc_baseline",
        display_name="RAGFlow deepdoc (default ONNX OCR)",
        description=(
            "RAGFlow's deepdoc pipeline: ONNX layout detector + ONNX text "
            "detection/recognition + ONNX table-structure recognizer. Vendored "
            "from upstream's `deepdoc/vision/` (Apache 2.0). Subprocess-isolated; "
            "first-run downloads ~250 MB of ONNX weights from `InfiniFlow/deepdoc` "
            "on Hugging Face."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            DeepdocStage(params={"ocr_backend": "default", "layout_score_threshold": 0.4}),
            PresidioPII(redact_image=False),
            DocFormatStage(),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
