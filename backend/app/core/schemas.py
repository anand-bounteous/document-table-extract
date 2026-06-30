"""Normalized result schemas.

The whole pipeline pivots on a single coordinate space: rasterized-image pixels at
the run DPI, top-left origin. Any tool that returns PDF points (bottom-left) must
convert before populating these models.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


PdfKind = Literal["vector", "scanned", "mixed", "unknown"]
SolutionStatus = Literal["ok", "partial", "skipped", "error"]
StageStatus = Literal["ok", "skipped", "error"]
TableOrientation = Literal["horizontal", "vertical_kv"]
TableBorderMode = Literal["ruled", "whitespace", "mixed", "unknown"]


class RegionType(str, Enum):
    LOGO = "logo"
    NORMAL_TEXT = "normal_text"
    TABLE = "table"
    TABLE_HEADER = "table_header"
    TABLE_ROW = "table_row"
    TABLE_CELL = "table_cell"
    IMAGE = "image"
    HANDWRITING_SIGNATURE = "handwriting_signature"
    SEAL = "seal"
    WATERMARK = "watermark"
    KV_PAIR = "kv_pair"
    UNKNOWN = "unknown"


class BBox(BaseModel):
    x: float
    y: float
    w: float
    h: float
    page_index: int
    coord_space: str = "image_px@300"

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h


class PiiSpan(BaseModel):
    entity_type: str
    start: int
    end: int
    score: float
    bbox: Optional[BBox] = None
    masked_value: str
    token: Optional[str] = None  # Fernet-map key for revealing the original value


class TableCell(BaseModel):
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1
    text: str = ""
    bbox: Optional[BBox] = None
    multiline: bool = False
    confidence: Optional[float] = None
    is_header: bool = False  # True when the upstream tool tagged this cell as a header


class TableModel(BaseModel):
    region_id: str
    orientation: TableOrientation = "horizontal"
    border_mode: TableBorderMode = "unknown"
    n_rows: int = 0
    n_cols: int = 0
    cells: List[TableCell] = Field(default_factory=list)
    html: Optional[str] = None


class Region(BaseModel):
    id: str
    type: RegionType
    bbox: BBox
    text: str = ""
    confidence: float = 0.0
    raw_confidence: Optional[float] = None
    source_tool: str
    parent_id: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    artifact_refs: List[str] = Field(default_factory=list)
    pii_spans: List[PiiSpan] = Field(default_factory=list)


class AuditStep(BaseModel):
    stage_name: str
    tool: str
    order: int
    started_at: datetime
    duration_ms: float
    params: Dict[str, Any] = Field(default_factory=dict)
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)
    status: StageStatus = "ok"
    message: Optional[str] = None
    usage: Dict[str, Any] = Field(default_factory=dict)


CustomTableStatus = Literal["ok", "na_missing_bbox", "not_found"]


class CustomTable(TableModel):
    """Table reconstructed from pure-Python geometric analysis of region bboxes.

    Mirrors TableModel; the `detection` dict captures the tolerances used and
    the cluster sizes so a reviewer can see WHY the heuristic fired.
    """
    detection: Dict[str, Any] = Field(default_factory=dict)


class PageResult(BaseModel):
    page_index: int
    width: int
    height: int
    dpi: int
    pdf_kind: PdfKind = "unknown"
    regions: List[Region] = Field(default_factory=list)
    tables: List[TableModel] = Field(default_factory=list)
    custom_tables: List[CustomTable] = Field(default_factory=list)
    custom_table_status: CustomTableStatus = "not_found"
    custom_table_message: Optional[str] = None
    annotated_image_ref: Optional[str] = None
    # Raw rasterized page PNG (no annotations baked in). The UI uses this as
    # the background; SVG draws toggle-able overlays on top.
    page_image_ref: Optional[str] = None
    # Page-level layout-format label derived from region distribution. One of
    # ``tabular-heavy | form-like | narrative | image-heavy | mixed | unknown``.
    # Set by ``DocFormatStage`` or authoritatively by the layout solution.
    doc_format: Optional[str] = None
    doc_format_scores: Dict[str, float] = Field(default_factory=dict)
    full_text: str = ""
    table_crop_refs: List[str] = Field(default_factory=list)
    table_obfuscated_refs: List[str] = Field(default_factory=list)


class SolutionTimings(BaseModel):
    total_ms: float = 0.0
    by_stage: Dict[str, float] = Field(default_factory=dict)


class SolutionResult(BaseModel):
    solution_name: str
    status: SolutionStatus = "ok"
    skipped_reason: Optional[str] = None
    pages: List[PageResult] = Field(default_factory=list)
    audit: List[AuditStep] = Field(default_factory=list)
    timings: SolutionTimings = Field(default_factory=SolutionTimings)
    overall_confidence: float = 0.0
    artifacts_dir: Optional[str] = None
    error: Optional[str] = None


class DocumentResult(BaseModel):
    document_id: str
    filename: str
    pdf_kind: PdfKind = "unknown"
    n_pages: int = 0
    solution_results: List[SolutionResult] = Field(default_factory=list)


class SolutionDescriptor(BaseModel):
    """Public registry view of a Solution (no callables)."""

    name: str
    display_name: str
    description: str
    supported_kinds: List[PdfKind]
    stages: List[str]
    enabled: bool = True
    model: Optional[str] = None
