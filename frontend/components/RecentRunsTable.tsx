"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { deleteRun, listRuns, pdfUrl } from "@/lib/api";
import type { RunListEntry, SolutionLifecycle } from "@/lib/types";

const COLOR: Record<SolutionLifecycle, string> = {
  pending: "#9a6700",
  running: "#0969da",
  done: "#1a7f37",
  error: "#cf222e",
  skipped: "#57606a",
  partial: "#bf8700",
};

interface DocGroup {
  document_id: string;
  filename: string;
  pdf_kind: string;
  runs: RunListEntry[];
}

function groupByDocument(runs: RunListEntry[]): DocGroup[] {
  const map = new Map<string, DocGroup>();
  for (const r of runs) {
    const id = r.document?.document_id ?? "unknown";
    if (!map.has(id)) {
      map.set(id, {
        document_id: id,
        filename: r.document?.filename ?? id,
        pdf_kind: r.document?.pdf_kind ?? "unknown",
        runs: [],
      });
    }
    map.get(id)!.runs.push(r);
  }
  // Groups already in most-recent-first order (runs are sorted by mtime from backend)
  return Array.from(map.values());
}

function SolutionChips({ r }: { r: RunListEntry }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
      {(r.solution_names ?? []).map((name) => {
        const state = (r.solution_status?.[name]?.state ?? "pending") as SolutionLifecycle;
        const c = COLOR[state];
        return (
          <span
            key={name}
            title={`${name}: ${state}`}
            style={{
              background: c + "22", color: c,
              border: `1px solid ${c}55`,
              padding: "0 5px", borderRadius: 999, fontSize: 10,
            }}
          >
            {name}
          </span>
        );
      })}
    </div>
  );
}

export function RecentRunsTable() {
  const [runs, setRuns] = useState<RunListEntry[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [expandedDocs, setExpandedDocs] = useState<Set<string>>(new Set());

  async function load() {
    try {
      const data = await listRuns(50);
      setRuns(data.runs);
      // Auto-expand the first (most recent) document group
      if (data.runs.length > 0) {
        const firstDocId = data.runs[0].document?.document_id;
        if (firstDocId) setExpandedDocs(new Set([firstDocId]));
      }
    } catch (e) { setErr(String(e)); }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, []);

  async function handleDelete(runId: string) {
    if (!confirm(`Delete run ${runId} and all its artifacts?`)) return;
    setDeleting(runId);
    try {
      await deleteRun(runId);
      setRuns((prev) => prev?.filter((r) => r.run_id !== runId) ?? null);
    } catch (e) { setErr(String(e)); }
    finally { setDeleting(null); }
  }

  function toggleDoc(docId: string) {
    setExpandedDocs((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) next.delete(docId); else next.add(docId);
      return next;
    });
  }

  if (err) return <p style={{ color: "#cf222e" }}>{err}</p>;
  if (!runs) return <p className="muted">loading runs…</p>;
  if (runs.length === 0) return <p className="muted">No runs yet — pick a PDF below.</p>;

  const groups = groupByDocument(runs);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {groups.map((g) => {
        const expanded = expandedDocs.has(g.document_id);
        const runningCount = g.runs.filter((r) => r.status === "running").length;
        const doneCount = g.runs.filter((r) => r.status === "done").length;
        return (
          <div key={g.document_id} style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
            {/* Document header row */}
            <div
              className="row"
              style={{
                padding: "8px 12px",
                background: "#f6f8fa",
                borderBottom: expanded ? "1px solid var(--border)" : undefined,
                gap: 8,
                cursor: "pointer",
                alignItems: "center",
              }}
              onClick={() => toggleDoc(g.document_id)}
            >
              <span style={{ fontSize: 13 }}>{expanded ? "▾" : "▸"}</span>
              <strong style={{ fontSize: 13, flex: 1 }}>{g.filename}</strong>
              <span className="muted" style={{ fontSize: 11 }}>{g.pdf_kind}</span>
              <span className="muted" style={{ fontSize: 11 }}>{g.runs.length} run{g.runs.length !== 1 ? "s" : ""}</span>
              {runningCount > 0 && <span className="pill running" style={{ fontSize: 10 }}>{runningCount} running</span>}
              {doneCount > 0 && <span className="pill ok" style={{ fontSize: 10 }}>{doneCount} done</span>}
              <Link
                className="btn"
                href={`/documents/${encodeURIComponent(g.document_id)}/history`}
                style={{ fontSize: 11, padding: "2px 8px" }}
                onClick={(e) => e.stopPropagation()}
              >
                history
              </Link>
              <a
                className="btn"
                href={pdfUrl(g.document_id)}
                target="_blank"
                rel="noreferrer"
                style={{ fontSize: 11, padding: "2px 8px" }}
                onClick={(e) => e.stopPropagation()}
              >
                PDF ↗
              </a>
            </div>

            {/* Runs list */}
            {expanded && (
              <table style={{ margin: 0 }}>
                <thead>
                  <tr>
                    <th>run id</th>
                    <th>status</th>
                    <th>solutions</th>
                    <th>started</th>
                    <th>actions</th>
                  </tr>
                </thead>
                <tbody>
                  {g.runs.map((r) => {
                    const started = r.started_at ? new Date(r.started_at).toLocaleString() : "—";
                    const isDeleting = deleting === r.run_id;
                    return (
                      <tr key={r.run_id} style={{ opacity: isDeleting ? 0.5 : 1 }}>
                        <td>
                          <code style={{ fontSize: 11 }}>{r.run_id}</code>
                        </td>
                        <td>
                          <span className={`pill ${r.status === "done" ? "ok" : "running"}`}>{r.status}</span>
                        </td>
                        <td><SolutionChips r={r} /></td>
                        <td className="muted" style={{ fontSize: 11 }}>{started}</td>
                        <td>
                          <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
                            <Link className="btn" href={`/runs/${r.run_id}`} style={{ fontSize: 11, padding: "2px 8px" }}>
                              view
                            </Link>
                            <button
                              className="btn"
                              disabled={isDeleting || r.status === "running"}
                              title={r.status === "running" ? "Cannot delete a running execution" : "Delete run and all artifacts"}
                              style={{ fontSize: 11, padding: "2px 8px", color: "#cf222e", borderColor: "#cf222e55" }}
                              onClick={() => handleDelete(r.run_id)}
                            >
                              {isDeleting ? "deleting…" : "delete"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        );
      })}
    </div>
  );
}
