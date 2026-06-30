"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createBenchmark, listDocumentRuns, listDocuments } from "@/lib/api";
import type { BenchmarkSelection, DocumentMeta, RunListEntry } from "@/lib/types";

interface DocSel {
  document_id: string;
  filename: string;
  n_pages: number;
  runs: RunListEntry[];
  selected_run_id: string | null;
  selected_pages: Set<number>;
}

export default function NewBenchmarkPage() {
  const router = useRouter();
  const [docs, setDocs] = useState<DocumentMeta[] | null>(null);
  const [docSelections, setDocSelections] = useState<Record<string, DocSel>>({});
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    listDocuments().then((d) => setDocs(d.documents)).catch((e) => setErr(String(e)));
  }, []);

  async function toggleDoc(doc: DocumentMeta) {
    if (docSelections[doc.id]) {
      const copy = { ...docSelections };
      delete copy[doc.id];
      setDocSelections(copy);
      return;
    }
    try {
      const { runs } = await listDocumentRuns(doc.id);
      const completed = runs.filter((r) => r.status === "done");
      const n_pages = doc.n_pages ?? completed[0]?.document.n_pages ?? 1;
      setDocSelections({
        ...docSelections,
        [doc.id]: {
          document_id: doc.id,
          filename: doc.filename,
          n_pages,
          runs: completed,
          selected_run_id: completed[0]?.run_id ?? null,
          selected_pages: new Set(Array.from({ length: n_pages }, (_, i) => i)),
        },
      });
    } catch (e) { setErr(String(e)); }
  }

  function pickRun(docId: string, runId: string) {
    setDocSelections((s) => ({ ...s, [docId]: { ...s[docId], selected_run_id: runId } }));
  }

  function togglePage(docId: string, page: number) {
    setDocSelections((s) => {
      const sel = s[docId];
      const n = new Set(sel.selected_pages);
      if (n.has(page)) n.delete(page); else n.add(page);
      return { ...s, [docId]: { ...sel, selected_pages: n } };
    });
  }

  async function submit() {
    setErr(null);
    setBusy(true);
    try {
      const selections: BenchmarkSelection[] = Object.values(docSelections)
        .filter((d) => d.selected_run_id && d.selected_pages.size > 0)
        .map((d) => ({
          document_id: d.document_id,
          run_id: d.selected_run_id!,
          page_indices: Array.from(d.selected_pages).sort((a, b) => a - b),
        }));
      if (selections.length === 0) throw new Error("pick at least one document + run + page");
      const { id } = await createBenchmark(name || `analysis-${new Date().toISOString().slice(0, 19)}`, selections);
      router.push(`/benchmarks/${id}`);
    } catch (e) {
      setErr(String(e));
      setBusy(false);
    }
  }

  if (err && !docs) return <main className="container"><p style={{ color: "#cf222e" }}>{err}</p></main>;

  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <div>
          <Link href="/benchmarks" className="muted">← back to analyses</Link>
          <h1 style={{ marginBottom: 4 }}>New benchmark analysis</h1>
          <p className="muted" style={{ fontSize: 13 }}>
            Pick documents, pick one run per document, pick pages within each, then submit. The selections + reviews are sent to Claude for a per-category summary.
          </p>
        </div>
      </div>

      <label style={{ display: "block", margin: "12px 0" }}>
        <span className="muted" style={{ fontSize: 12 }}>analysis name (optional)</span>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Bank statements Q3 2026"
          style={{ width: "100%", padding: 6, fontSize: 14, marginTop: 2 }}
        />
      </label>

      <h2>1. Pick documents</h2>
      <div className="grid cols-3">
        {(docs ?? []).map((d) => {
          const on = !!docSelections[d.id];
          return (
            <label key={d.id} className="card" style={{ cursor: "pointer", borderColor: on ? "#1a7f37" : undefined }}>
              <div className="row" style={{ marginBottom: 4 }}>
                <input type="checkbox" checked={on} onChange={() => toggleDoc(d)} />
                <strong style={{ fontSize: 13 }}>{d.filename}</strong>
              </div>
              <div className="muted" style={{ fontSize: 11 }}>
                {d.pdf_kind ?? "?"} · {d.n_pages ?? "?"} pages
              </div>
            </label>
          );
        })}
      </div>

      {Object.values(docSelections).length > 0 && (
        <>
          <h2 style={{ marginTop: 18 }}>2. Pick run + pages per document</h2>
          {Object.values(docSelections).map((d) => (
            <div key={d.document_id} className="card" style={{ marginTop: 10 }}>
              <strong>{d.filename}</strong>
              {d.runs.length === 0 && (
                <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  No completed runs for this document. Run it first (back on the home page).
                </p>
              )}
              {d.runs.length > 0 && (
                <>
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>which run:</div>
                  <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                    {d.runs.map((r) => (
                      <label key={r.run_id} className="row" style={{ gap: 4, fontSize: 11, cursor: "pointer" }}>
                        <input
                          type="radio"
                          name={`run-${d.document_id}`}
                          checked={d.selected_run_id === r.run_id}
                          onChange={() => pickRun(d.document_id, r.run_id)}
                        />
                        <code>{r.run_id}</code>
                        <span className="muted">{r.started_at ? new Date(r.started_at).toLocaleString() : "—"}</span>
                      </label>
                    ))}
                  </div>
                  <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>which pages:</div>
                  <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
                    {Array.from({ length: d.n_pages }).map((_, i) => {
                      const on = d.selected_pages.has(i);
                      return (
                        <button
                          key={i}
                          onClick={() => togglePage(d.document_id, i)}
                          style={{
                            padding: "2px 8px", borderRadius: 999,
                            border: `1px solid ${on ? "#1a7f37" : "var(--border)"}`,
                            background: on ? "#dafbe1" : "white",
                            color: on ? "#1a7f37" : "var(--fg)",
                            fontSize: 11, cursor: "pointer",
                          }}
                        >
                          {on ? "✓ " : ""}{i + 1}
                        </button>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          ))}
        </>
      )}

      <div className="row" style={{ marginTop: 18, gap: 8 }}>
        <button className="btn primary" disabled={busy || Object.keys(docSelections).length === 0} onClick={submit}>
          {busy ? "submitting…" : "Run analysis"}
        </button>
        {err && <span style={{ color: "#cf222e" }}>{err}</span>}
      </div>
    </main>
  );
}
