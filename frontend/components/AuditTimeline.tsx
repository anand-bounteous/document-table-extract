import type { AuditStep } from "@/lib/types";

export function AuditTimeline({ audit }: { audit: AuditStep[] }) {
  const max = Math.max(1, ...audit.map((s) => s.duration_ms));
  return (
    <div style={{ fontSize: 12 }}>
      {audit.map((s) => (
        <div key={s.order} style={{ display: "grid", gridTemplateColumns: "30px 1fr 60px", gap: 6, alignItems: "center", padding: "2px 0" }}>
          <span className="muted">#{s.order}</span>
          <div>
            <div><strong>{s.stage_name}</strong> · {s.tool} <span className={`pill ${s.status}`}>{s.status}</span></div>
            <div style={{ background: "#eaeef2", height: 6, borderRadius: 3, overflow: "hidden" }}>
              <div style={{ width: `${(s.duration_ms / max) * 100}%`, height: "100%", background: "#0969da" }} />
            </div>
          </div>
          <span className="muted" style={{ textAlign: "right" }}>{s.duration_ms.toFixed(0)} ms</span>
        </div>
      ))}
    </div>
  );
}
