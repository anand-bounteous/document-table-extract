"use client";

import { useEffect, useMemo, useState } from "react";
import type { PageResult, Region } from "@/lib/types";
import { artifactUrl } from "@/lib/api";
import { ZoomableImage } from "./ZoomableImage";

const COLOR: Record<string, string> = {
  table: "#0050dc",
  table_row: "#50a0dc",
  table_header: "#00b4dc",
  table_cell: "#8cb4e6",
  logo: "#00b400",
  normal_text: "#787878",
  handwriting_signature: "#f08c00",
  seal: "#a03cc8",
  watermark: "#dcc800",
  kv_pair: "#3ca0a0",
  image: "#8c5a3c",
  unknown: "#8c8c8c",
};

export function AnnotatedImageViewer({
  runId,
  page,
  caption,
}: {
  runId: string;
  page: PageResult;
  caption?: string;
}) {
  const [hover, setHover] = useState<Region | null>(null);
  const [zoom, setZoom] = useState(false);

  // Only show feature toggles for region types this solution actually found
  // on this page (with counts). Avoids the 12-checkbox carpet that appeared
  // identically on every card regardless of what the solution emitted.
  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const r of page.regions) counts[r.type] = (counts[r.type] ?? 0) + 1;
    return counts;
  }, [page.regions]);
  const presentTypes = useMemo(
    () => Object.keys(typeCounts).sort((a, b) => typeCounts[b] - typeCounts[a]),
    [typeCounts]
  );

  // Default: every present type ON. PII overlay defaults on iff any region
  // carries a PII span.
  const piiCount = useMemo(
    () => page.regions.reduce((n, r) => n + r.pii_spans.length, 0),
    [page.regions]
  );
  const [layers, setLayers] = useState<Set<string>>(() => new Set(presentTypes));
  const [showPii, setShowPii] = useState(piiCount > 0);

  // Keep the layer set in sync if the page/regions change (e.g. solution
  // still streaming results). New types come in enabled; removed types fall
  // out of the set automatically.
  useEffect(() => {
    setLayers((prev) => {
      const next = new Set<string>();
      for (const t of presentTypes) {
        // preserve user's prior choice if they explicitly turned a type off
        if (prev.size === 0 || prev.has(t)) next.add(t);
      }
      return next;
    });
  }, [presentTypes]);

  const visible = useMemo(
    () => page.regions.filter((r) => layers.has(r.type)),
    [page.regions, layers]
  );

  function toggle(type: string) {
    const n = new Set(layers);
    if (n.has(type)) n.delete(type);
    else n.add(type);
    setLayers(n);
  }

  const ratio = page.height / page.width;
  return (
    <div>
      <div className="row" style={{ marginBottom: 6, fontSize: 11, flexWrap: "wrap", gap: 6 }}>
        {presentTypes.length === 0 ? (
          <span className="muted">no regions detected</span>
        ) : (
          presentTypes.map((t) => {
            const color = COLOR[t] ?? COLOR.unknown;
            const on = layers.has(t);
            return (
              <label
                key={t}
                title={`${typeCounts[t]} ${t} region(s) — click to toggle`}
                style={{
                  cursor: "pointer",
                  color: on ? color : color + "88",
                  border: `1px solid ${on ? color : color + "55"}`,
                  background: on ? color + "18" : "transparent",
                  padding: "1px 6px",
                  borderRadius: 999,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  fontWeight: on ? 600 : 400,
                }}
              >
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => toggle(t)}
                  style={{ margin: 0 }}
                />
                {t}
                <span style={{ opacity: 0.7 }}>· {typeCounts[t]}</span>
              </label>
            );
          })
        )}
        {piiCount > 0 && (
          <label
            title={`${piiCount} PII span(s) — toggle red highlights`}
            style={{
              cursor: "pointer",
              color: showPii ? "#cf222e" : "#cf222e88",
              border: `1px solid ${showPii ? "#cf222e" : "#cf222e55"}`,
              background: showPii ? "#cf222e18" : "transparent",
              padding: "1px 6px",
              borderRadius: 999,
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              fontWeight: showPii ? 600 : 400,
            }}
          >
            <input type="checkbox" checked={showPii} onChange={() => setShowPii(!showPii)} style={{ margin: 0 }} />
            PII <span style={{ opacity: 0.7 }}>· {piiCount}</span>
          </label>
        )}
      </div>
      <div
        style={{
          position: "relative",
          width: "100%",
          paddingBottom: `${ratio * 100}%`,
          background: "#eee",
          border: "1px solid var(--border)",
          borderRadius: 4,
          cursor: "zoom-in",
        }}
        onClick={() => setZoom(true)}
        title="click to zoom"
      >
        {(page.page_image_ref || page.annotated_image_ref) && (
          // Underlying image is the RAW rasterized page — same content per
          // solution at a given DPI (each run stores its own copy under the
          // solution's artifacts dir, but the bytes are identical). Falls
          // back to the annotated PNG only for older runs that predate
          // page_image_ref.
          <img
            src={artifactUrl(runId, (page.page_image_ref || page.annotated_image_ref) as string)}
            alt={`page ${page.page_index + 1}`}
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
          />
        )}
        <svg
          viewBox={`0 0 ${page.width} ${page.height}`}
          preserveAspectRatio="none"
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
        >
          {visible.map((r) => {
            const c = COLOR[r.type] ?? COLOR.unknown;
            const active = hover && hover.id === r.id;
            return (
              <g
                key={r.id}
                onMouseEnter={() => setHover(r)}
                onMouseLeave={() => setHover((h) => (h === r ? null : h))}
              >
                <rect
                  x={r.bbox.x}
                  y={r.bbox.y}
                  width={r.bbox.w}
                  height={r.bbox.h}
                  // Light fill so the user can clearly see what's selected;
                  // the underlying raw image stays visible underneath.
                  fill={c}
                  fillOpacity={active ? 0.22 : 0.10}
                  stroke={c}
                  strokeWidth={active ? 3 : 2}
                  opacity={active ? 1 : 0.85}
                />
              </g>
            );
          })}
          {showPii &&
            page.regions.flatMap((r) =>
              r.pii_spans
                .filter((p) => p.bbox)
                .map((p, i) => (
                  <g key={`${r.id}-pii-${i}`}>
                    <rect
                      x={p.bbox!.x}
                      y={p.bbox!.y}
                      width={p.bbox!.w}
                      height={p.bbox!.h}
                      fill="rgba(220, 30, 30, 0.32)"
                      stroke="#cf222e"
                      strokeWidth={3}
                    />
                    <text
                      x={p.bbox!.x + 2}
                      y={p.bbox!.y - 4}
                      fontSize={14}
                      fill="#cf222e"
                      fontWeight={700}
                    >
                      {p.entity_type}
                    </text>
                  </g>
                ))
            )}
        </svg>
      </div>
      {hover && (
        <div className="card" style={{ marginTop: 6, fontSize: 12 }}>
          <strong>{hover.type}</strong> · conf {hover.confidence.toFixed(2)} · tool {hover.source_tool}
          <div className="muted" style={{ marginTop: 4 }}>{hover.text}</div>
          {hover.pii_spans.length > 0 && (
            <div className="muted" style={{ marginTop: 4, color: "#cf222e" }}>
              PII: {hover.pii_spans.map((p) => `${p.entity_type}=${p.masked_value}`).join(", ")}
            </div>
          )}
        </div>
      )}
      {zoom && (page.page_image_ref || page.annotated_image_ref) && (
        <ZoomableImage
          src={artifactUrl(runId, (page.page_image_ref || page.annotated_image_ref) as string)}
          alt={caption ?? `page ${page.page_index + 1}`}
          caption={caption ?? `Page ${page.page_index + 1}`}
          onClose={() => setZoom(false)}
        />
      )}
    </div>
  );
}
