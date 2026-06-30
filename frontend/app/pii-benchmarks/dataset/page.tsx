"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  createPiiDatasetRun,
  listPiiDatasetRuns,
  listPiiDatasets,
  listPiiDetectors,
  uploadPiiDataset,
} from "@/lib/api";
import type { PiiDatasetMeta, PiiDetectorDescriptor } from "@/lib/types";
import { useRouter } from "next/navigation";

export default function PiiDatasetIndexPage() {
  const router = useRouter();
  const [datasets, setDatasets] = useState<PiiDatasetMeta[]>([]);
  const [runs, setRuns] = useState<any[]>([]);
  const [detectors, setDetectors] = useState<PiiDetectorDescriptor[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [chosenDataset, setChosenDataset] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  async function reload() {
    try {
      const [d, r, det] = await Promise.all([listPiiDatasets(), listPiiDatasetRuns(), listPiiDetectors()]);
      setDatasets(d.datasets);
      setRuns(r.runs);
      setDetectors(det.detectors);
      if (selected.size === 0) setSelected(new Set(det.detectors.map((x) => x.name)));
    } catch (e) {
      setErr(String(e));
    }
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggleDet(name: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  async function onUpload() {
    const file = fileInput.current?.files?.[0];
    if (!file) return;
    try {
      const meta = await uploadPiiDataset(file);
      await reload();
      setChosenDataset(meta.dataset_id);
      if (fileInput.current) fileInput.current.value = "";
    } catch (e) {
      setErr(String(e));
    }
  }

  async function onRun() {
    if (!chosenDataset || selected.size === 0) return;
    setStarting(true);
    try {
      const { dataset_run_id } = await createPiiDatasetRun({
        dataset_id: chosenDataset,
        detector_names: Array.from(selected),
      });
      router.push(`/pii-benchmarks/dataset/${dataset_run_id}`);
    } catch (e) {
      setErr(String(e));
      setStarting(false);
    }
  }

  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <h1 style={{ marginBottom: 4 }}>PII benchmark · JSONL mode</h1>
        <Link href="/pii-benchmarks" className="btn">← runs</Link>
      </div>
      <p className="muted" style={{ fontSize: 13 }}>
        Upload an annotated JSONL dataset (one record per line: <code>id</code>, <code>text</code>,{" "}
        <code>entities[]</code>) and run every selected detector to get precision/recall/F1 plus
        false-positive and false-negative reports. Generate a synthetic 500-record sample with{" "}
        <code>uv run python -m scripts.generate_pii_dataset --count 500 --out data/pii_v2/synthetic_500.jsonl</code>.
      </p>
      {err && <p style={{ color: "#cf222e" }}>{err}</p>}

      <h2 style={{ marginTop: 18, fontSize: 16 }}>1. Upload dataset</h2>
      <div className="row" style={{ gap: 8 }}>
        <input ref={fileInput} type="file" accept=".jsonl,.json" />
        <button className="btn" onClick={onUpload}>upload</button>
      </div>

      <h2 style={{ marginTop: 18, fontSize: 16 }}>2. Pick dataset</h2>
      <table style={{ width: "100%", fontSize: 12, marginTop: 6 }}>
        <thead>
          <tr style={{ background: "#f6f8fa" }}>
            <th></th>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>filename</th>
            <th>records</th>
            <th>uploaded</th>
          </tr>
        </thead>
        <tbody>
          {datasets.map((d) => (
            <tr
              key={d.dataset_id}
              onClick={() => setChosenDataset(d.dataset_id)}
              style={{ cursor: "pointer", background: chosenDataset === d.dataset_id ? "#ddf4ff" : undefined }}
            >
              <td style={{ padding: "4px 8px" }}>
                <input type="radio" checked={chosenDataset === d.dataset_id} onChange={() => setChosenDataset(d.dataset_id)} />
              </td>
              <td><code>{d.filename}</code></td>
              <td style={{ textAlign: "center" }}>{d.n_records}</td>
              <td style={{ color: "var(--muted)" }}>{d.uploaded_at.slice(0, 19)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2 style={{ marginTop: 18, fontSize: 16 }}>3. Pick detectors</h2>
      <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
        {detectors.map((d) => (
          <label key={d.name} className="row" style={{ gap: 4, alignItems: "center" }}>
            <input type="checkbox" checked={selected.has(d.name)} onChange={() => toggleDet(d.name)} />
            <code style={{ fontSize: 11 }}>{d.name}</code>
          </label>
        ))}
      </div>

      <div className="row" style={{ marginTop: 14 }}>
        <button className="btn primary" disabled={!chosenDataset || selected.size === 0 || starting} onClick={onRun}>
          {starting ? "starting…" : "Run benchmark"}
        </button>
      </div>

      <h2 style={{ marginTop: 28, fontSize: 16 }}>Recent runs</h2>
      <table style={{ width: "100%", fontSize: 12, marginTop: 6 }}>
        <thead>
          <tr style={{ background: "#f6f8fa" }}>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>id</th>
            <th>status</th>
            <th>detectors</th>
            <th>started</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.dataset_run_id} style={{ borderTop: "1px solid var(--border)" }}>
              <td style={{ padding: "4px 8px" }}>
                <Link href={`/pii-benchmarks/dataset/${r.dataset_run_id}`}><code>{r.dataset_run_id}</code></Link>
              </td>
              <td style={{ textAlign: "center" }}>
                <span className={`pill ${r.status === "done" ? "ok" : "running"}`}>{r.status}</span>
              </td>
              <td style={{ fontSize: 11, color: "var(--muted)" }}>{(r.detector_names ?? []).join(", ")}</td>
              <td style={{ color: "var(--muted)" }}>{(r.started_at ?? "").slice(0, 19)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
