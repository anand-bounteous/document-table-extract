"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { getBatch } from "@/lib/api";
import type { BatchState, BatchDocument } from "@/lib/types";

export default function BatchPage() {
  const { batchId } = useParams<{ batchId: string }>();
  const [batch, setBatch] = useState<BatchState | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!batchId) return;
    let cancelled = false;
    async function tick() {
      try {
        const b = await getBatch(batchId);
        if (!cancelled) setBatch(b);
        if (b.status !== "done" && !cancelled) setTimeout(tick, 1500);
      } catch (e) {
        if (!cancelled) setErr(String(e));
      }
    }
    tick();
    return () => {
      cancelled = true;
    };
  }, [batchId]);

  if (err) return <main className="container"><p style={{ color: "#cf222e" }}>{err}</p></main>;
  if (!batch) return <main className="container"><p className="muted">loading batch…</p></main>;

  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <h1 style={{ marginBottom: 4 }}>Batch {batchId}</h1>
        <Link href="/" className="btn">← home</Link>
      </div>
      <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
        {batch.documents.length} document{batch.documents.length !== 1 ? "s" : ""} · {batch.solution_names.length} solution{batch.solution_names.length !== 1 ? "s" : ""} ·{" "}
        <span className={`pill ${batch.status === "done" ? "ok" : "running"}`}>{batch.status}</span>
      </div>

      <StatsBar stats={batch.stats} total={batch.documents.length} />

      <div style={{ marginTop: 16 }}>
        {batch.documents.map((doc, i) => (
          <DocCard key={doc.run_id} doc={doc} index={i + 1} />
        ))}
      </div>
    </main>
  );
}

function StatsBar({
  stats,
  total,
}: {
  stats: BatchState["stats"];
  total: number;
}) {
  const pct = total > 0 ? Math.round((stats.done / total) * 100) : 0;
  const pills: { label: string; count: number; color: string }[] = [
    { label: "queued", count: stats.queued, color: "#9a6700" },
    { label: "running", count: stats.running, color: "#0969da" },
    { label: "done", count: stats.done, color: "#1a7f37" },
    { label: "error", count: stats.error, color: "#cf222e" },
  ];
  return (
    <div
      className="row"
      style={{
        flexWrap: "wrap",
        gap: 8,
        alignItems: "center",
        padding: "10px 12px",
        border: "1px solid var(--border)",
        borderRadius: 8,
        background: "#f6f8fa",
      }}
    >
      <strong style={{ fontSize: 13 }}>Documents</strong>
      {pills.map((p) => (
        <span
          key={p.label}
          style={{
            background: p.color + "1a",
            color: p.color,
            border: `1px solid ${p.color}55`,
            padding: "2px 10px",
            borderRadius: 999,
            fontSize: 12,
            fontWeight: 600,
          }}
        >
          {p.label}: {p.count}
        </span>
      ))}
      <span style={{ flex: 1 }} />
      <span className="muted" style={{ fontSize: 12 }}>{pct}% done</span>
      <div
        style={{
          width: 180,
          height: 8,
          background: "#dde",
          borderRadius: 4,
          overflow: "hidden",
        }}
      >
        <div style={{ width: `${pct}%`, height: "100%", background: "#1a7f37", transition: "width 0.5s ease" }} />
      </div>
    </div>
  );
}

function DocCard({ doc, index }: { doc: BatchDocument; index: number }) {
  const statusColor: Record<string, string> = {
    queued: "#9a6700",
    running: "#0969da",
    done: "#1a7f37",
    error: "#cf222e",
  };
  const color = statusColor[doc.status] ?? "#57606a";

  // Per-solution roll-up from the inlined run state.
  const solStats = (() => {
    const counts = { pending: 0, running: 0, done: 0, error: 0, skipped: 0 };
    const ss = doc.run?.solution_status ?? {};
    for (const v of Object.values(ss)) {
      const s = (v as any)?.state as keyof typeof counts;
      if (s && counts[s] !== undefined) counts[s]++;
    }
    return counts;
  })();

  // Active solutions with progress.
  const activeProgress: { name: string; current: number; total: number; tool?: string }[] = [];
  const ss = doc.run?.solution_status ?? {};
  for (const [name, entry] of Object.entries(ss)) {
    const e: any = entry;
    if (e?.state === "running" && e?.progress?.total_pages) {
      activeProgress.push({
        name,
        current: e.progress.current_page,
        total: e.progress.total_pages,
        tool: e.progress.tool,
      });
    }
  }

  return (
    <div
      className="card"
      style={{
        marginBottom: 12,
        borderColor: doc.status === "running" ? color : undefined,
        borderWidth: doc.status === "running" ? 2 : 1,
      }}
    >
      <div className="row" style={{ alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <div>
          <strong style={{ fontSize: 14 }}>#{index} · {doc.filename}</strong>
          <div className="muted" style={{ fontSize: 11 }}>
            {doc.pdf_kind} · {doc.n_pages} page{doc.n_pages !== 1 ? "s" : ""}
          </div>
        </div>
        <div className="row" style={{ gap: 6 }}>
          <span
            style={{
              background: color + "1a",
              color,
              border: `1px solid ${color}55`,
              padding: "2px 10px",
              borderRadius: 999,
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            {doc.status}
          </span>
          <Link className="btn" href={`/runs/${doc.run_id}`} style={{ padding: "2px 10px", fontSize: 12 }}>
            open run ↗
          </Link>
        </div>
      </div>

      {doc.status !== "queued" && (
        <div className="row" style={{ gap: 6, flexWrap: "wrap", marginTop: 8, fontSize: 11 }}>
          {([
            ["pending", "#9a6700"],
            ["running", "#0969da"],
            ["done", "#1a7f37"],
            ["error", "#cf222e"],
            ["skipped", "#57606a"],
          ] as const).map(([k, c]) =>
            solStats[k as keyof typeof solStats] > 0 ? (
              <span
                key={k}
                style={{
                  background: c + "1a",
                  color: c,
                  border: `1px solid ${c}55`,
                  padding: "1px 8px",
                  borderRadius: 999,
                }}
              >
                {k}: {solStats[k as keyof typeof solStats]}
              </span>
            ) : null,
          )}
        </div>
      )}

      {activeProgress.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>currently running:</div>
          <table style={{ width: "100%", fontSize: 11 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left" }}>solution</th>
                <th style={{ width: 110 }}>page</th>
                <th style={{ width: 80 }}>tool</th>
                <th>progress</th>
              </tr>
            </thead>
            <tbody>
              {activeProgress.map((p) => (
                <tr key={p.name}>
                  <td><code>{p.name}</code></td>
                  <td style={{ fontFamily: "ui-monospace, SFMono-Regular, monospace" }}>
                    {p.current} / {p.total}
                  </td>
                  <td style={{ color: "var(--muted)" }}>{p.tool ?? "—"}</td>
                  <td>
                    <div style={{ width: "100%", height: 6, background: "#dde", borderRadius: 3, overflow: "hidden" }}>
                      <div
                        style={{
                          width: `${Math.round((p.current / Math.max(1, p.total)) * 100)}%`,
                          height: "100%",
                          background: "#0969da",
                          transition: "width 0.5s ease",
                        }}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
