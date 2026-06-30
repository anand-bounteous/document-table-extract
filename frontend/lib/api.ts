import type {
  BatchState,
  BenchmarkAnalysis, BenchmarkAnalysisListEntry, BenchmarkSelection,
  CompositeResult, DashboardStats, DocumentMeta, PiiBenchmarkRun, PiiBundle, PiiCellResult, PiiDatasetMeta, PiiDatasetRun, PiiDetectorDescriptor, ReviewRecord, RunDiff, RunListEntry, RunState, SolutionDescriptor,
} from "./types";

const API = "/api";

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function listDocuments(): Promise<{ documents: DocumentMeta[] }> {
  return jget("/documents");
}

export async function uploadDocument(file: File): Promise<DocumentMeta> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${API}/documents`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(`upload: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function getDocument(id: string): Promise<DocumentMeta> {
  return jget(`/documents/${encodeURIComponent(id)}`);
}

export async function listSolutions(): Promise<{ solutions: SolutionDescriptor[] }> {
  return jget("/solutions");
}

export async function startRun(document_id: string, solution_names: string[], dpi?: number) {
  const r = await fetch(`${API}/runs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ document_id, solution_names, dpi }),
  });
  if (!r.ok) throw new Error(`start run: ${r.status} ${await r.text()}`);
  return (await r.json()) as { run_id: string; status: string };
}

export async function getRun(runId: string): Promise<RunState> {
  return jget(`/runs/${runId}`);
}

export async function resumeRun(
  runId: string,
  solutionNames?: string[],
): Promise<{
  run_id: string;
  status: string;
  resumed_solutions: string[];
  kept_solutions: string[];
}> {
  const r = await fetch(`${API}/runs/${encodeURIComponent(runId)}/resume`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(solutionNames ? { solution_names: solutionNames } : {}),
  });
  if (!r.ok) throw new Error(`resume: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function createBatch(
  document_ids: string[],
  solution_names: string[],
  dpi?: number,
): Promise<{ batch_id: string; run_ids: string[] }> {
  const r = await fetch(`${API}/batches`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ document_ids, solution_names, dpi }),
  });
  if (!r.ok) throw new Error(`create batch: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function getBatch(batchId: string): Promise<BatchState> {
  return jget(`/batches/${encodeURIComponent(batchId)}`);
}

export async function listBatches(limit = 50): Promise<{ batches: any[] }> {
  return jget(`/batches?limit=${limit}`);
}

// ---- pii_v2 benchmark API -------------------------------------------------

export async function listPiiDetectors(): Promise<{ detectors: PiiDetectorDescriptor[] }> {
  return jget("/pii-benchmarks/detectors");
}

export async function createPiiRun(body: {
  document_ids: string[];
  detector_names?: string[];
  ocr_producers?: string[];
  jurisdictions?: string[];
  dpi?: number;
  paired_run_ids?: string[];
  paired_batch_id?: string | null;
}): Promise<{ pii_run_id: string; detector_names: string[]; ocr_producers: string[] }> {
  const r = await fetch(`${API}/pii-benchmarks/runs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`create pii run: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function getPiiRun(piiRunId: string): Promise<PiiBenchmarkRun> {
  return jget(`/pii-benchmarks/${encodeURIComponent(piiRunId)}`);
}

export async function resumePiiRun(piiRunId: string): Promise<{
  pii_run_id: string;
  status: string;
  resumed_documents: string[];
}> {
  const r = await fetch(`${API}/pii-benchmarks/${encodeURIComponent(piiRunId)}/resume`, {
    method: "POST",
  });
  if (!r.ok) throw new Error(`resume pii: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function rebuildPiiRedactions(piiRunId: string): Promise<{
  pii_run_id: string;
  status: string;
}> {
  const r = await fetch(
    `${API}/pii-benchmarks/${encodeURIComponent(piiRunId)}/redaction/rebuild`,
    { method: "POST" },
  );
  if (!r.ok) throw new Error(`rebuild redactions: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function listPiiRuns(limit = 50): Promise<{ runs: any[] }> {
  return jget(`/pii-benchmarks?limit=${limit}`);
}

export async function getPiiCell(
  piiRunId: string,
  documentId: string,
  pageIndex: number,
  ocr: string,
  detector: string,
): Promise<PiiCellResult> {
  return jget(
    `/pii-benchmarks/${encodeURIComponent(piiRunId)}/cell/${encodeURIComponent(documentId)}/${pageIndex}/${encodeURIComponent(ocr)}/${encodeURIComponent(detector)}`,
  );
}

export async function getDetectorCapability(name: string): Promise<import("./types").PiiDetectorCapability> {
  return jget(`/pii-benchmarks/detectors/${encodeURIComponent(name)}/capabilities`);
}

export async function getPiiTextLayout(
  piiRunId: string,
  documentId: string,
  pageIndex: number,
  ocr: string,
): Promise<{ region_index: import("./types").PiiRegionSpan[] }> {
  return jget(
    `/pii-benchmarks/${encodeURIComponent(piiRunId)}/text-layout/${encodeURIComponent(documentId)}/${pageIndex}/${encodeURIComponent(ocr)}`,
  );
}

export async function getPiiVisualCodes(
  piiRunId: string,
  documentId: string,
  pageIndex: number,
): Promise<{ codes: import("./types").PiiVisualCode[]; skipped: string[] }> {
  return jget(
    `/pii-benchmarks/${encodeURIComponent(piiRunId)}/visual/${encodeURIComponent(documentId)}/${pageIndex}`,
  );
}

export function piiPageImageUrl(piiRunId: string, documentId: string, pageIndex: number): string {
  return `${API}/pii-benchmarks/${encodeURIComponent(piiRunId)}/page-image/${encodeURIComponent(documentId)}/${pageIndex}`;
}

export function piiRedactedImageUrl(
  piiRunId: string, documentId: string, pageIndex: number, ocr: string, detector: string,
  annotated: boolean = false,
): string {
  const suffix = annotated ? "?annotated=true" : "";
  return `${API}/pii-benchmarks/${encodeURIComponent(piiRunId)}/redaction/${encodeURIComponent(documentId)}/${pageIndex}/${encodeURIComponent(ocr)}/${encodeURIComponent(detector)}/image${suffix}`;
}

export async function getPiiRedaction(
  piiRunId: string, documentId: string, pageIndex: number, ocr: string, detector: string,
): Promise<import("./types").RedactionPayload> {
  return jget(
    `/pii-benchmarks/${encodeURIComponent(piiRunId)}/redaction/${encodeURIComponent(documentId)}/${pageIndex}/${encodeURIComponent(ocr)}/${encodeURIComponent(detector)}`,
  );
}

export function piiRedactionMappingUrl(
  piiRunId: string, documentId: string, pageIndex: number, ocr: string, detector: string,
): string {
  return `${API}/pii-benchmarks/${encodeURIComponent(piiRunId)}/redaction/${encodeURIComponent(documentId)}/${pageIndex}/${encodeURIComponent(ocr)}/${encodeURIComponent(detector)}/mapping?reveal=true`;
}

export async function listManualAnnotations(
  piiRunId: string,
  documentId: string,
): Promise<{ doc_scope: import("./types").PiiManualAnnotation[]; run_scope: import("./types").PiiManualAnnotation[] }> {
  return jget(
    `/pii-benchmarks/${encodeURIComponent(piiRunId)}/manual-annotations/${encodeURIComponent(documentId)}`,
  );
}

export async function addManualAnnotation(
  piiRunId: string,
  documentId: string,
  body: {
    page_index: number;
    entity_type: string;
    text: string;
    bbox_px?: { x: number; y: number; w: number; h: number };
    jurisdiction?: string;
    scope?: "doc" | "run";
  },
): Promise<import("./types").PiiManualAnnotation> {
  const r = await fetch(
    `${API}/pii-benchmarks/${encodeURIComponent(piiRunId)}/manual-annotations/${encodeURIComponent(documentId)}`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!r.ok) throw new Error(`add manual annotation: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function deleteManualAnnotation(
  piiRunId: string,
  documentId: string,
  annotationId: string,
): Promise<void> {
  const r = await fetch(
    `${API}/pii-benchmarks/${encodeURIComponent(piiRunId)}/manual-annotations/${encodeURIComponent(documentId)}/${encodeURIComponent(annotationId)}`,
    { method: "DELETE" },
  );
  if (!r.ok) throw new Error(`delete manual annotation: ${r.status} ${await r.text()}`);
}

export interface ProcessedAnnotation {
  bbox_px: { x: number; y: number; w: number; h: number };
  extracted_text: string;
  visual_codes: import("./types").PiiVisualCode[];
  matched_by: {
    ocr: string;
    detector: string;
    entity_type: string;
    text: string;
    score: number;
    bbox: { x: number; y: number; w: number; h: number };
    iou: number;
    discovery?: string;
  }[];
  suggested_entity_type: string;
  error?: string;
}

export async function processPendingAnnotations(
  piiRunId: string,
  documentId: string,
  pageIndex: number,
  annotations: { bbox_px: { x: number; y: number; w: number; h: number } }[],
): Promise<{ processed_annotations: ProcessedAnnotation[] }> {
  const r = await fetch(
    `${API}/pii-benchmarks/${encodeURIComponent(piiRunId)}/annotations/process`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ document_id: documentId, page_index: pageIndex, annotations }),
    },
  );
  if (!r.ok) throw new Error(`process annotations: ${r.status} ${await r.text()}`);
  return r.json();
}

// ---- JSONL benchmark API --------------------------------------------------

export async function listPiiDatasets(): Promise<{ datasets: PiiDatasetMeta[] }> {
  return jget("/pii-benchmarks/dataset/datasets");
}

export async function uploadPiiDataset(file: File): Promise<PiiDatasetMeta> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${API}/pii-benchmarks/dataset/datasets`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(`upload dataset: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function listPiiDatasetRuns(): Promise<{ runs: any[] }> {
  return jget("/pii-benchmarks/dataset/runs");
}

export async function createPiiDatasetRun(body: {
  dataset_id: string;
  detector_names?: string[];
  jurisdictions?: string[];
}): Promise<{ dataset_run_id: string; detector_names: string[] }> {
  const r = await fetch(`${API}/pii-benchmarks/dataset/runs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`create dataset run: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function getPiiDatasetRun(id: string): Promise<PiiDatasetRun> {
  return jget(`/pii-benchmarks/dataset/runs/${encodeURIComponent(id)}`);
}

export function piiDatasetReportMdUrl(id: string): string {
  return `${API}/pii-benchmarks/dataset/runs/${encodeURIComponent(id)}/report.md`;
}

export function piiDatasetCsvUrl(id: string, detector: string, kind: "false_positives" | "false_negatives"): string {
  return `${API}/pii-benchmarks/dataset/runs/${encodeURIComponent(id)}/${encodeURIComponent(detector)}/${kind}.csv`;
}

export async function getMasterBpmn(): Promise<string> {
  const r = await fetch(`${API}/bpmn/master`, { cache: "no-store" });
  if (!r.ok) throw new Error(`bpmn master: ${r.status}`);
  return r.text();
}

export async function getSolutionBpmn(solutionName: string): Promise<string> {
  const r = await fetch(`${API}/bpmn/${encodeURIComponent(solutionName)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`bpmn ${solutionName}: ${r.status}`);
  return r.text();
}

export async function deleteRun(runId: string): Promise<void> {
  const r = await fetch(`${API}/runs/${encodeURIComponent(runId)}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`delete run: ${r.status} ${await r.text()}`);
}

export function artifactUrl(runId: string, artifactRef: string): string {
  return `${API}/runs/${runId}/artifacts/${encodeURIComponent(artifactRef)}`;
}

export function redactedPdfUrl(runId: string, solutionName: string): string {
  return `${API}/runs/${runId}/solutions/${encodeURIComponent(solutionName)}/redacted-pdf`;
}

export function reportHtmlUrl(runId: string): string {
  return `${API}/runs/${runId}/report.html`;
}
export function reportPdfUrl(runId: string): string {
  return `${API}/runs/${runId}/report.pdf`;
}

export async function getSolutionPii(runId: string, solution: string): Promise<PiiBundle> {
  return jget(`/runs/${runId}/solutions/${encodeURIComponent(solution)}/pii`);
}

export async function getTableCrops(runId: string, solution: string): Promise<import("./types").TableCropsBundle> {
  return jget(`/runs/${runId}/solutions/${encodeURIComponent(solution)}/table-crops`);
}

export async function getReview(documentId: string): Promise<ReviewRecord> {
  return jget(`/reviews/${encodeURIComponent(documentId)}`);
}

export async function acceptPage(documentId: string, pageIndex: number, solution: string, runId: string): Promise<ReviewRecord> {
  const r = await fetch(`${API}/reviews/accept`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ document_id: documentId, page_index: pageIndex, solution, run_id: runId }),
  });
  if (!r.ok) throw new Error(`accept: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function revokePage(documentId: string, pageIndex: number): Promise<ReviewRecord> {
  const r = await fetch(`${API}/reviews/revoke`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ document_id: documentId, page_index: pageIndex }),
  });
  if (!r.ok) throw new Error(`revoke: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function acceptCategory(
  documentId: string, pageIndex: number, category: string, solution: string, runId: string,
  opts: { order?: number; comment?: string } = {},
): Promise<ReviewRecord> {
  const r = await fetch(`${API}/reviews/accept-category`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      document_id: documentId, page_index: pageIndex, category, solution, run_id: runId,
      order: opts.order, comment: opts.comment ?? "",
    }),
  });
  if (!r.ok) throw new Error(`accept-category: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function reorderCategory(documentId: string, pageIndex: number, category: string, orderedSolutions: string[]): Promise<ReviewRecord> {
  const r = await fetch(`${API}/reviews/reorder-category`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ document_id: documentId, page_index: pageIndex, category, ordered_solutions: orderedSolutions }),
  });
  if (!r.ok) throw new Error(`reorder-category: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function commentCategory(documentId: string, pageIndex: number, category: string, solution: string, comment: string): Promise<ReviewRecord> {
  const r = await fetch(`${API}/reviews/comment-category`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ document_id: documentId, page_index: pageIndex, category, solution, comment }),
  });
  if (!r.ok) throw new Error(`comment-category: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function rejectCategory(
  documentId: string, pageIndex: number, category: string, solution: string, runId: string, reason: string, filename = "",
): Promise<ReviewRecord> {
  const r = await fetch(`${API}/reviews/reject-category`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ document_id: documentId, page_index: pageIndex, category, solution, run_id: runId, reason, filename }),
  });
  if (!r.ok) throw new Error(`reject-category: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function unrejectCategory(documentId: string, pageIndex: number, category: string, solution: string): Promise<ReviewRecord> {
  const r = await fetch(`${API}/reviews/unreject-category`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ document_id: documentId, page_index: pageIndex, category, solution }),
  });
  if (!r.ok) throw new Error(`unreject-category: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function revokeCategory(documentId: string, pageIndex: number, category: string, solution?: string): Promise<ReviewRecord> {
  const r = await fetch(`${API}/reviews/revoke-category`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ document_id: documentId, page_index: pageIndex, category, solution }),
  });
  if (!r.ok) throw new Error(`revoke-category: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function getComposite(documentId: string): Promise<CompositeResult> {
  return jget(`/reviews/composite/${encodeURIComponent(documentId)}`);
}

export async function getStats(): Promise<DashboardStats> {
  return jget("/stats");
}

export async function listBenchmarks(): Promise<{ analyses: BenchmarkAnalysisListEntry[] }> {
  return jget("/benchmarks");
}

export async function getBenchmark(id: string): Promise<BenchmarkAnalysis> {
  return jget(`/benchmarks/${id}`);
}

export async function createBenchmark(name: string, selections: BenchmarkSelection[]): Promise<{ id: string; status: string }> {
  const r = await fetch(`${API}/benchmarks/analyze`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ name, selections }),
  });
  if (!r.ok) throw new Error(`create benchmark: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function deleteBenchmark(id: string): Promise<void> {
  const r = await fetch(`${API}/benchmarks/${id}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`delete benchmark: ${r.status} ${await r.text()}`);
}

export async function listRuns(limit = 50): Promise<{ runs: RunListEntry[] }> {
  return jget(`/runs?limit=${limit}`);
}

export function solutionLogUrl(runId: string, solution: string): string {
  return `${API}/runs/${runId}/solutions/${encodeURIComponent(solution)}/log`;
}

export function pdfUrl(documentId: string): string {
  return `${API}/documents/file/${encodeURIComponent(documentId)}`;
}

export async function listDocumentRuns(documentId: string): Promise<{ document_id: string; runs: RunListEntry[] }> {
  return jget(`/documents/runs/${encodeURIComponent(documentId)}`);
}

export async function diffRuns(documentId: string, runA: string, runB: string): Promise<RunDiff> {
  return jget(`/documents/diff/${encodeURIComponent(documentId)}?run_a=${runA}&run_b=${runB}`);
}

export async function mergeRuns(documentId: string, runIds: string[]): Promise<RunState & {
  merged: boolean;
  merged_from_runs: string[];
  page_sources_by_solution: Record<string, Record<string, string>>;
}> {
  const r = await fetch(`${API}/documents/merge/${encodeURIComponent(documentId)}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ run_ids: runIds }),
  });
  if (!r.ok) throw new Error(`merge runs: ${r.status} ${await r.text()}`);
  return r.json();
}
