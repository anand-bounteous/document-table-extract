"use client";

import { useEffect, useState } from "react";
import { getDetectorCapability } from "@/lib/api";
import type { PiiCellSummary, PiiDetectorCapability } from "@/lib/types";

const CATEGORY_COLOR: Record<string, string> = {
  PII: "#8250df",
  Network: "#0969da",
  Location: "#1a7f37",
  Visual: "#9a6700",
};

export function PiiCapabilityModal({
  detectorName,
  cell,
  onClose,
}: {
  detectorName: string;
  cell?: PiiCellSummary;
  onClose: () => void;
}) {
  const [cap, setCap] = useState<PiiDetectorCapability | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getDetectorCapability(detectorName).then(setCap).catch((e) => setErr(String(e)));
  }, [detectorName]);

  const foundTypes = new Set(Object.keys(cell?.entity_types ?? {}));

  return (
    <ModalShell title={`Capabilities · ${detectorName}`} onClose={onClose}>
      {err && <p style={{ color: "#cf222e" }}>{err}</p>}
      {!err && !cap && <p className="muted">loading…</p>}
      {cap && (
        <div>
          <p style={{ fontSize: 13, marginTop: 0 }}>{cap.description}</p>

          <h3 style={{ fontSize: 12, margin: "12px 0 4px" }}>Jurisdictions enabled</h3>
          <div className="row" style={{ flexWrap: "wrap", gap: 4 }}>
            {cap.jurisdictions.map((j) => (
              <span
                key={j}
                style={{
                  padding: "1px 8px",
                  fontSize: 11,
                  borderRadius: 999,
                  background: "#0969da11",
                  border: "1px solid #0969da55",
                  color: "#0969da",
                }}
              >
                {j}
              </span>
            ))}
          </div>

          {cap.requires_models.length > 0 && (
            <>
              <h3 style={{ fontSize: 12, margin: "12px 0 4px" }}>Required models</h3>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 11 }}>
                {cap.requires_models.map((m) => (
                  <li key={m}><code>{m}</code></li>
                ))}
              </ul>
            </>
          )}

          <h3 style={{ fontSize: 12, margin: "12px 0 4px" }}>
            Entity taxonomy ({cap.entity_types.length})
            {" "}
            <span className="muted" style={{ fontWeight: 400 }}>
              · ● = found in this cell · ○ = supported, not found here
            </span>
          </h3>
          <div style={{ maxHeight: 340, overflow: "auto", border: "1px solid var(--border)", borderRadius: 6 }}>
            <table style={{ width: "100%", fontSize: 11 }}>
              <thead style={{ position: "sticky", top: 0, background: "#f6f8fa" }}>
                <tr>
                  <th></th>
                  <th style={{ textAlign: "left", padding: "4px 8px" }}>type</th>
                  <th>category</th>
                  <th style={{ textAlign: "left", padding: "4px 8px" }}>jurisdictions</th>
                  <th>validator?</th>
                </tr>
              </thead>
              <tbody>
                {cap.entity_types.map((t) => {
                  const found = foundTypes.has(t.entity_type);
                  return (
                    <tr key={t.entity_type} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ textAlign: "center", padding: "2px 8px" }}>
                        <span style={{ color: found ? "#1a7f37" : "var(--muted)" }}>
                          {found ? "●" : "○"}
                        </span>
                      </td>
                      <td style={{ padding: "2px 8px" }}><code>{t.entity_type}</code></td>
                      <td style={{ textAlign: "center" }}>
                        <span style={{
                          fontSize: 10,
                          padding: "1px 6px",
                          borderRadius: 999,
                          background: (CATEGORY_COLOR[t.category] ?? "#57606a") + "1a",
                          color: CATEGORY_COLOR[t.category] ?? "#57606a",
                        }}>{t.category}</span>
                      </td>
                      <td style={{ padding: "2px 8px", color: "var(--muted)" }}>
                        {t.jurisdictions.join(", ")}
                      </td>
                      <td style={{ textAlign: "center" }}>{t.has_validator ? "✓" : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <h3 style={{ fontSize: 12, margin: "12px 0 4px" }}>Config knobs</h3>
          <table style={{ width: "100%", fontSize: 11 }}>
            <tbody>
              {cap.config_knobs.map((k) => (
                <tr key={k.name} style={{ borderTop: "1px solid var(--border)" }}>
                  <td style={{ padding: "2px 8px", width: "40%" }}><code>{k.name}</code></td>
                  <td style={{ padding: "2px 8px", color: "var(--muted)" }}>{k.purpose}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </ModalShell>
  );
}

export function ModalShell({
  title,
  onClose,
  children,
  width = 760,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  width?: number;
}) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.45)",
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        padding: "5vh 16px",
        zIndex: 100,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "white",
          width: "100%",
          maxWidth: width,
          maxHeight: "90vh",
          overflow: "auto",
          borderRadius: 10,
          padding: 18,
          boxShadow: "0 8px 32px rgba(0,0,0,0.2)",
        }}
      >
        <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
          <h2 style={{ margin: 0, fontSize: 16 }}>{title}</h2>
          <button onClick={onClose} className="btn" style={{ padding: "2px 12px" }}>close</button>
        </div>
        {children}
      </div>
    </div>
  );
}
