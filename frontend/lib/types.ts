// Mirrors backend/app/core/schemas.py. Regenerate from /openapi.json when contract changes.

export type PdfKind = "vector" | "scanned" | "mixed" | "unknown";
export type SolutionStatus = "ok" | "partial" | "skipped" | "error";
export type StageStatus = "ok" | "skipped" | "error";

export interface BBox {
  x: number; y: number; w: number; h: number; page_index: number; coord_space: string;
}

export interface PiiSpan {
  entity_type: string;
  start: number; end: number;
  score: number;
  bbox?: BBox | null;
  masked_value: string;
  token?: string | null;
}

export interface PiiTokenInfo {
  token: string;
  entity: string;
  masked: string;
  original: string | null;
  n_occurrences: number;
  pages: number[];
}

export interface PiiBundle {
  tokens: PiiTokenInfo[];
  masked_pages: { page_index: number; ref: string }[];
  /** Same-length mock-redacted variants written by the PresidioPII stage
   * (see backend/app/stages/pii/presidio.py::_emit_mock_variants). The
   * legacy OCR run dashboard surfaces these so the user can pass safe
   * text/image to an LLM and later restore via the encrypted mapping —
   * mirrors the pii_v2 benchmark's Redaction tab. */
  mock_redacted_pages?: {
    page_index: number;
    clean_ref: string | null;
    annotated_ref: string | null;
  }[];
  mock_mapping_index?: {
    n_mappings: number;
    entity_types: Record<string, number>;
  } | null;
  mock_mapping_ref?: string | null;
}

export interface ReviewRecord {
  document_id: string;
  filename: string;
  pages: Record<string, PageReview>;
  updated_at?: string;
}

export interface DashboardStats {
  docs_reviewed: number;
  pages_accepted: number;
  per_solution: { solution: string; accepts: number }[];
  recent: { document_id: string; filename: string; n_pages_accepted: number; updated_at: string | null }[];
}

export interface Region {
  id: string;
  type: string;
  bbox: BBox;
  text: string;
  confidence: number;
  raw_confidence?: number | null;
  source_tool: string;
  parent_id?: string | null;
  attributes: Record<string, unknown>;
  artifact_refs: string[];
  pii_spans: PiiSpan[];
}

export interface TableCell {
  row: number; col: number; rowspan: number; colspan: number;
  text: string;
  bbox?: BBox | null;
  multiline: boolean;
  confidence?: number | null;
  is_header?: boolean;
}

export interface TableModel {
  region_id: string;
  orientation: "horizontal" | "vertical_kv";
  border_mode: "ruled" | "whitespace" | "mixed" | "unknown";
  n_rows: number; n_cols: number;
  cells: TableCell[];
  html?: string | null;
}

export interface CustomTable extends TableModel {
  detection: Record<string, unknown>;
}

export type CustomTableStatus = "ok" | "na_missing_bbox" | "not_found";

export interface LlmUsage {
  model?: string;
  input_tokens?: number;
  output_tokens?: number;
}

export interface AuditStep {
  stage_name: string; tool: string; order: number;
  started_at: string; duration_ms: number;
  params: Record<string, unknown>;
  inputs: string[]; outputs: string[];
  status: StageStatus;
  message?: string | null;
  usage?: LlmUsage;
}

export interface PageResult {
  page_index: number; width: number; height: number; dpi: number;
  pdf_kind: PdfKind;
  regions: Region[]; tables: TableModel[];
  custom_tables: CustomTable[];
  custom_table_status: CustomTableStatus;
  custom_table_message?: string | null;
  annotated_image_ref?: string | null;
  page_image_ref?: string | null;
  doc_format?: string | null;
  doc_format_scores?: Record<string, number>;
  full_text: string;
  table_crop_refs: string[];
  table_obfuscated_refs: string[];
}

export interface TableCropEntry {
  page_index: number;
  kind: "plain" | "obfuscated";
  ref: string;
  n_rows: number;
  n_cols: number;
  cells: TableCell[];
}

export interface TableCropsBundle {
  crops: TableCropEntry[];
}

export interface SolutionResult {
  solution_name: string;
  status: SolutionStatus;
  skipped_reason?: string | null;
  pages: PageResult[];
  audit: AuditStep[];
  timings: { total_ms: number; by_stage: Record<string, number> };
  overall_confidence: number;
  artifacts_dir?: string | null;
  error?: string | null;
}

export interface SolutionDescriptor {
  name: string; display_name: string; description: string;
  supported_kinds: PdfKind[]; stages: string[];
  enabled?: boolean;
  model?: string | null;
}

export interface DocumentMeta {
  id: string; filename: string; source?: string; size_bytes?: number;
  pdf_kind?: PdfKind; n_pages?: number;
}

export type SolutionLifecycle = "pending" | "running" | "done" | "error" | "skipped" | "partial";

export interface SolutionProgress {
  current_page: number;
  total_pages: number;
  status: "running" | "done" | "error";
  elapsed_sec?: number;
  updated_at?: string;
  page_index?: number;
  tool?: string;
}

export interface SolutionStatusEntry {
  state: SolutionLifecycle;
  queued_at?: string;
  started_at?: string;
  updated_at?: string;
  result_status?: SolutionStatus;
  overall_confidence?: number;
  duration_ms?: number;
  error?: string | null;
  progress?: SolutionProgress;
  n_pages_done?: number;
  n_pages_expected?: number;
}

export interface BatchDocument {
  document_id: string;
  filename: string;
  run_id: string;
  pdf_kind: PdfKind;
  n_pages: number;
  status: "queued" | "running" | "done" | "error";
  started_at?: string | null;
  finished_at?: string | null;
  run?: RunState;
}

export interface BatchState {
  batch_id: string;
  created_at: string;
  updated_at?: string;
  status: "running" | "done";
  solution_names: string[];
  dpi: number;
  documents: BatchDocument[];
  stats: {
    total: number;
    queued: number;
    running: number;
    done: number;
    error: number;
  };
}

// ---- pii_v2 benchmark types ----------------------------------------------

export interface PiiV2Entity {
  entity_type: string;
  text: string;
  start: number;
  end: number;
  score: number;
  source: string;
  detection_method: string;
  jurisdiction?: string | null;
  risk_level?: string | null;
  sensitivity_category?: string | null;
  metadata?: Record<string, unknown>;
}

export interface PiiDetectorDescriptor {
  name: string;
  display_name: string;
  description: string;
  requires_models?: string[];
}

export interface PiiCellSummary {
  entity_count: number;
  latency_ms: number;
  error?: string | null;
  entity_types: Record<string, number>;
  category_counts?: Record<string, number>;
  status?: "ok" | "skipped" | "error";
  reason?: string | null;
  audit_step_count?: number;
  occurrence_count?: number;
  manual_annotation_count?: number;
  search_only_count?: number;
  redaction?: {
    n_entities: number;
    n_mocks: number;
    entity_types?: Record<string, number>;
    has_image: boolean;
    error?: string | null;
  };
}

export interface RedactionDiffSpan {
  start: number;
  end: number;
  original: string;
  mock: string;
  entity_type: string;
  bbox_px?: { x: number; y: number; w: number; h: number; page_index?: number; coord_space?: string } | null;
}

export interface RedactionPayload {
  redacted_text: string;
  diff_spans: RedactionDiffSpan[];
  mapping_index: {
    n_mappings: number;
    entity_types: Record<string, number>;
  } | null;
  has_image: boolean;
}

export interface PiiAuditStep {
  stage_name: string;
  tool: string;
  order: number;
  started_at: string;
  duration_ms: number;
  status: string;
  inputs: string[];
  outputs: string[];
  message?: string;
  metadata?: Record<string, unknown>;
}

export interface PiiOccurrenceEntry {
  text: string;
  entity_type: string;
  page_count: number;
  doc_count: number;
  by_source: Record<string, number>;
}

export interface PiiDetectorCapability {
  name: string;
  display_name: string;
  description: string;
  requires_models: string[];
  jurisdictions: string[];
  entity_types: {
    entity_type: string;
    category: string;
    jurisdictions: string[];
    has_validator: boolean;
  }[];
  config_knobs: { name: string; purpose: string }[];
  architecture?: { stage: string; tool: string; blurb?: string }[];
  customisation?: { name: string; value: string; purpose: string }[];
  user_custom_dictionary?: {
    jurisdictions: Record<string, { entity_type: string; text: string }[]>;
    total_entries: number;
  };
}

export interface PiiRegionSpan {
  start: number;
  end: number;
  region_id: string;
  bbox: { x: number; y: number; w: number; h: number; page_index: number; coord_space: string };
  text_len: number;
}

export interface PiiVisualCode {
  type: "QR_CODE" | "BAR_CODE";
  payload: string;
  bbox_px: { x: number; y: number; w: number; h: number };
  source: "cv2.qrcode" | "pyzbar";
  metadata?: Record<string, unknown>;
}

export interface PiiManualAnnotation {
  annotation_id: string;
  scope: "doc" | "run";
  page_index: number;
  entity_type: string;
  text: string;
  bbox_px?: { x: number; y: number; w: number; h: number };
  jurisdiction?: string | null;
  created_at: string;
}

export interface PiiBenchmarkDocument {
  document_id: string;
  filename: string;
  pdf_kind: PdfKind;
  n_pages: number;
  status: "queued" | "running" | "done" | "error" | "partial";
  started_at?: string | null;
  finished_at?: string | null;
  paired_run_id?: string | null;
  pages: Record<string, Record<string, Record<string, PiiCellSummary>>>; // page -> ocr -> detector -> summary
}

export interface PiiBenchmarkRun {
  pii_run_id: string;
  status: "running" | "done" | "partial";
  started_at?: string;
  finished_at?: string;
  updated_at?: string;
  ocr_producers: string[];
  detector_names: string[];
  jurisdictions: string[];
  paired_run_ids: string[];
  paired_batch_id?: string | null;
  documents: PiiBenchmarkDocument[];
  stats: { total_docs: number; done_docs: number; error_docs: number };
}

export interface PiiCellResult {
  detector_name: string;
  entities: PiiV2Entity[];
  text_len: number;
  latency_ms: number;
  error?: string | null;
  metadata?: Record<string, unknown>;
  source_text?: string;
}

// ---- JSONL dataset benchmark ----------------------------------------------

export interface PiiDatasetMeta {
  dataset_id: string;
  filename: string;
  n_records: number;
  uploaded_at: string;
}

export interface PiiDatasetMetricCounts {
  tp: number;
  fp: number;
  fn: number;
  precision: number;
  recall: number;
  f1: number;
}

export interface PiiDatasetDetectorMetrics {
  overall_exact: PiiDatasetMetricCounts;
  overall_partial: PiiDatasetMetricCounts;
  by_entity_exact: Record<string, PiiDatasetMetricCounts>;
  by_entity_partial: Record<string, PiiDatasetMetricCounts>;
}

export interface PiiDatasetDetectorSummary {
  n_records: number;
  load_time_ms: number;
  latency_ms: { p50: number; p95: number; p99: number; mean: number };
  metrics: PiiDatasetDetectorMetrics;
  false_positive_count: number;
  false_negative_count: number;
  status?: string;
  records_done?: number;
  error?: string;
}

export interface PiiDatasetRecommendation {
  winner_overall_f1?: string | null;
  winner_recall?: string | null;
  winner_precision?: string | null;
  winner_latency_p95?: string | null;
  ranking: { detector: string; f1: number; recall: number; precision: number; p95_ms: number }[];
}

export interface PiiDatasetRun {
  dataset_run_id: string;
  dataset_id: string;
  status: "running" | "done";
  started_at?: string;
  finished_at?: string;
  updated_at?: string;
  detector_names: string[];
  jurisdictions: string[];
  per_detector: Record<string, PiiDatasetDetectorSummary>;
  summary?: {
    per_detector: Record<string, PiiDatasetDetectorSummary>;
    recommendation: PiiDatasetRecommendation;
  };
}

export interface RunState {
  run_id: string;
  status: "running" | "done";
  started_at?: string;
  finished_at?: string;
  updated_at?: string;
  document: { document_id: string; filename: string; pdf_kind: PdfKind; n_pages: number };
  solution_names: string[];
  completed: string[];
  solution_status?: Record<string, SolutionStatusEntry>;
  solution_results: SolutionResult[];
  pii_v2_run_id?: string | null;
}

export interface RunListEntry {
  run_id: string;
  status: "running" | "done";
  started_at?: string;
  finished_at?: string;
  updated_at?: string;
  document: { document_id: string; filename: string; pdf_kind: PdfKind; n_pages: number };
  solution_names: string[];
  solution_status: Record<string, SolutionStatusEntry>;
  completed: string[];
}

export interface RunMetricSnapshot {
  regions: number;
  tables: number;
  pii: number;
  overall_confidence: number;
  duration_ms: number;
  status: SolutionStatus;
}

export interface RunDiff {
  document_id: string;
  run_a: string;
  run_b: string;
  solutions: {
    name: string;
    a: RunMetricSnapshot | null;
    b: RunMetricSnapshot | null;
    delta: Omit<RunMetricSnapshot, "status"> | null;
  }[];
}

export type Category = "tables" | "text" | "pii" | "layout";

export interface CategoryAccept {
  solution: string;
  run_id: string;
  accepted_at: string;
  order: number;
  comment: string;
}

export interface CategoryRejection {
  solution: string;
  run_id: string;
  reason: string;
  rejected_at: string;
}

export interface PageReview {
  solution?: string;
  run_id?: string;
  accepted_at?: string;
  categories?: Partial<Record<Category, CategoryAccept[]>>;
  rejections?: Partial<Record<Category, CategoryRejection[]>>;
}

export interface CompositePage {
  page_index: number;
  sources: Record<Category, string | null>;
  ordered_sources?: Partial<Record<Category, CategoryAccept[]>>;
  tables: TableModel[];
  regions: Region[];
  pii: PiiSpan[];
}

export interface CompositeResult {
  document_id: string;
  filename: string;
  pages: CompositePage[];
}

export interface BenchmarkSelection {
  document_id: string;
  run_id: string;
  page_indices: number[];
}

export interface BenchmarkSummary {
  by_category?: Partial<Record<Category, { winner: string; runners_up?: string[]; limitations?: string[] }>>;
  overall?: { winner: string; rationale: string };
  per_document_notes?: { document_id: string; filename?: string; notes: string }[];
}

export interface BenchmarkAnalysis {
  id: string;
  name: string;
  status: "pending" | "done" | "error";
  created_at: string;
  updated_at?: string;
  selections: BenchmarkSelection[];
  review_snapshot?: Record<string, unknown> | null;
  metrics_snapshot?: Record<string, unknown> | null;
  llm_input_preview?: string | null;
  llm_raw?: string | null;
  llm_summary?: BenchmarkSummary | null;
  error?: string | null;
}

export interface BenchmarkAnalysisListEntry {
  id: string;
  name: string;
  status: "pending" | "done" | "error";
  created_at: string;
  updated_at?: string;
  n_documents: number;
  error?: string | null;
}
