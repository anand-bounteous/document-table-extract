"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { deleteBenchmark, listBenchmarks } from "@/lib/api";
import type { BenchmarkAnalysisListEntry } from "@/lib/types";

export default function BenchmarksListPage() {
  const [items, setItems] = useState<BenchmarkAnalysisListEntry[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    try { setItems((await listBenchmarks()).analyses); }
    catch (e) { setErr(String(e)); }
  }

  useEffect(() => {
    let stop = false;
    async function tick() {
      await refresh();
      if (!stop) setTimeout(tick, 4000);
    }
    tick();
    return () => { stop = true; };
  }, []);

  async function onDelete(id: string) {
    if (!confirm(`Delete analysis ${id}?`)) return;
    try {
      await deleteBenchmark(id);
      await refresh();
    } catch (e) { setErr(String(e)); }
  }

  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <div>
          <Link href="/" className="muted">← back to home</Link>
          <h1 style={{ marginBottom: 4 }}>Benchmark analyses</h1>
          <p className="muted" style={{ fontSize: 13 }}>
            LLM-summarized comparisons across multiple documents.
          </p>
        </div>
        <Link href="/benchmarks/new" className="btn primary">+ new analysis</Link>
      </div>

      {err && <p style={{ color: "#cf222e" }}>{err}</p>}
      {!items && <p className="muted">loading…</p>}
      {items && items.length === 0 && <p className="muted" style={{ marginTop: 12 }}>No analyses yet — start with “new analysis”.</p>}

      {items && items.length > 0 && (
        <table style={{ marginTop: 12 }}>
          <thead>
            <tr><th>name</th><th>status</th><th>documents</th><th>created</th><th></th></tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id}>
                <td>
                  <Link href={`/benchmarks/${a.id}`}>{a.name}</Link>
                  <div className="muted" style={{ fontSize: 11 }}><code>{a.id}</code></div>
                </td>
                <td>
                  <span className={`pill ${a.status === "done" ? "ok" : a.status === "error" ? "error" : "running"}`}>
                    {a.status}
                  </span>
                  {a.error && <div className="muted" style={{ fontSize: 10, color: "#cf222e" }}>{a.error}</div>}
                </td>
                <td>{a.n_documents}</td>
                <td className="muted" style={{ fontSize: 11 }}>
                  {a.created_at ? new Date(a.created_at).toLocaleString() : "—"}
                </td>
                <td className="row" style={{ gap: 6 }}>
                  <Link className="btn" href={`/benchmarks/${a.id}`}>view</Link>
                  <button className="btn" onClick={() => onDelete(a.id)}>delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
