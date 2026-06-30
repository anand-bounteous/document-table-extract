"use client";

import { useEffect, useState } from "react";
import { artifactUrl, getTableCrops } from "@/lib/api";
import type { TableCropEntry, TableCropsBundle } from "@/lib/types";
import { TableWithCoordsToggle } from "./TableWithCoordsToggle";
import { ZoomableImage } from "./ZoomableImage";

export function TableCropPanel({
  runId,
  solution,
  pageIndex,
}: {
  runId: string;
  solution: string;
  pageIndex: number;
}) {
  const [bundle, setBundle] = useState<TableCropsBundle | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [zoom, setZoom] = useState<{ src: string; caption: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    getTableCrops(runId, solution)
      .then((b) => { if (!cancelled) setBundle(b); })
      .catch((e) => { if (!cancelled) setErr(String(e)); });
    return () => { cancelled = true; };
  }, [runId, solution]);

  if (err) return <p style={{ color: "#cf222e", fontSize: 12 }}>{err}</p>;
  if (!bundle) return <p className="muted" style={{ fontSize: 12 }}>loading table crops…</p>;

  const forPage = bundle.crops.filter((c) => c.page_index === pageIndex);
  const plain = forPage.filter((c) => c.kind === "plain");
  const obfuscated = forPage.filter((c) => c.kind === "obfuscated");

  if (forPage.length === 0) {
    return <p className="muted" style={{ fontSize: 12 }}>No table crops for this page (tables need a bbox to be cropped).</p>;
  }

  function CropRow({ crops, label }: { crops: TableCropEntry[]; label: string }) {
    if (crops.length === 0) return null;
    return (
      <div style={{ marginTop: 8 }}>
        <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>{label}</div>
        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          {crops.map((c, i) => {
            const src = artifactUrl(runId, c.ref);
            return (
              <div key={i} style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "center" }}>
                <img
                  src={src}
                  alt={`${label} table ${i + 1}`}
                  style={{ maxWidth: 200, maxHeight: 150, border: "1px solid #d0d7de", borderRadius: 4, cursor: "zoom-in" }}
                  onClick={() => setZoom({ src, caption: `${label} — table ${i + 1} · page ${pageIndex + 1}` })}
                />
                <div className="row" style={{ gap: 4 }}>
                  <button
                    className="btn"
                    style={{ padding: "2px 8px", fontSize: 11 }}
                    onClick={() => setZoom({ src, caption: `${label} — table ${i + 1} · page ${pageIndex + 1}` })}
                  >
                    zoom
                  </button>
                  <a
                    className="btn"
                    href={src}
                    download={`table-${i + 1}-${c.kind}.png`}
                    style={{ padding: "2px 8px", fontSize: 11 }}
                  >
                    ↓
                  </a>
                </div>
                {c.n_rows > 0 && c.cells.length > 0 && (
                  <details style={{ marginTop: 4, maxWidth: 400 }}>
                    <summary style={{ fontSize: 11, cursor: "pointer" }}>extracted text table</summary>
                    <TableWithCoordsToggle nRows={c.n_rows} nCols={c.n_cols} cells={c.cells} />
                  </details>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div>
      <CropRow crops={plain} label="Plain crops" />
      <CropRow crops={obfuscated} label="Obfuscated (char-substituted)" />
      {zoom && <ZoomableImage src={zoom.src} alt={zoom.caption} caption={zoom.caption} onClose={() => setZoom(null)} />}
    </div>
  );
}
