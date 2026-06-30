"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getPiiRun } from "@/lib/api";
import type { PiiBenchmarkRun, PiiCellSummary } from "@/lib/types";
import { PiiCardDetailPanel } from "@/components/PiiCardDetailPanel";
import type { SidePanelTab } from "@/components/PiiSidePanel";

/**
 * Full-screen view of one PII cell — same tabbed surface as the drawer in
 * the dashboard, just rendered inline so the user gets the full viewport.
 *
 * URL: /pii-benchmarks/<id>/cell/<doc_id>/<page>/<ocr>/<detector>?tab=...
 */
export default function PiiCellPage() {
  const params = useParams<{
    id: string;
    document_id: string;
    page_index: string;
    ocr: string;
    detector: string;
  }>();
  const search = useSearchParams();
  const initialTab = (search?.get("tab") as SidePanelTab | null) ?? "image";

  const piiRunId = decodeURIComponent(params.id);
  const documentId = decodeURIComponent(params.document_id);
  const pageIndex = parseInt(params.page_index, 10);
  const ocr = decodeURIComponent(params.ocr);
  const detector = decodeURIComponent(params.detector);

  const [run, setRun] = useState<PiiBenchmarkRun | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPiiRun(piiRunId).then((r) => { if (!cancelled) setRun(r); }).catch((e) => {
      if (!cancelled) setErr(String(e));
    });
    return () => { cancelled = true; };
  }, [piiRunId]);

  if (err) return <main className="container"><p style={{ color: "#cf222e" }}>{err}</p></main>;
  if (!run) return <main className="container"><p className="muted">loading…</p></main>;

  const doc = run.documents.find((d) => d.document_id === documentId);
  const cell: PiiCellSummary | undefined =
    doc?.pages?.[String(pageIndex)]?.[ocr]?.[detector];
  const totalPages = doc?.n_pages ?? 1;

  return (
    <main className="container" style={{ maxWidth: 1400 }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
        <div>
          <Link href={`/pii-benchmarks/${piiRunId}`} className="muted">← back to dashboard</Link>
          <h1 style={{ margin: "4px 0 0", fontSize: 18 }}>
            <code>{ocr}</code> → <code>{detector}</code>
            <span className="muted" style={{ fontSize: 13, fontWeight: 400 }}>
              {" "}· page {pageIndex + 1} of {totalPages}
            </span>
          </h1>
          <div className="muted" style={{ fontSize: 12 }}>{doc?.filename ?? documentId}</div>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <Link href="/pii-benchmarks" className="btn">all PII runs</Link>
          <Link href="/" className="btn">home</Link>
        </div>
      </div>

      <PiiCardDetailPanel
        open
        onClose={() => undefined}
        piiRunId={piiRunId}
        documentId={documentId}
        pageIndex={pageIndex}
        totalPages={totalPages}
        target={{ ocr, detector, cell }}
        initialTab={initialTab}
        pairedRunId={doc?.paired_run_id ?? null}
        mode="fullscreen"
      />
    </main>
  );
}
