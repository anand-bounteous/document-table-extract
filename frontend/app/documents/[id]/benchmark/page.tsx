"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { getComposite, getReview, pdfUrl } from "@/lib/api";
import type { Category, CompositeResult, ReviewRecord } from "@/lib/types";
import { CATEGORY_LABEL } from "@/lib/solutionDocs";
import { TableWithCoordsToggle } from "@/components/TableWithCoordsToggle";

const CAT_ORDER: Category[] = ["tables", "text", "pii", "layout"];

export default function BenchmarkPage() {
  const { id } = useParams<{ id: string }>();
  const documentId = decodeURIComponent(id);
  const [composite, setComposite] = useState<CompositeResult | null>(null);
  const [review, setReview] = useState<ReviewRecord | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      getComposite(documentId),
      getReview(documentId).catch(() => null),
    ]).then(([c, r]) => { setComposite(c); setReview(r); }).catch((e) => setErr(String(e)));
  }, [documentId]);

  if (err) return <main className="container"><p style={{ color: "#cf222e" }}>{err}</p></main>;
  if (!composite) return <main className="container"><p className="muted">loading composite…</p></main>;

  function downloadJson() {
    const blob = new Blob([JSON.stringify(composite, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${composite!.filename || documentId}.composite.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <div>
          <Link href="/" className="muted">← back to home</Link>
          <h1 style={{ marginBottom: 4 }}>Benchmark composite</h1>
          <div className="muted" style={{ fontSize: 13 }}>{composite.filename || documentId}</div>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <a className="btn" href={pdfUrl(documentId)} target="_blank" rel="noreferrer">view PDF ↗</a>
          <Link className="btn" href={`/documents/${encodeURIComponent(documentId)}/history`}>history</Link>
          <button className="btn primary" onClick={downloadJson}>download composite JSON</button>
        </div>
      </div>

      {composite.pages.length === 0 && (
        <p className="muted" style={{ marginTop: 12 }}>No accepted reviews for this document yet — run it through a few solutions and accept categories on the run page.</p>
      )}

      {composite.pages.map((p) => (
        <article key={p.page_index} className="card" style={{ marginTop: 14 }}>
          <h2 style={{ marginTop: 0 }}>Page {p.page_index + 1}</h2>

          <div style={{ marginBottom: 12 }}>
            {CAT_ORDER.map((cat) => {
              const ordered = p.ordered_sources?.[cat] ?? [];
              const winner = p.sources[cat];
              const pageRejections = review?.pages?.[String(p.page_index)]?.rejections?.[cat] ?? [];
              return (
                <div key={cat} style={{ marginTop: 6 }}>
                  <span className="pill" style={{ background: winner ? "#dafbe1" : "#fff8c5", color: winner ? "#1a7f37" : "#9a6700" }}>
                    {CATEGORY_LABEL[cat]}: {winner ?? "—"}
                  </span>
                  {ordered.length > 1 && (
                    <ol style={{ margin: "4px 0 0 22px", padding: 0, fontSize: 12 }}>
                      {ordered.map((e) => (
                        <li key={e.solution} style={{ marginTop: 2 }}>
                          <strong>{e.solution}</strong>
                          {e.comment ? <> — <em>{e.comment}</em></> : <span className="muted"> — (no comment)</span>}
                        </li>
                      ))}
                    </ol>
                  )}
                  {ordered.length === 1 && ordered[0].comment && (
                    <div className="muted" style={{ marginLeft: 22, fontSize: 12 }}>
                      — <em>{ordered[0].comment}</em>
                    </div>
                  )}
                  {pageRejections.length > 0 && (
                    <ul style={{ margin: "4px 0 0 22px", padding: 0, fontSize: 12, listStyle: "none" }}>
                      {pageRejections.map((rj) => (
                        <li key={rj.solution} style={{ marginTop: 2, color: "#cf222e" }}>
                          <strong>✗ {rj.solution}</strong>
                          {rj.reason ? <> — <em>{rj.reason}</em></> : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>

          <h3 style={{ marginTop: 12 }}>Tables ({p.tables.length})</h3>
          {p.tables.length === 0 && <p className="muted" style={{ fontSize: 12 }}>none</p>}
          {p.tables.map((t, ti) => (
            <details key={ti} open={ti === 0} style={{ marginTop: 6 }}>
              <summary>{t.n_rows} × {t.n_cols} ({t.border_mode})</summary>
              <TableWithCoordsToggle nRows={t.n_rows} nCols={t.n_cols} cells={t.cells} />
            </details>
          ))}

          <h3 style={{ marginTop: 12 }}>Text regions ({p.regions.length})</h3>
          {p.regions.length === 0 && <p className="muted" style={{ fontSize: 12 }}>none</p>}
          {p.regions.length > 0 && (
            <details>
              <summary>show first 40</summary>
              <table style={{ marginTop: 6 }}>
                <thead><tr><th>type</th><th>conf</th><th>text</th></tr></thead>
                <tbody>
                  {p.regions.slice(0, 40).map((r) => (
                    <tr key={r.id}>
                      <td><code style={{ fontSize: 11 }}>{r.type}</code></td>
                      <td>{r.confidence.toFixed(2)}</td>
                      <td style={{ whiteSpace: "pre-wrap" }}>{r.text.slice(0, 200)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}

          <h3 style={{ marginTop: 12 }}>PII ({p.pii.length})</h3>
          {p.pii.length === 0 && <p className="muted" style={{ fontSize: 12 }}>none</p>}
          {p.pii.length > 0 && (
            <table>
              <thead><tr><th>entity</th><th>masked</th><th>score</th></tr></thead>
              <tbody>
                {p.pii.map((s, i) => (
                  <tr key={i}>
                    <td><span className="pill" style={{ background: "#ffebe9", color: "#cf222e" }}>{s.entity_type}</span></td>
                    <td><code>{s.masked_value}</code></td>
                    <td>{s.score.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </article>
      ))}
    </main>
  );
}
