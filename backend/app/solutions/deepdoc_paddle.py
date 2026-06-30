"""RAGFlow deepdoc layout/TSR + PaddleOCR."""

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
        name="deepdoc_paddle",
        display_name="RAGFlow deepdoc · PaddleOCR",
        description=(
            "Deepdoc layout + table-structure recognizers feed text from "
            "PaddleOCR (PP-OCRv4 by default to avoid the OOM that PP-OCRv5 "
            "triggers on 8 GB Macs). Requires `[ocr-paddle]` extras."
        ),
        supported_kinds={"vector", "scanned", "mixed"},
        stages=[
            DeepdocStage(params={"ocr_backend": "paddle", "layout_score_threshold": 0.4}),
            PresidioPII(redact_image=False),
            DocFormatStage(),
            CustomTableStage(),
            TableCropStage(),
            TableObfuscateStage(),
            AnnotatePage(),
        ],
    )
)
