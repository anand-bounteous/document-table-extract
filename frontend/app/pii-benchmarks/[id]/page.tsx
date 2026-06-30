"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getPiiRun, rebuildPiiRedactions, resumePiiRun } from "@/lib/api";
import type { PiiBenchmarkRun, PiiBenchmarkDocument } from "@/lib/types";
import { PiiBenchmarkGrid } from "@/components/PiiBenchmarkGrid";

export default function PiiBenchmarkPage() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<PiiBenchmarkRun | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    async function tick() {
      try {
        const r = await getPiiRun(id);
        if (!cancelled) setRun(r);
        if (r.status !== "done" && !cancelled) setTimeout(tick, 1500);
      } catch (e) {
        if (!cancelled) setErr(String(e));
      }
    }
    tick();
    return () => { cancelled = true; };
  }, [id]);

  if (err) return <main className="container"><p style={{ color: "#cf222e" }}>{err}</p></main>;
  if (!run) return <main className="container"><p className="muted">loading…</p></main>;

  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <h1 style={{ marginBottom: 4 }}>PII benchmark · {id}</h1>
        <div className="row" style={{ gap: 8 }}>
          {(() => {
            const failed = (run.documents ?? []).filter(
              (d) => d.status === "error" || d.status === "partial",
            );
            if (failed.length === 0) return null;
            return (
              <button
                className="btn primary"
                disabled={run.status === "running"}
                onClick={async () => {
                  try {
                    await resumePiiRun(id);
                  } catch (e) {
                    alert(`resume failed: ${e}`);
                  }
                }}
                title="re-run only documents that failed, keeping the same pii_run_id"
              >
                Resume {failed.length} failed ▶
              </button>
            );
          })()}
          <button
            className="btn"
            onClick={async () => {
              if (!confirm(
                "Re-run redaction for every cell in this pii_run? This re-bakes the redacted_page*.png files using the correct doc-specific source images. Doesn't re-detect. Runs in the background.",
              )) return;
              try {
                await rebuildPiiRedactions(id);
                alert("Rebuild scheduled — refresh in a few seconds to see the corrected images.");
              } catch (e) {
                alert(`rebuild failed: ${e}`);
              }
            }}
            title="Re-bake redaction PNGs for older pii_runs whose images were written with the multi-doc source-image bug"
          >
            ↻ rebuild redactions
          </button>
          <Link href="/pii-benchmarks" className="btn">← list</Link>
          <Link href="/" className="btn">home</Link>
        </div>
      </div>
      <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
        {run.documents.length} doc{run.documents.length !== 1 ? "s" : ""} · {" "}
        {run.detector_names.length} detector{run.detector_names.length !== 1 ? "s" : ""} · {" "}
        {run.ocr_producers.length} OCR producer{run.ocr_producers.length !== 1 ? "s" : ""} · {" "}
        <span className={`pill ${run.status === "done" ? "ok" : "running"}`}>{run.status}</span>
        {run.paired_batch_id && (
          <> · paired batch <Link href={`/batches/${run.paired_batch_id}`}><code>{run.paired_batch_id}</code></Link></>
        )}
      </div>
      <div className="row" style={{ flexWrap: "wrap", gap: 4, fontSize: 11, marginBottom: 12 }}>
        <span className="muted">jurisdictions:</span>
        {run.jurisdictions.map((j) => (
          <span key={j} style={{ padding: "1px 8px", border: "1px solid var(--border)", borderRadius: 999 }}>{j}</span>
        ))}
      </div>

      {run.documents.map((doc) => (
        <PiiDocCard key={doc.document_id} doc={doc} run={run} />
      ))}
    </main>
  );
}

function PiiDocCard({ doc, run }: { doc: PiiBenchmarkDocument; run: PiiBenchmarkRun }) {
  const statusColor: Record<string, string> = {
    queued: "#9a6700",
    running: "#0969da",
    done: "#1a7f37",
    error: "#cf222e",
  };
  const color = statusColor[doc.status] ?? "#57606a";
  const pages = Object.keys(doc.pages).map((k) => parseInt(k, 10)).sort((a, b) => a - b);

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="row" style={{ alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <strong>{doc.filename}</strong>
          <div className="muted" style={{ fontSize: 11 }}>
            {doc.pdf_kind} · {doc.n_pages} page{doc.n_pages !== 1 ? "s" : ""}
          </div>
        </div>
        <div className="row" style={{ gap: 6 }}>
          <span
            style={{
              background: color + "1a",
              color,
              border: `1px solid ${color}55`,
              padding: "2px 10px",
              borderRadius: 999,
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            {doc.status}
          </span>
          {doc.paired_run_id && (
            <Link className="btn" href={`/runs/${doc.paired_run_id}`} style={{ padding: "2px 10px", fontSize: 12 }}>
              🔗 OCR run ↗
            </Link>
          )}
        </div>
      </div>

      {pages.length === 0 && doc.status !== "done" && (
        <p className="muted" style={{ marginTop: 8, fontSize: 12 }}>waiting for first page…</p>
      )}

      {pages.map((p) => (
        <PiiPageSections
          key={p}
          piiRunId={run.pii_run_id}
          documentId={doc.document_id}
          pageIndex={p}
          ocrProducers={run.ocr_producers}
          detectorNames={run.detector_names}
          pages={doc.pages}
          pairedRunId={doc.paired_run_id ?? null}
          totalPages={doc.n_pages || pages.length}
        />
      ))}
    </div>
  );
}

function PiiPageSections(props: {
  piiRunId: string;
  documentId: string;
  pageIndex: number;
  ocrProducers: string[];
  detectorNames: string[];
  pages: Record<string, Record<string, Record<string, import("@/lib/types").PiiCellSummary>>>;
  pairedRunId: string | null;
  totalPages: number;
}) {
  const { piiRunId, documentId, pageIndex, ocrProducers, detectorNames, pages, pairedRunId, totalPages } = props;
  const pageMatrix = pages[String(pageIndex)] ?? {};
  // Counts across all (ocr × detector) cells on this page, per category.
  const categoryTotals: Record<string, number> = { PII: 0, Network: 0, Location: 0, Visual: 0 };
  for (const ocr of Object.keys(pageMatrix)) {
    for (const det of Object.keys(pageMatrix[ocr])) {
      const cc = pageMatrix[ocr][det].category_counts ?? {};
      for (const [k, v] of Object.entries(cc)) {
        categoryTotals[k] = (categoryTotals[k] ?? 0) + (v as number);
      }
    }
  }
  return (
    <div style={{ marginTop: 16 }}>
      <h4 style={{ margin: "6px 0", fontSize: 14, borderBottom: "1px solid var(--border)", paddingBottom: 4 }}>
        page {pageIndex + 1}
        <span className="muted" style={{ fontWeight: 400, marginLeft: 8, fontSize: 11 }}>
          totals: PII {categoryTotals.PII} · Network {categoryTotals.Network} · Location {categoryTotals.Location} · Visual {categoryTotals.Visual}
        </span>
      </h4>
      <CategorySection
        title="PII identifiers"
        category="PII"
        {...{ piiRunId, documentId, pageIndex, ocrProducers, detectorNames, pages, pairedRunId, totalPages }}
      />
      {categoryTotals.Network > 0 && (
        <CategorySection
          title="Network identifiers"
          category="Network"
          {...{ piiRunId, documentId, pageIndex, ocrProducers, detectorNames, pages, pairedRunId, totalPages }}
        />
      )}
      {categoryTotals.Location > 0 && (
        <CategorySection
          title="Location identifiers"
          category="Location"
          {...{ piiRunId, documentId, pageIndex, ocrProducers, detectorNames, pages, pairedRunId, totalPages }}
        />
      )}
      <VisualSection
        piiRunId={piiRunId}
        documentId={documentId}
        pageIndex={pageIndex}
        pairedRunId={pairedRunId}
        totalPages={totalPages}
      />
    </div>
  );
}

function CategorySection({
  title,
  category,
  piiRunId,
  documentId,
  pageIndex,
  ocrProducers,
  detectorNames,
  pages,
  pairedRunId,
  totalPages,
}: {
  title: string;
  category: "PII" | "Network" | "Location";
  piiRunId: string;
  documentId: string;
  pageIndex: number;
  ocrProducers: string[];
  detectorNames: string[];
  pages: Record<string, Record<string, Record<string, import("@/lib/types").PiiCellSummary>>>;
  pairedRunId: string | null;
  totalPages: number;
}) {
  return (
    <details open style={{ marginTop: 10 }}>
      <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 12 }}>{title}</summary>
      <div style={{ marginTop: 8 }}>
        <PiiBenchmarkGrid
          piiRunId={piiRunId}
          documentId={documentId}
          pageIndex={pageIndex}
          ocrProducers={ocrProducers}
          detectorNames={detectorNames}
          pages={pages}
          pairedRunId={pairedRunId}
          totalPages={totalPages}
          categoryFilter={category}
          onResumePiiDoc={async () => {
            try {
              await resumePiiRun(piiRunId);
            } catch (e) {
              alert(`PII resume failed: ${e}`);
            }
          }}
        />
      </div>
    </details>
  );
}

function VisualSection({
  piiRunId,
  documentId,
  pageIndex,
  pairedRunId,
  totalPages,
}: {
  piiRunId: string;
  documentId: string;
  pageIndex: number;
  pairedRunId: string | null;
  totalPages: number;
}) {
  const [data, setData] = useState<{
    codes: import("@/lib/types").PiiVisualCode[];
    skipped: string[];
  } | null>(null);

  useEffect(() => {
    import("@/lib/api").then(({ getPiiVisualCodes }) =>
      getPiiVisualCodes(piiRunId, documentId, pageIndex).then(setData).catch(() => setData({ codes: [], skipped: ["error"] })),
    );
  }, [piiRunId, documentId, pageIndex]);

  if (!data) return null;
  if (data.codes.length === 0 && data.skipped.every((s) => s.includes("pyzbar"))) {
    // Render a minimal note only when the only "issue" is missing pyzbar.
    return (
      <details style={{ marginTop: 10 }}>
        <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 12 }}>
          Visual identifiers <span className="muted" style={{ fontWeight: 400 }}>(none on this page)</span>
        </summary>
        <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
          {data.skipped.join(" · ") || "no QR / barcode detected"}
        </div>
      </details>
    );
  }
  if (data.codes.length === 0) return null;

  return (
    <details open style={{ marginTop: 10 }}>
      <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 12 }}>
        Visual identifiers <span className="muted" style={{ fontWeight: 400 }}>({data.codes.length})</span>
      </summary>
      <div
        style={{
          marginTop: 8,
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
          gap: 10,
        }}
      >
        {data.codes.map((c, i) => (
          <div key={i} className="card">
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 4 }}>
              <code style={{ fontWeight: 600 }}>{c.type}</code>
              <span className="muted" style={{ fontSize: 11 }}>{c.source}</span>
            </div>
            <div style={{ fontSize: 12, wordBreak: "break-all", marginBottom: 4 }}>
              {c.payload}
            </div>
            <div className="muted" style={{ fontSize: 10 }}>
              bbox: {Math.round(c.bbox_px.x)},{Math.round(c.bbox_px.y)} · {Math.round(c.bbox_px.w)}×{Math.round(c.bbox_px.h)} px
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}
