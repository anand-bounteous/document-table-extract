"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listPiiRuns } from "@/lib/api";

interface PiiRunListEntry {
  pii_run_id: string;
  status: string;
  started_at?: string;
  finished_at?: string;
  ocr_producers: string[];
  detector_names: string[];
  paired_run_ids: string[];
  paired_batch_id?: string | null;
  stats: { total_docs: number; done_docs: number; error_docs: number };
  n_documents: number;
}

export default function PiiBenchmarksListPage() {
  const [runs, setRuns] = useState<PiiRunListEntry[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    listPiiRuns()
      .then((r) => setRuns(r.runs as PiiRunListEntry[]))
      .catch((e) => setErr(String(e)));
  }, []);

  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <h1 style={{ marginBottom: 4 }}>PII benchmarks</h1>
        <div className="row" style={{ gap: 8 }}>
          <Link href="/pii-benchmarks/dataset" className="btn">JSONL dataset mode ↗</Link>
          <Link href="/" className="btn">← home</Link>
        </div>
      </div>
      <p className="muted" style={{ fontSize: 13 }}>
        Independent UK-banking PII detection track. Each run compares the
        selected detectors across the selected OCR producers, on every page of
        every uploaded document.
      </p>
      {err && <p style={{ color: "#cf222e" }}>{err}</p>}
      {!runs && !err && <p className="muted">loading…</p>}
      {runs && runs.length === 0 && (
        <p className="muted">
          No runs yet. Tick <em>New PII Benchmark</em> on the home page when starting a run.
        </p>
      )}
      {runs && runs.length > 0 && (
        <table style={{ width: "100%", fontSize: 13, marginTop: 12 }}>
          <thead>
            <tr style={{ background: "#f6f8fa" }}>
              <th style={{ textAlign: "left", padding: "6px 8px" }}>id</th>
              <th>status</th>
              <th>docs</th>
              <th>detectors</th>
              <th>ocr</th>
              <th>paired</th>
              <th>started</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.pii_run_id} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: "6px 8px" }}>
                  <Link href={`/pii-benchmarks/${r.pii_run_id}`}><code>{r.pii_run_id}</code></Link>
                </td>
                <td style={{ textAlign: "center" }}>
                  <span className={`pill ${r.status === "done" ? "ok" : "running"}`}>{r.status}</span>
                </td>
                <td style={{ textAlign: "center" }}>
                  {r.stats?.done_docs ?? 0}/{r.n_documents}
                </td>
                <td style={{ fontSize: 11, color: "var(--muted)" }}>{r.detector_names.join(", ")}</td>
                <td style={{ fontSize: 11, color: "var(--muted)" }}>{r.ocr_producers.length} producers</td>
                <td style={{ fontSize: 11 }}>
                  {r.paired_batch_id ? (
                    <Link href={`/batches/${r.paired_batch_id}`}>batch</Link>
                  ) : r.paired_run_ids.length > 0 ? (
                    <Link href={`/runs/${r.paired_run_ids[0]}`}>run</Link>
                  ) : "—"}
                </td>
                <td style={{ fontSize: 11, color: "var(--muted)" }}>{r.started_at?.slice(0, 19)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
