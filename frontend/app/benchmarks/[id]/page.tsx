"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { getBenchmark, pdfUrl } from "@/lib/api";
import type { BenchmarkAnalysis, Category } from "@/lib/types";

const CATEGORIES: Category[] = ["tables", "text", "pii", "layout"];

export default function BenchmarkDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [rec, setRec] = useState<BenchmarkAnalysis | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let stop = false;
    async function tick() {
      try {
        const data = await getBenchmark(id);
        if (!stop) setRec(data);
        if (data.status === "pending" && !stop) setTimeout(tick, 2000);
      } catch (e) { if (!stop) setErr(String(e)); }
    }
    tick();
    return () => { stop = true; };
  }, [id]);

  if (err) return <main className="container"><p style={{ color: "#cf222e" }}>{err}</p></main>;
  if (!rec) return <main className="container"><p className="muted">loading…</p></main>;

  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <div>
          <Link href="/benchmarks" className="muted">← back to analyses</Link>
          <h1 style={{ marginBottom: 4 }}>{rec.name}</h1>
          <div className="muted" style={{ fontSize: 13 }}>
            <code>{rec.id}</code> ·{" "}
            <span className={`pill ${rec.status === "done" ? "ok" : rec.status === "error" ? "error" : "running"}`}>
              {rec.status}
            </span>
            {" · created "}
            {new Date(rec.created_at).toLocaleString()}
          </div>
        </div>
      </div>

      {rec.status === "error" && (
        <div className="card" style={{ background: "#ffebe9", borderColor: "#ffaaaa", marginTop: 12 }}>
          <strong>Error:</strong> <code>{rec.error}</code>
        </div>
      )}

      {rec.status === "pending" && (
        <p className="muted" style={{ marginTop: 12 }}>
          Calling Claude… this can take 30–90 s depending on payload size.
        </p>
      )}

      <h2 style={{ marginTop: 18 }}>Selections</h2>
      <table>
        <thead><tr><th>document</th><th>run</th><th>pages</th><th>PDF</th></tr></thead>
        <tbody>
          {rec.selections.map((s) => (
            <tr key={`${s.document_id}-${s.run_id}`}>
              <td>{s.document_id}</td>
              <td><Link href={`/runs/${s.run_id}`}><code>{s.run_id}</code></Link></td>
              <td>{s.page_indices.map((p) => p + 1).join(", ")}</td>
              <td><a className="btn" href={pdfUrl(s.document_id)} target="_blank" rel="noreferrer">view ↗</a></td>
            </tr>
          ))}
        </tbody>
      </table>

      {rec.llm_summary && (
        <>
          <h2 style={{ marginTop: 18 }}>By category</h2>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12 }}>
            {CATEGORIES.map((cat) => {
              const block = rec.llm_summary?.by_category?.[cat];
              return (
                <div key={cat} className="card">
                  <strong style={{ textTransform: "capitalize" }}>{cat}</strong>
                  {!block && <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>—</p>}
                  {block && (
                    <>
                      <div className="row" style={{ marginTop: 4 }}>
                        <span className="pill ok">winner: {block.winner}</span>
                      </div>
                      {block.runners_up && block.runners_up.length > 0 && (
                        <div style={{ fontSize: 12, marginTop: 6 }}>
                          <strong>Runners-up:</strong>{" "}
                          {block.runners_up.map((r, i) => (
                            <span key={i} className="pill" style={{ marginRight: 4 }}>{r}</span>
                          ))}
                        </div>
                      )}
                      {block.limitations && block.limitations.length > 0 && (
                        <div style={{ marginTop: 8 }}>
                          <strong style={{ fontSize: 12 }}>Limitations</strong>
                          <ul style={{ margin: "4px 0 0 18px", padding: 0, fontSize: 12 }}>
                            {block.limitations.map((l, i) => <li key={i}>{l}</li>)}
                          </ul>
                        </div>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>

          {rec.llm_summary.overall && (
            <div className="card" style={{ marginTop: 12 }}>
              <strong>Overall</strong>
              <div className="row" style={{ marginTop: 4 }}>
                <span className="pill ok">winner: {rec.llm_summary.overall.winner}</span>
              </div>
              <p style={{ fontSize: 13, marginTop: 6 }}>{rec.llm_summary.overall.rationale}</p>
            </div>
          )}

          {rec.llm_summary.per_document_notes && rec.llm_summary.per_document_notes.length > 0 && (
            <>
              <h2 style={{ marginTop: 18 }}>Per-document notes</h2>
              {rec.llm_summary.per_document_notes.map((n, i) => (
                <div key={i} className="card" style={{ marginTop: 8 }}>
                  <strong>{n.filename || n.document_id}</strong>
                  <p style={{ fontSize: 13, marginTop: 4 }}>{n.notes}</p>
                </div>
              ))}
            </>
          )}
        </>
      )}

      <details style={{ marginTop: 18 }}>
        <summary className="muted">Raw LLM input</summary>
        <pre style={{ fontSize: 11, background: "#f6f8fa", padding: 8, borderRadius: 4, overflow: "auto" }}>
{rec.llm_input_preview}
        </pre>
      </details>
      {rec.llm_raw && (
        <details style={{ marginTop: 8 }}>
          <summary className="muted">Raw LLM response</summary>
          <pre style={{ fontSize: 11, background: "#f6f8fa", padding: 8, borderRadius: 4, overflow: "auto" }}>
{rec.llm_raw}
          </pre>
        </details>
      )}
    </main>
  );
}
