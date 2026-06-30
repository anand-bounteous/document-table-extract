"use client";

import type { PiiAuditStep } from "@/lib/types";

const STATUS_COLOR: Record<string, string> = {
  ok: "#1a7f37",
  skipped: "#57606a",
  error: "#cf222e",
};

export function PiiAuditTimeline({ steps }: { steps: PiiAuditStep[] }) {
  if (!steps.length) return <div className="muted" style={{ fontSize: 11 }}>no audit steps recorded</div>;
  const maxMs = Math.max(...steps.map((s) => s.duration_ms || 0), 1);
  return (
    <table style={{ width: "100%", fontSize: 11 }}>
      <thead>
        <tr style={{ background: "#f6f8fa" }}>
          <th style={{ width: 24 }}>#</th>
          <th style={{ textAlign: "left" }}>stage</th>
          <th style={{ textAlign: "left" }}>tool</th>
          <th style={{ textAlign: "right", width: 70 }}>ms</th>
          <th>bar</th>
          <th>status</th>
        </tr>
      </thead>
      <tbody>
        {steps.map((s) => {
          const pct = maxMs > 0 ? (s.duration_ms / maxMs) * 100 : 0;
          const color = STATUS_COLOR[s.status] ?? "#57606a";
          const summary = [
            s.inputs.length ? `in: ${s.inputs.join(", ")}` : "",
            s.outputs.length ? `out: ${s.outputs.join(", ")}` : "",
            s.message,
          ]
            .filter(Boolean)
            .join(" · ");
          return (
            <tr key={s.order} style={{ borderTop: "1px solid var(--border)" }}>
              <td style={{ color: "var(--muted)" }}>{s.order}</td>
              <td><code>{s.stage_name}</code></td>
              <td style={{ color: "var(--muted)" }}>
                <div>{s.tool}</div>
                {summary && <div style={{ fontSize: 10 }}>{summary}</div>}
              </td>
              <td style={{ textAlign: "right", fontFamily: "ui-monospace, monospace" }}>
                {s.duration_ms.toFixed(2)}
              </td>
              <td>
                <div style={{ width: "100%", height: 6, background: "#dde", borderRadius: 3, overflow: "hidden" }}>
                  <div style={{ width: `${pct}%`, height: "100%", background: color }} />
                </div>
              </td>
              <td style={{ textAlign: "center", color }}>
                <span className={`pill ${s.status}`}>{s.status}</span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
