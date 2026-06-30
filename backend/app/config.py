"""Application configuration via Pydantic Settings."""

from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    anthropic_api_key: str = Field(default="")
    anthropic_model: str = Field(default="claude-sonnet-4-6")
    anthropic_max_tokens: int = Field(default=8192)

    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o")

    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-2.0-flash")

    pii_mask_key: str = Field(default="")

    cors_origins: str = Field(default="http://localhost:3000")
    data_dir: str = Field(default=str(_BACKEND_ROOT.parent / "data"))
    runs_dir: str = Field(default=str(_BACKEND_ROOT / "storage" / "runs"))

    default_dpi: int = Field(default=300)
    vision_dpi: int = Field(default=200)

    # Solution-level concurrency. 0 = auto-tune from psutil.virtual_memory().available.
    # The auto-tune divides free RAM by ram_per_solution_gb and clamps to
    # [1, min(n_solutions, 16)].
    max_concurrent_solutions: int = Field(default=0)
    ram_per_solution_gb: float = Field(default=3.0)

    # pii_v2 (independent UK-banking PII benchmark track)
    pii_v2_enabled: bool = Field(default=True)
    pii_v2_visual_enabled: bool = Field(default=True)
    pii_v2_redaction_enabled: bool = Field(default=True)
    pii_v2_redaction_font_path: str = Field(default="")
    pii_v2_max_overlays: int = Field(default=50)
    pii_v2_user_custom_score: float = Field(default=0.85)
    pii_v2_default_jurisdictions: str = Field(default="GLOBAL_COMMON,UK")
    pii_v2_default_detectors: str = Field(default="presidio_regex,presidio_spacy,gliner,piiranha,hybrid")
    pii_v2_text_producers: str = Field(
        default="native_pymupdf,native_pdfplumber,paddleocr_baseline,ocr_tesseract_baseline,easyocr_baseline,doctr_baseline,trocr_printed,trocr_handwritten,docling,docling_tesseract,docling_rapidocr,docling_doctr,docling_trocr_handwritten"
    )
    pii_v2_runs_dir: str = Field(default=str(_BACKEND_ROOT / "storage" / "pii_runs"))

    # Native-PDF (PyMuPDF / pdfplumber) feature flags. All default True so a
    # fresh checkout gets the richest output; switch any one off when
    # benchmarking the bare extractor against the enriched pipeline.
    native_pymupdf_emit_font_details: bool = Field(default=True)
    native_pymupdf_emit_drawings: bool = Field(default=True)
    native_pymupdf_emit_template: bool = Field(default=True)
    # Template generation: by default keep every non-text element (images,
    # line art, fills). Flip either flag to True when you want a "structure
    # only" template — useful for benchmarking layout detectors that should
    # not see any visual content.
    native_pymupdf_template_remove_images: bool = Field(default=False)
    native_pymupdf_template_remove_graphics: bool = Field(default=False)
    native_pdf_emit_visual_codes: bool = Field(default=True)

    @property
    def pii_v2_runs_path(self) -> Path:
        return Path(self.pii_v2_runs_dir).resolve()

    @property
    def pii_v2_default_jurisdictions_list(self) -> List[str]:
        return [j.strip() for j in self.pii_v2_default_jurisdictions.split(",") if j.strip()]

    @property
    def pii_v2_default_detectors_list(self) -> List[str]:
        return [d.strip() for d in self.pii_v2_default_detectors.split(",") if d.strip()]

    @property
    def pii_v2_text_producers_list(self) -> List[str]:
        return [p.strip() for p in self.pii_v2_text_producers.split(",") if p.strip()]

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir).resolve()

    @property
    def runs_path(self) -> Path:
        return Path(self.runs_dir).resolve()


settings = Settings()
