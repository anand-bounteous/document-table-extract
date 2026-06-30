"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getPiiDatasetRun, piiDatasetCsvUrl, piiDatasetReportMdUrl } from "@/lib/api";
import type { PiiDatasetDetectorSummary, PiiDatasetRecommendation, PiiDatasetRun } from "@/lib/types";

export default function PiiDatasetRunPage() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<PiiDatasetRun | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    async function tick() {
      try {
        const r = await getPiiDatasetRun(id);
        if (!cancelled) setRun(r);
        if (r.status !== "done" && !cancelled) setTimeout(tick, 1500);
      } catch (e) {
        if (!cancelled) setErr(String(e));
      }
    }
    tick();
    return () => { cancelled = true; };
  }, [id]);

  if (err) return <main className="container"><p style={{ color: "#cf222e" }}>{err}</p></main>;
  if (!run) return <main className="container"><p className="muted">loading…</p></main>;

  const perDet = run.summary?.per_detector ?? run.per_detector ?? {};
  const recommendation = run.summary?.recommendation;

  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <h1 style={{ marginBottom: 4 }}>JSONL benchmark · {id}</h1>
        <div className="row" style={{ gap: 8 }}>
          <Link className="btn" href="/pii-benchmarks/dataset">← datasets</Link>
          <Link className="btn" href="/pii-benchmarks">all PII runs</Link>
          {run.status === "done" && (
            <a className="btn" href={piiDatasetReportMdUrl(id)} target="_blank" rel="noreferrer">
              download report.md ↗
            </a>
          )}
        </div>
      </div>
      <div className="muted" style={{ fontSize: 13, marginBottom: 12 }}>
        dataset <code>{run.dataset_id}</code> · {run.detector_names.length} detector{run.detector_names.length !== 1 ? "s" : ""} ·{" "}
        <span className={`pill ${run.status === "done" ? "ok" : "running"}`}>{run.status}</span>
      </div>

      {recommendation && (
        <RecommendationPanel rec={recommendation} />
      )}

      <h2 style={{ marginTop: 18, fontSize: 16 }}>Per-detector metrics</h2>
      <table style={{ width: "100%", fontSize: 12 }}>
        <thead>
          <tr style={{ background: "#f6f8fa" }}>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>detector</th>
            <th>status</th>
            <th>P</th>
            <th>R</th>
            <th>F1</th>
            <th>FP</th>
            <th>FN</th>
            <th>p50 ms</th>
            <th>p95 ms</th>
            <th>p99 ms</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(perDet).map(([name, data]) => (
            <DetectorRow key={name} name={name} data={data} runId={id} />
          ))}
        </tbody>
      </table>

      <h2 style={{ marginTop: 18, fontSize: 16 }}>By entity type (exact match)</h2>
      <EntityBreakdown perDet={perDet} />
    </main>
  );
}

function DetectorRow({
  name,
  data,
  runId,
}: {
  name: string;
  data: PiiDatasetDetectorSummary;
  runId: string;
}) {
  const m = data.metrics?.overall_exact;
  const status = data.status ?? "—";
  return (
    <tr style={{ borderTop: "1px solid var(--border)" }}>
      <td style={{ padding: "4px 8px" }}><code>{name}</code></td>
      <td style={{ textAlign: "center", fontSize: 11 }}>{status}</td>
      <td style={{ textAlign: "right" }}>{m?.precision?.toFixed(3) ?? "—"}</td>
      <td style={{ textAlign: "right" }}>{m?.recall?.toFixed(3) ?? "—"}</td>
      <td style={{ textAlign: "right", fontWeight: 600 }}>{m?.f1?.toFixed(3) ?? "—"}</td>
      <td style={{ textAlign: "right" }}>
        {data.false_positive_count != null ? (
          <a href={piiDatasetCsvUrl(runId, name, "false_positives")} target="_blank" rel="noreferrer">
            {data.false_positive_count} ↓
          </a>
        ) : "—"}
      </td>
      <td style={{ textAlign: "right" }}>
        {data.false_negative_count != null ? (
          <a href={piiDatasetCsvUrl(runId, name, "false_negatives")} target="_blank" rel="noreferrer">
            {data.false_negative_count} ↓
          </a>
        ) : "—"}
      </td>
      <td style={{ textAlign: "right" }}>{data.latency_ms?.p50?.toFixed(1) ?? "—"}</td>
      <td style={{ textAlign: "right" }}>{data.latency_ms?.p95?.toFixed(1) ?? "—"}</td>
      <td style={{ textAlign: "right" }}>{data.latency_ms?.p99?.toFixed(1) ?? "—"}</td>
    </tr>
  );
}

function RecommendationPanel({ rec }: { rec: PiiDatasetRecommendation }) {
  const items: { label: string; value?: string | null }[] = [
    { label: "Overall F1 winner", value: rec.winner_overall_f1 },
    { label: "Highest recall", value: rec.winner_recall },
    { label: "Highest precision", value: rec.winner_precision },
    { label: "Lowest p95 latency", value: rec.winner_latency_p95 },
  ];
  return (
    <div
      style={{
        padding: 12,
        border: "1px solid var(--border)",
        borderRadius: 8,
        background: "#f0fff4",
        marginBottom: 14,
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 6 }}>Production recommendation matrix</div>
      <div className="row" style={{ flexWrap: "wrap", gap: 12 }}>
        {items.map((it) => (
          <div key={it.label} style={{ fontSize: 12 }}>
            <div className="muted" style={{ fontSize: 11 }}>{it.label}</div>
            <div><code style={{ background: "#ddffe1", padding: "1px 6px", borderRadius: 4 }}>{it.value ?? "—"}</code></div>
          </div>
        ))}
      </div>
    </div>
  );
}

function EntityBreakdown({ perDet }: { perDet: Record<string, PiiDatasetDetectorSummary> }) {
  const types = new Set<string>();
  for (const d of Object.values(perDet)) {
    for (const t of Object.keys(d.metrics?.by_entity_exact ?? {})) types.add(t);
  }
  const detNames = Object.keys(perDet);
  const typeList = Array.from(types).sort();
  if (typeList.length === 0) return <p className="muted">no entity breakdown yet</p>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "#f6f8fa" }}>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>entity type</th>
            {detNames.map((d) => (
              <th key={d} style={{ padding: "4px 6px" }} colSpan={3}>{d}</th>
            ))}
          </tr>
          <tr style={{ background: "#f6f8fa", fontSize: 10 }}>
            <th></th>
            {detNames.map((d) => (
              <>
                <th key={d + "-p"}>P</th>
                <th key={d + "-r"}>R</th>
                <th key={d + "-f"}>F1</th>
              </>
            ))}
          </tr>
        </thead>
        <tbody>
          {typeList.map((t) => (
            <tr key={t} style={{ borderTop: "1px solid var(--border)" }}>
              <td style={{ padding: "4px 8px" }}><code>{t}</code></td>
              {detNames.map((d) => {
                const m = perDet[d].metrics?.by_entity_exact?.[t];
                return (
                  <>
                    <td key={d + t + "p"} style={{ textAlign: "right" }}>{m ? m.precision.toFixed(2) : "—"}</td>
                    <td key={d + t + "r"} style={{ textAlign: "right" }}>{m ? m.recall.toFixed(2) : "—"}</td>
                    <td key={d + t + "f"} style={{ textAlign: "right" }}>{m ? m.f1.toFixed(2) : "—"}</td>
                  </>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
