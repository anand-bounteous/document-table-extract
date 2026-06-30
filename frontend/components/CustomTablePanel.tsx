"use client";

import type { CustomTableStatus, PageResult } from "@/lib/types";
import { TableWithCoordsToggle } from "./TableWithCoordsToggle";

const STATUS_COLOR: Record<CustomTableStatus, string> = {
  ok: "#0a7c7c",
  na_missing_bbox: "#9a6700",
  not_found: "#57606a",
};

const STATUS_LABEL: Record<CustomTableStatus, string> = {
  ok: "OK",
  na_missing_bbox: "NA — bbox missing",
  not_found: "Not found",
};

export function CustomTablePanel({ page }: { page: PageResult }) {
  const status = page.custom_table_status ?? "not_found";
  const color = STATUS_COLOR[status];

  return (
    <div>
      <div className="row" style={{ marginBottom: 6, gap: 8 }}>
        <strong>Custom-code tables</strong>
        <span
          style={{
            background: color + "1a",
            color,
            border: `1px solid ${color}55`,
            padding: "0 8px",
            borderRadius: 999,
            fontSize: 11,
            fontWeight: 600,
          }}
        >
          {STATUS_LABEL[status]}
        </span>
        <span className="muted" style={{ fontSize: 11 }}>{page.custom_table_message}</span>
      </div>

      {page.custom_tables.length === 0 && (
        <p className="muted" style={{ fontSize: 12 }}>
          {status === "na_missing_bbox"
            ? "Upstream stage did not provide bbox data for this page."
            : status === "not_found"
            ? "Heuristic ran but found no horizontal or vertical-kv table."
            : "—"}
        </p>
      )}

      {page.custom_tables.map((ct, ti) => (
        <details key={ti} open={ti === 0} style={{ marginTop: 6 }}>
          <summary>
            <code>{ct.orientation}</code> · {ct.n_rows} × {ct.n_cols} ({ct.cells.length} cells)
          </summary>
          <TableWithCoordsToggle nRows={ct.n_rows} nCols={ct.n_cols} cells={ct.cells} />
          <details style={{ marginTop: 6 }}>
            <summary className="muted" style={{ fontSize: 11 }}>detection details</summary>
            <pre style={{ fontSize: 10, background: "#f6f8fa", padding: 6, borderRadius: 4, overflow: "auto" }}>
              {JSON.stringify(ct.detection, null, 2)}
            </pre>
          </details>
        </details>
      ))}
    </div>
  );
}
