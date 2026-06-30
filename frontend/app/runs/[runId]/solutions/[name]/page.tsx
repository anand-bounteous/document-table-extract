"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { artifactUrl, getRun, pdfUrl, redactedPdfUrl, solutionLogUrl } from "@/lib/api";
import { TableWithCoordsToggle } from "@/components/TableWithCoordsToggle";
import type { RunState, SolutionResult } from "@/lib/types";
import { SOLUTION_DOCS } from "@/lib/solutionDocs";
import { AnnotatedImageViewer } from "@/components/AnnotatedImageViewer";
import { AuditTimeline } from "@/components/AuditTimeline";
import { CustomTablePanel } from "@/components/CustomTablePanel";
import { TableCropPanel } from "@/components/TableCropPanel";
import { Mermaid } from "@/components/Mermaid";
import { RegionTable } from "@/components/RegionTable";
import { PiiPanel } from "@/components/PiiPanel";

export default function SolutionDetailPage() {
  const { runId, name } = useParams<{ runId: string; name: string }>();
  const [run, setRun] = useState<RunState | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    let stop = false;
    async function tick() {
      try {
        const data = await getRun(runId);
        if (!stop) setRun(data);
        if (data.status !== "done" && !stop) setTimeout(tick, 2000);
      } catch (e) { if (!stop) setErr(String(e)); }
    }
    tick();
    return () => { stop = true; };
  }, [runId]);

  const sol: SolutionResult | undefined = useMemo(
    () => run?.solution_results.find((s) => s.solution_name === name),
    [run, name]
  );

  if (err) return <main className="container"><p style={{ color: "#cf222e" }}>{err}</p></main>;
  if (!run) return <main className="container"><p className="muted">loading run…</p></main>;
  if (!sol) return <main className="container"><p>solution <code>{name}</code> not in this run.</p></main>;

  const page = sol.pages.find((p) => p.page_index === pageIndex) ?? sol.pages[0];
  const tablesOnPage = page?.tables ?? [];
  const piiCount = page?.regions.reduce((n, r) => n + r.pii_spans.length, 0) ?? 0;

  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8, gap: 12, flexWrap: "wrap" }}>
        <div>
          <Link href={`/runs/${runId}`} className="muted">← back to run</Link>
          <h1 style={{ margin: "4px 0 0" }}>{sol.solution_name}</h1>
          <div className="muted" style={{ fontSize: 13 }}>
            doc <code>{run.document.filename}</code> · {run.document.n_pages} pages ·{" "}
            <span className={`pill ${sol.status}`}>{sol.status}</span>{" "}
            <span className="pill">overall conf {sol.overall_confidence.toFixed(2)}</span>{" "}
            <span className="pill">{sol.timings.total_ms.toFixed(0)} ms total</span>
          </div>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <a className="btn" href={pdfUrl(run.document.document_id)} target="_blank" rel="noreferrer">view PDF ↗</a>
          <a className="btn" href={solutionLogUrl(runId, name)} target="_blank" rel="noreferrer">log ↗</a>
        </div>
      </div>

      {sol.status === "error" && (
        <div className="card" style={{ background: "#ffebe9", borderColor: "#ffaaaa", marginBottom: 12 }}>
          <strong>Error:</strong> <code>{sol.error}</code>
        </div>
      )}

      {SOLUTION_DOCS[name] && <AboutSolution name={name} />}

      <h2 style={{ marginTop: 18 }}>Pipeline steps</h2>
      <AuditTimeline audit={sol.audit} />

      <h2 style={{ marginTop: 18 }}>Pages</h2>
      <div className="row" style={{ marginBottom: 12, flexWrap: "wrap" }}>
        {sol.pages.map((p) => (
          <button
            key={p.page_index}
            className={`btn ${p.page_index === pageIndex ? "primary" : ""}`}
            onClick={() => setPageIndex(p.page_index)}
          >
            {p.page_index + 1}
          </button>
        ))}
      </div>

      {page && (
        <div className="grid" style={{ gridTemplateColumns: "1.4fr 1fr" }}>
          <div>
            <AnnotatedImageViewer runId={runId} page={page} caption={`${sol.solution_name} · page ${page.page_index + 1}`} />
          </div>
          <div>
            <div className="card" style={{ marginBottom: 12 }}>
              <strong>Page {page.page_index + 1}</strong>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                {page.width} × {page.height}px @ {page.dpi} DPI · {page.regions.length} regions · {page.tables.length} tables · {piiCount} PII
              </div>
            </div>
            <div className="card" style={{ marginBottom: 12 }}>
              <strong>Regions</strong>
              <RegionTable regions={page.regions} />
            </div>
            <NativePdfExtras
              runId={runId}
              solutionName={sol.solution_name}
              pageIndex={page.page_index}
              piiCount={piiCount}
            />
            {tablesOnPage.length > 0 && (
              <div className="card" style={{ marginBottom: 12 }}>
                <strong>Tables</strong>
                {tablesOnPage.map((t, ti) => (
                  <details key={ti} open={ti === 0} style={{ marginTop: 6 }}>
                    <summary>{t.n_rows} × {t.n_cols} ({t.border_mode})</summary>
                    <TableWithCoordsToggle nRows={t.n_rows} nCols={t.n_cols} cells={t.cells} />
                  </details>
                ))}
              </div>
            )}
            <div className="card" style={{ marginBottom: 12 }}>
              <CustomTablePanel page={page} />
            </div>
            <div className="card" style={{ marginBottom: 12 }}>
              <strong>Table crops</strong>
              <TableCropPanel runId={runId} solution={sol.solution_name} pageIndex={page.page_index} />
            </div>
            <div className="card">
              <PiiPanel runId={runId} solution={sol.solution_name} pageIndex={page.page_index} />
            </div>
          </div>
        </div>
      )}

      <h2 style={{ marginTop: 18 }}>Stage timings</h2>
      <table style={{ maxWidth: 600 }}>
        <thead><tr><th>stage</th><th>ms</th></tr></thead>
        <tbody>
          {Object.entries(sol.timings.by_stage).map(([k, v]) => (
            <tr key={k}><td>{k}</td><td>{v.toFixed(0)}</td></tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}

function AboutSolution({ name }: { name: string }) {
  const doc = SOLUTION_DOCS[name];
  if (!doc) return null;
  return (
    <section className="card" style={{ marginTop: 12 }}>
      <h2 style={{ marginTop: 0 }}>About {doc.display_name}</h2>
      <p style={{ marginTop: 4 }}>{doc.long_description}</p>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12, marginTop: 8 }}>
        <div>
          <strong>Prerequisites</strong>
          <ul style={{ margin: "4px 0 0 18px", padding: 0 }}>
            {doc.prerequisites.map((p, i) => <li key={i} style={{ fontSize: 12 }} dangerouslySetInnerHTML={{ __html: renderInlineCode(p) }} />)}
          </ul>
        </div>
        <div>
          <strong>Good at</strong>
          <ul style={{ margin: "4px 0 0 18px", padding: 0 }}>
            {doc.good_at.map((p, i) => <li key={i} style={{ fontSize: 12 }}>{p}</li>)}
          </ul>
        </div>
        <div>
          <strong>Weak at</strong>
          <ul style={{ margin: "4px 0 0 18px", padding: 0 }}>
            {doc.weak_at.map((p, i) => <li key={i} style={{ fontSize: 12 }}>{p}</li>)}
          </ul>
        </div>
      </div>
      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
        <Mermaid source={doc.mermaid_flow} caption="Stage flow" />
        <Mermaid source={doc.mermaid_sequence} caption="Sequence" />
      </div>
      <div style={{ marginTop: 12 }}>
        <strong>How to read the result</strong>
        <p style={{ fontSize: 13, marginTop: 4 }} dangerouslySetInnerHTML={{ __html: renderInlineCode(doc.interpretation) }} />
      </div>
    </section>
  );
}

function renderInlineCode(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function NativePdfExtras({
  runId,
  solutionName,
  pageIndex,
  piiCount,
}: {
  runId: string;
  solutionName: string;
  pageIndex: number;
  piiCount: number;
}) {
  // Only render for the two native-PDF solutions where these artifacts can
  // actually exist. (The template artifacts are written by pymupdf_native
  // when settings.native_pymupdf_emit_template is true; the redacted-PDF
  // route works for any solution that detected pii_spans.)
  const isNativePyMuPDF = solutionName === "native_pymupdf";
  const isNativePdfPlumber = solutionName === "native_pdfplumber";
  if (!isNativePyMuPDF && !isNativePdfPlumber && piiCount === 0) return null;

  const templatePdfRef = `${solutionName}:pymupdf_native/template/template-${String(pageIndex).padStart(3, "0")}.pdf`;
  const templatePngRef = `${solutionName}:pymupdf_native/template/template-${String(pageIndex).padStart(3, "0")}.png`;

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <strong>Native PDF extras</strong>
      <p className="muted" style={{ fontSize: 11, margin: "4px 0 8px" }}>
        Template = page with every text run redacted (graphics + images intact).
        Redacted PDF = vector-safe download with detected PII bboxes wiped via
        PyMuPDF apply_redactions.
      </p>
      <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
        {isNativePyMuPDF && (
          <>
            <a
              className="btn"
              href={artifactUrl(runId, templatePdfRef)}
              target="_blank"
              rel="noreferrer"
              download={`template-page-${pageIndex + 1}.pdf`}
              title="Vector PDF, text removed"
            >
              ⬇ template page (PDF)
            </a>
            <a
              className="btn"
              href={artifactUrl(runId, templatePngRef)}
              target="_blank"
              rel="noreferrer"
              download={`template-page-${pageIndex + 1}.png`}
              title="Raster PNG of the redacted-text page"
            >
              ⬇ template page (PNG)
            </a>
          </>
        )}
        {piiCount > 0 && (
          <a
            className="btn primary"
            href={redactedPdfUrl(runId, solutionName)}
            target="_blank"
            rel="noreferrer"
            download={`${solutionName}-redacted.pdf`}
            title={`Vector-safe PDF with all detected PII (${piiCount}) wiped`}
          >
            ⬇ redacted PDF (whole doc · {piiCount} PII)
          </a>
        )}
      </div>
    </div>
  );
}
