"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { diffRuns, listDocumentRuns, mergeRuns, pdfUrl } from "@/lib/api";
import type { RunDiff, RunListEntry, RunState, SolutionLifecycle } from "@/lib/types";

const COLOR: Record<SolutionLifecycle, string> = {
  pending: "#9a6700",
  running: "#0969da",
  done: "#1a7f37",
  error: "#cf222e",
  skipped: "#57606a",
  partial: "#bf8700",
};

export default function HistoryPage() {
  const { id } = useParams<{ id: string }>();
  const documentId = decodeURIComponent(id);
  const [runs, setRuns] = useState<RunListEntry[] | null>(null);
  const [filename, setFilename] = useState<string>("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [diff, setDiff] = useState<RunDiff | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const data = await listDocumentRuns(documentId);
        if (!cancelled) {
          setRuns(data.runs);
          setFilename(data.runs[0]?.document.filename ?? documentId);
        }
      } catch (e) { if (!cancelled) setErr(String(e)); }
      if (!cancelled) setTimeout(tick, 5000);
    }
    tick();
    return () => { cancelled = true; };
  }, [documentId]);

  function toggle(runId: string) {
    const n = new Set(picked);
    if (n.has(runId)) n.delete(runId);
    else n.add(runId);
    setPicked(n);
  }

  async function compare() {
    if (picked.size !== 2) return;
    setBusy(true);
    try {
      const [a, b] = Array.from(picked);
      const d = await diffRuns(documentId, a, b);
      setDiff(d);
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }

  const [merged, setMerged] = useState<(RunState & {
    merged: boolean;
    merged_from_runs: string[];
    page_sources_by_solution: Record<string, Record<string, string>>;
  }) | null>(null);

  async function doMerge() {
    if (picked.size < 2) return;
    setBusy(true);
    try {
      const m = await mergeRuns(documentId, Array.from(picked));
      setMerged(m);
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }

  if (err) return <main className="container"><p style={{ color: "#cf222e" }}>{err}</p></main>;

  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <div>
          <Link href="/" className="muted">← back to home</Link>
          <h1 style={{ marginBottom: 4 }}>Run history</h1>
          <div className="muted" style={{ fontSize: 13 }}>{filename}</div>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <a className="btn" href={pdfUrl(documentId)} target="_blank" rel="noreferrer">view PDF ↗</a>
          <Link className="btn" href={`/documents/${encodeURIComponent(documentId)}/benchmark`}>benchmark</Link>
        </div>
      </div>

      {!runs && <p className="muted" style={{ marginTop: 12 }}>loading runs…</p>}
      {runs && runs.length === 0 && <p className="muted" style={{ marginTop: 12 }}>No runs for this document yet.</p>}

      {runs && runs.length > 0 && (
        <>
          <div className="row" style={{ marginTop: 12, gap: 8, flexWrap: "wrap" }}>
            <button className="btn" disabled={picked.size !== 2 || busy} onClick={compare}>
              {busy ? "…" : `compare 2`}
            </button>
            <button className="btn primary" disabled={picked.size < 2 || busy} onClick={doMerge}>
              {busy ? "merging…" : `Merge ${picked.size}`}
            </button>
            <button className="btn" disabled={picked.size === 0} onClick={() => setPicked(new Set())}>clear pick</button>
            <span className="muted" style={{ fontSize: 12, alignSelf: "center" }}>
              tick 2+ runs to merge — for each (solution × page), the best result wins
            </span>
          </div>

          <table style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th style={{ width: 28 }}></th>
                <th>run</th>
                <th>status</th>
                <th>solutions</th>
                <th>started</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id} style={picked.has(r.run_id) ? { background: "#ddf4ff" } : undefined}>
                  <td>
                    <input
                      type="checkbox"
                      checked={picked.has(r.run_id)}
                      onChange={() => toggle(r.run_id)}
                    />
                  </td>
                  <td><code style={{ fontSize: 11 }}>{r.run_id}</code></td>
                  <td><span className={`pill ${r.status === "done" ? "ok" : "running"}`}>{r.status}</span></td>
                  <td>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                      {r.solution_names.map((name) => {
                        const state = (r.solution_status?.[name]?.state ?? "pending") as SolutionLifecycle;
                        const c = COLOR[state];
                        return (
                          <span key={name} title={`${name}: ${state}`} style={{
                            background: c + "22", color: c, border: `1px solid ${c}55`,
                            padding: "0 6px", borderRadius: 999, fontSize: 10,
                          }}>{name}</span>
                        );
                      })}
                    </div>
                  </td>
                  <td className="muted" style={{ fontSize: 11 }}>
                    {r.started_at ? new Date(r.started_at).toLocaleString() : "—"}
                  </td>
                  <td><Link className="btn" href={`/runs/${r.run_id}`}>view</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {diff && <DiffModal diff={diff} onClose={() => setDiff(null)} />}
      {merged && <MergedReportPanel merged={merged} onClose={() => setMerged(null)} />}
    </main>
  );
}

function MergedReportPanel({
  merged,
  onClose,
}: {
  merged: RunState & {
    merged: boolean;
    merged_from_runs: string[];
    page_sources_by_solution: Record<string, Record<string, string>>;
  };
  onClose: () => void;
}) {
  return (
    <>
      <div onClick={onClose} style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", zIndex: 90,
      }} />
      <aside style={{
        position: "fixed", top: 0, right: 0, height: "100vh",
        width: "clamp(420px, 65vw, 1040px)", background: "white",
        boxShadow: "-8px 0 24px rgba(0,0,0,0.18)", zIndex: 100,
        display: "flex", flexDirection: "column",
      }}>
        <header style={{
          padding: "12px 16px", borderBottom: "1px solid var(--border)",
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <h2 style={{ margin: 0, fontSize: 15 }}>
            Merged report · {merged.merged_from_runs.length} runs
          </h2>
          <button onClick={onClose} className="btn">close ✕</button>
        </header>
        <div style={{ padding: 16, overflow: "auto" }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
            For each (solution × page) we kept the page with the highest
            confidence; ties broken by recency. Merged from:{" "}
            {merged.merged_from_runs.map((r, i) => (
              <span key={r}>
                {i > 0 && " · "}
                <Link href={`/runs/${r}`}><code>{r}</code></Link>
              </span>
            ))}
          </div>
          <table style={{ width: "100%", fontSize: 12 }}>
            <thead style={{ background: "#f6f8fa" }}>
              <tr>
                <th style={{ textAlign: "left", padding: "6px 8px" }}>solution</th>
                <th>status</th>
                <th>pages kept</th>
                <th style={{ textAlign: "left" }}>page → source run</th>
                <th>regions</th>
                <th>tables</th>
                <th>confidence</th>
              </tr>
            </thead>
            <tbody>
              {merged.solution_results.map((sol) => {
                const sources = merged.page_sources_by_solution[sol.solution_name] ?? {};
                const regions = (sol.pages ?? []).reduce((n, p) => n + (p.regions?.length ?? 0), 0);
                const tables = (sol.pages ?? []).reduce((n, p) => n + (p.tables?.length ?? 0), 0);
                return (
                  <tr key={sol.solution_name} style={{ borderTop: "1px solid var(--border)" }}>
                    <td style={{ padding: "6px 8px" }}><code>{sol.solution_name}</code></td>
                    <td style={{ textAlign: "center" }}>
                      <span className={`pill ${sol.status === "ok" ? "ok" : "error"}`}>{sol.status}</span>
                    </td>
                    <td style={{ textAlign: "center" }}>{(sol.pages ?? []).length}</td>
                    <td style={{ padding: "6px 8px", fontSize: 11 }}>
                      <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
                        {Object.entries(sources).map(([pidx, rid]) => (
                          <span
                            key={pidx}
                            style={{
                              padding: "0 6px",
                              background: "#0969da11",
                              border: "1px solid #0969da55",
                              borderRadius: 999,
                              fontSize: 10,
                              fontFamily: "ui-monospace, monospace",
                            }}
                            title={`page ${Number(pidx) + 1} kept from run ${rid}`}
                          >
                            p{Number(pidx) + 1}→{rid.slice(0, 8)}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td style={{ textAlign: "center" }}>{regions}</td>
                    <td style={{ textAlign: "center" }}>{tables}</td>
                    <td style={{ textAlign: "center" }}>
                      {(sol.overall_confidence ?? 0).toFixed(2)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </aside>
    </>
  );
}

function DiffModal({ diff, onClose }: { diff: RunDiff; onClose: () => void }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 1000,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      <div onClick={(e) => e.stopPropagation()} className="card" style={{ background: "white", maxWidth: 1000, width: "94%", maxHeight: "88vh", overflow: "auto" }}>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2 style={{ margin: 0 }}>Diff</h2>
          <button className="btn" onClick={onClose}>close</button>
        </div>
        <p className="muted" style={{ fontSize: 12 }}>
          <code>A</code>: <code>{diff.run_a}</code> &nbsp;|&nbsp;
          <code>B</code>: <code>{diff.run_b}</code>
        </p>
        <table style={{ marginTop: 6 }}>
          <thead>
            <tr>
              <th>solution</th>
              <th colSpan={3}>regions</th>
              <th colSpan={3}>tables</th>
              <th colSpan={3}>PII</th>
              <th colSpan={3}>conf</th>
              <th colSpan={3}>ms</th>
            </tr>
            <tr style={{ fontSize: 10, color: "var(--muted)" }}>
              <th></th>
              <th>A</th><th>B</th><th>Δ</th>
              <th>A</th><th>B</th><th>Δ</th>
              <th>A</th><th>B</th><th>Δ</th>
              <th>A</th><th>B</th><th>Δ</th>
              <th>A</th><th>B</th><th>Δ</th>
            </tr>
          </thead>
          <tbody>
            {diff.solutions.map((s) => (
              <tr key={s.name}>
                <td><code>{s.name}</code></td>
                {renderMetric(s.a?.regions, s.b?.regions, s.delta?.regions)}
                {renderMetric(s.a?.tables, s.b?.tables, s.delta?.tables)}
                {renderMetric(s.a?.pii, s.b?.pii, s.delta?.pii)}
                {renderMetric(s.a?.overall_confidence, s.b?.overall_confidence, s.delta?.overall_confidence, 2)}
                {renderMetric(s.a?.duration_ms, s.b?.duration_ms, s.delta?.duration_ms, 0)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function renderMetric(a: number | undefined, b: number | undefined, delta: number | undefined, decimals = 0) {
  const f = (v: number | undefined) => v == null ? "—" : decimals ? v.toFixed(decimals) : String(Math.round(v));
  const color = delta == null || delta === 0 ? "var(--muted)" : delta > 0 ? "#1a7f37" : "#cf222e";
  return (
    <>
      <td style={{ fontSize: 12 }}>{f(a)}</td>
      <td style={{ fontSize: 12 }}>{f(b)}</td>
      <td style={{ fontSize: 12, color, fontWeight: 600 }}>{delta == null ? "—" : (delta > 0 ? "+" : "") + (decimals ? delta.toFixed(decimals) : Math.round(delta))}</td>
    </>
  );
}
