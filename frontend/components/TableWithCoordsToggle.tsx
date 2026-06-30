"use client";

import { useState } from "react";
import type { TableCell, TableModel } from "@/lib/types";
import { TableCellView } from "./TableCellView";
import { formatBBox, formatBBoxLong, copyBBox } from "@/lib/coords";

type ViewMode = "grid" | "raw" | "json";

export function TableWithCoordsToggle({
  table,
  // Back-compat shim: legacy callers passed nRows/nCols/cells without a TableModel.
  nRows,
  nCols,
  cells,
}: {
  table?: TableModel;
  nRows?: number;
  nCols?: number;
  cells?: TableCell[];
}) {
  const model: TableModel | null = table
    ? table
    : nRows !== undefined && nCols !== undefined && cells
      ? { region_id: "", orientation: "horizontal", border_mode: "unknown", n_rows: nRows, n_cols: nCols, cells }
      : null;

  const [view, setView] = useState<ViewMode>("grid");
  const [showCoords, setShowCoords] = useState(false);

  if (!model) return null;

  const cellsWithText = model.cells.filter((c) => (c.text ?? "").trim().length > 0).length;

  return (
    <div style={{ marginBottom: 8 }}>
      {/* Summary header + view switcher */}
      <div
        className="row"
        style={{
          alignItems: "center",
          gap: 6,
          flexWrap: "wrap",
          marginBottom: 6,
          fontSize: 11,
        }}
      >
        <span className="pill" style={{ background: "#eef2f6", border: "1px solid #d0d7de", color: "#24292f" }}>
          {model.n_rows} × {model.n_cols}
        </span>
        <span className="pill" style={{ background: "#eef2f6", border: "1px solid #d0d7de", color: "#24292f" }}>
          {model.cells.length} cells · {cellsWithText} w/ text
        </span>
        <span className="pill" style={{ background: "#eef2f6", border: "1px solid #d0d7de", color: "#24292f" }}>
          {model.border_mode}
        </span>
        <span style={{ flex: 1 }} />
        <ViewButton current={view} mode="grid" setView={setView}>grid</ViewButton>
        <ViewButton current={view} mode="raw" setView={setView}>raw cells</ViewButton>
        <ViewButton current={view} mode="json" setView={setView}>json</ViewButton>
      </div>

      {view === "grid" && (
        <div>
          <button
            className="btn"
            style={{ padding: "2px 8px", fontSize: 11, marginBottom: 4 }}
            onClick={() => setShowCoords((v) => !v)}
          >
            {showCoords ? "hide coords" : "show coords"}
          </button>
          {model.n_rows === 0 || model.n_cols === 0 ? (
            <p className="muted" style={{ fontSize: 12 }}>
              No grid emitted (n_rows={model.n_rows}, n_cols={model.n_cols}). Use the
              "raw cells" view if the backend produced a flat cell list.
            </p>
          ) : (
            <table>
              <tbody>
                {Array.from({ length: model.n_rows }).map((_, r) => (
                  <tr key={r}>
                    {Array.from({ length: model.n_cols }).map((_, c) => {
                      const cell = model.cells.find((cc) => cc.row === r && cc.col === c);
                      return <TableCellView key={c} cell={cell} showCoords={showCoords} />;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {view === "raw" && <RawCellsView model={model} />}

      {view === "json" && (
        <pre
          style={{
            background: "#0d1117",
            color: "#e6edf3",
            padding: 10,
            borderRadius: 4,
            fontSize: 11,
            maxHeight: 360,
            overflow: "auto",
            margin: 0,
          }}
        >
          {JSON.stringify(model, null, 2)}
        </pre>
      )}
    </div>
  );
}

function ViewButton({
  current,
  mode,
  setView,
  children,
}: {
  current: ViewMode;
  mode: ViewMode;
  setView: (m: ViewMode) => void;
  children: React.ReactNode;
}) {
  const active = current === mode;
  return (
    <button
      onClick={() => setView(mode)}
      style={{
        padding: "2px 9px",
        borderRadius: 999,
        border: `1px solid ${active ? "#0969da" : "#0969da55"}`,
        background: active ? "#0969da18" : "white",
        color: active ? "#0969da" : "#0969da99",
        fontSize: 11,
        fontWeight: active ? 600 : 400,
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

function RawCellsView({ model }: { model: TableModel }) {
  // Sort cells by (row, col) so the user can quickly scan ordering.
  const sorted = [...model.cells].sort((a, b) => a.row - b.row || a.col - b.col);
  const [copied, setCopied] = useState<string | null>(null);
  async function copy(c: TableCell, key: string) {
    if (c.bbox && (await copyBBox(c.bbox))) {
      setCopied(key);
      setTimeout(() => setCopied((k) => (k === key ? null : k)), 1000);
    }
  }
  return (
    <div style={{ maxHeight: 420, overflow: "auto" }}>
      <table style={{ width: "100%", fontSize: 11 }}>
        <thead>
          <tr>
            <th style={{ width: 26 }}>#</th>
            <th style={{ width: 36 }}>r,c</th>
            <th style={{ width: 36 }}>span</th>
            <th style={{ width: 140 }}>bbox (x, y, w, h)</th>
            <th>text</th>
            <th style={{ width: 60 }}>conf</th>
            <th style={{ width: 50 }}>flags</th>
          </tr>
        </thead>
        <tbody>
          {sorted.slice(0, 500).map((c, i) => {
            const key = `${c.row}-${c.col}-${i}`;
            const text = (c.text ?? "").trim();
            const flags: string[] = [];
            if (c.is_header) flags.push("hdr");
            if (c.multiline) flags.push("multi");
            return (
              <tr key={key} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ color: "var(--muted)" }}>{i + 1}</td>
                <td style={{ fontFamily: "ui-monospace, SFMono-Regular, monospace" }}>
                  {c.row},{c.col}
                </td>
                <td style={{ fontFamily: "ui-monospace, SFMono-Regular, monospace" }}>
                  {c.rowspan}×{c.colspan}
                </td>
                <td
                  onClick={() => copy(c, key)}
                  title={c.bbox ? formatBBoxLong(c.bbox) + (copied === key ? " · copied" : " · click to copy") : "no bbox"}
                  style={{
                    cursor: c.bbox ? "pointer" : "default",
                    fontFamily: "ui-monospace, SFMono-Regular, monospace",
                    whiteSpace: "nowrap",
                    background: copied === key ? "#dafbe1" : undefined,
                    color: c.bbox ? undefined : "var(--muted)",
                  }}
                >
                  {c.bbox ? formatBBox(c.bbox) : "(no bbox)"}
                </td>
                <td style={{ whiteSpace: "pre-wrap" }}>
                  {text || <span className="muted">(empty)</span>}
                </td>
                <td style={{ color: "var(--muted)" }}>
                  {c.confidence != null ? c.confidence.toFixed(2) : "—"}
                </td>
                <td style={{ color: "var(--muted)", fontSize: 10 }}>
                  {flags.join(" ") || "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {sorted.length > 500 && (
        <p className="muted" style={{ fontSize: 11, marginTop: 4 }}>
          showing first 500 of {sorted.length} cells
        </p>
      )}
    </div>
  );
}
