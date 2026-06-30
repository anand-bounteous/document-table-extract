"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getPiiRun, resumePiiRun } from "@/lib/api";
import type { PiiBenchmarkRun } from "@/lib/types";
import { PiiBenchmarkGrid } from "@/components/PiiBenchmarkGrid";

/**
 * Inline PII benchmark section for the /runs/<id> page.
 *
 * Polls /pii-benchmarks/<paired_pii_run_id> when present and renders the
 * matrix-as-cards for the current page so the user sees both flows together
 * in the run's "execution version".
 */
export function PiiBenchmarkSection({
  piiRunId,
  pageIndex,
  documentId,
}: {
  piiRunId: string;
  pageIndex: number;
  documentId: string;
}) {
  const [run, setRun] = useState<PiiBenchmarkRun | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!piiRunId) return;
    let cancelled = false;
    async function tick() {
      try {
        const r = await getPiiRun(piiRunId);
        if (!cancelled) setRun(r);
        if (r.status !== "done" && !cancelled) setTimeout(tick, 1500);
      } catch (e) {
        if (!cancelled) setErr(String(e));
      }
    }
    tick();
    return () => { cancelled = true; };
  }, [piiRunId]);

  if (err) return <p style={{ color: "#cf222e", fontSize: 12 }}>{err}</p>;
  if (!run) return <p className="muted" style={{ fontSize: 12 }}>loading PII benchmark…</p>;

  const doc = run.documents.find((d) => d.document_id === documentId);
  if (!doc) {
    return (
      <p className="muted" style={{ fontSize: 12 }}>
        PII benchmark did not include this document — see{" "}
        <Link href={`/pii-benchmarks/${piiRunId}`}>full benchmark</Link>.
      </p>
    );
  }

  const stats = _statusBreakdown(doc, run.detector_names);
  const failedDocs = (run.documents ?? []).filter(
    (d) => d.status === "error" || d.status === "partial",
  );

  return (
    <div>
      <div className="row" style={{ gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
        <span className="muted" style={{ fontSize: 11 }}>detectors:</span>
        {run.detector_names.map((d) => (
          <span key={d} style={{
            fontSize: 11,
            padding: "1px 8px",
            background: "#8250df18",
            border: "1px solid #8250df44",
            color: "#8250df",
            borderRadius: 999,
          }}>
            <code>{d}</code>
          </span>
        ))}
        <span style={{ flex: 1 }} />
        <span className={`pill ${doc.status === "done" ? "ok" : "running"}`}>{doc.status}</span>
        {failedDocs.length > 0 && (
          <button
            className="btn primary"
            disabled={run.status === "running"}
            onClick={async () => {
              try {
                await resumePiiRun(piiRunId);
              } catch (e) {
                alert(`PII resume failed: ${e}`);
              }
            }}
            style={{ padding: "2px 10px", fontSize: 11 }}
            title="re-run only failed documents on this same pii_run_id"
          >
            Resume {failedDocs.length} PII ▶
          </button>
        )}
        <Link href={`/pii-benchmarks/${piiRunId}`} className="btn" style={{ padding: "2px 10px", fontSize: 11 }}>
          full dashboard ↗
        </Link>
      </div>

      <div className="row" style={{ flexWrap: "wrap", gap: 4, fontSize: 11, marginBottom: 10 }}>
        {Object.entries(stats).map(([k, n]) =>
          n > 0 ? (
            <span
              key={k}
              style={{
                padding: "1px 8px",
                border: "1px solid var(--border)",
                background: "#f6f8fa",
                borderRadius: 999,
              }}
            >
              {k}: {n}
            </span>
          ) : null,
        )}
      </div>

      <PiiBenchmarkGrid
        piiRunId={piiRunId}
        documentId={documentId}
        pageIndex={pageIndex}
        ocrProducers={run.ocr_producers}
        detectorNames={run.detector_names}
        pages={doc.pages}
        pairedRunId={doc.paired_run_id ?? null}
        totalPages={doc.n_pages || 1}
        onResumePiiDoc={async () => {
          try {
            await resumePiiRun(piiRunId);
          } catch (e) {
            alert(`PII resume failed: ${e}`);
          }
        }}
      />
    </div>
  );
}

function _statusBreakdown(
  doc: { pages: Record<string, Record<string, Record<string, { status?: string }>>> },
  detectorNames: string[],
): Record<string, number> {
  const counts: Record<string, number> = { ok: 0, skipped: 0, error: 0, pending: 0 };
  for (const pageKey of Object.keys(doc.pages ?? {})) {
    const page = doc.pages[pageKey];
    for (const ocr of Object.keys(page ?? {})) {
      for (const det of detectorNames) {
        const cell = page[ocr]?.[det];
        const s = cell?.status ?? "pending";
        counts[s] = (counts[s] ?? 0) + 1;
      }
    }
  }
  return counts;
}
