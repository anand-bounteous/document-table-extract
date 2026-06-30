"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createBatch, createPiiRun, listDocuments, listSolutions, startRun } from "@/lib/api";
import type { DocumentMeta, SolutionDescriptor } from "@/lib/types";
import Link from "next/link";
import { Dashboard } from "@/components/Dashboard";
import { FlowSelector, type FlowSelection } from "@/components/FlowSelector";
import { PdfUploader } from "@/components/PdfUploader";
import { RecentRunsTable } from "@/components/RecentRunsTable";
import { SolutionPicker } from "@/components/SolutionPicker";

function runLabel(flows: FlowSelection, nDocs: number): string {
  const parts: string[] = [];
  if (flows.current) parts.push(nDocs > 1 ? `batch (${nDocs} docs)` : "run");
  if (flows.pii_v2) parts.push("pii benchmark");
  if (parts.length === 0) return "Run";
  return "Run " + parts.join(" + ");
}

export default function HomePage() {
  const router = useRouter();
  const [docs, setDocs] = useState<DocumentMeta[]>([]);
  const [solutions, setSolutions] = useState<SolutionDescriptor[]>([]);
  const [docIds, setDocIds] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [flows, setFlows] = useState<FlowSelection>({ current: true, pii_v2: false });
  const [starting, setStarting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function toggleDoc(id: string) {
    const next = new Set(docIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setDocIds(next);
  }

  const PREF_KEY = "ote_default_solutions";

  function loadSavedSelection(allNames: string[]): Set<string> {
    try {
      const raw = localStorage.getItem(PREF_KEY);
      if (!raw) return new Set(allNames);
      const saved: string[] = JSON.parse(raw);
      const valid = saved.filter((n) => allNames.includes(n));
      return valid.length > 0 ? new Set(valid) : new Set(allNames);
    } catch { return new Set(allNames); }
  }

  function updateSelected(next: Set<string>) {
    setSelected(next);
    try { localStorage.setItem(PREF_KEY, JSON.stringify(Array.from(next))); } catch {}
  }

  async function reload() {
    try {
      const [d, s] = await Promise.all([listDocuments(), listSolutions()]);
      setDocs(d.documents);
      setSolutions(s.solutions);
      if (selected.size === 0 && s.solutions.length > 0) {
        setSelected(loadSavedSelection(s.solutions.map((x) => x.name)));
      }
    } catch (e) {
      setErr(String(e));
    }
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function canRun(): boolean {
    if (docIds.size === 0) return false;
    if (!flows.current && !flows.pii_v2) return false;
    if (flows.current && selected.size === 0) return false;
    return true;
  }

  async function go() {
    if (!canRun()) return;
    setStarting(true);
    setErr(null);
    const docList = Array.from(docIds);
    try {
      let runIds: string[] = [];
      let batchId: string | null = null;
      let routeTo: string | null = null;

      if (flows.current) {
        if (docList.length === 1) {
          const { run_id } = await startRun(docList[0], Array.from(selected));
          runIds = [run_id];
          routeTo = `/runs/${run_id}`;
        } else {
          const created = await createBatch(docList, Array.from(selected));
          batchId = created.batch_id;
          runIds = created.run_ids;
          routeTo = `/batches/${batchId}`;
        }
      }
      if (flows.pii_v2) {
        const { pii_run_id } = await createPiiRun({
          document_ids: docList,
          paired_run_ids: runIds.length ? runIds : undefined,
          paired_batch_id: batchId,
        });
        // When both flows are picked, prefer the /runs (or /batches) destination
        // so the user can watch the OCR cards stream in; chips link to the
        // PII benchmark dashboard. When only the PII flow ran, land there.
        if (!flows.current) routeTo = `/pii-benchmarks/${pii_run_id}`;
      }
      if (routeTo) router.push(routeTo);
    } catch (e) {
      setErr(String(e));
      setStarting(false);
    }
  }

  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <h1 style={{ marginBottom: 4 }}>sof-table-extract</h1>
        <div className="row" style={{ gap: 8 }}>
          <Link href="/pii-benchmarks" className="btn">pii benchmarks ↗</Link>
          <Link href="/benchmarks" className="btn">benchmarks ↗</Link>
          <Link href="/guide" className="btn">user guide ↗</Link>
        </div>
      </div>
      <p className="muted">OCR / document-parsing comparison harness — pick a PDF, pick solutions, run.</p>

      <h2>Dashboard</h2>
      <Dashboard />

      <h2 style={{ marginTop: 24 }}>Recent runs</h2>
      <RecentRunsTable />

      <FlowSelector value={flows} onChange={setFlows} />

      <h2 style={{ marginTop: 24 }}>1. Pick or upload PDFs <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>· multi-select runs sequentially as a batch</span></h2>
      <PdfUploader onUploaded={(d) => { reload(); setDocIds((prev) => new Set([...prev, d.id])); }} />
      <div style={{ marginTop: 12, maxHeight: 240, overflow: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
        <table>
          <thead><tr><th></th><th>file</th><th>source</th><th>kind</th><th>pages</th></tr></thead>
          <tbody>
            {docs.map((d) => {
              const on = docIds.has(d.id);
              return (
                <tr key={d.id} style={{ background: on ? "#ddf4ff" : undefined, cursor: "pointer" }} onClick={() => toggleDoc(d.id)}>
                  <td><input type="checkbox" checked={on} onChange={() => toggleDoc(d.id)} /></td>
                  <td>{d.filename}</td>
                  <td>{d.source ?? "sample"}</td>
                  <td>{d.pdf_kind ?? "?"}</td>
                  <td>{d.n_pages ?? "?"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {docIds.size > 0 && (
        <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
          {docIds.size} document{docIds.size !== 1 ? "s" : ""} selected
          {docIds.size > 1 && " — they will be processed one at a time"}
        </div>
      )}

      <h2 style={{ marginTop: 24 }}>
        2. Pick solutions
        {!flows.current && (
          <span className="muted" style={{ fontSize: 12, fontWeight: 400 }}>
            {" "}· skipped — current flow is off
          </span>
        )}
      </h2>
      {flows.current && (
        <>
          <SolutionPicker solutions={solutions} selected={selected} onChange={updateSelected} />
          <button
            className="btn"
            style={{ marginTop: 6, fontSize: 11 }}
            onClick={() => {
              localStorage.removeItem(PREF_KEY);
              updateSelected(new Set(solutions.map((s) => s.name)));
            }}
          >
            reset to all
          </button>
        </>
      )}
      {flows.pii_v2 && (
        <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
          {flows.current ? "Also" : ""} running the new PII benchmark — text producers
          and detectors are picked automatically from defaults. Watch
          <Link href="/pii-benchmarks" style={{ marginLeft: 4 }}>/pii-benchmarks</Link>.
        </div>
      )}

      <div className="row" style={{ marginTop: 18 }}>
        <button className="btn primary" disabled={!canRun() || starting} onClick={go}>
          {starting ? "starting…" : runLabel(flows, docIds.size)}
        </button>
        {err && <span style={{ color: "#cf222e" }}>{err}</span>}
      </div>
    </main>
  );
}
