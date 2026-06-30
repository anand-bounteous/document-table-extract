"use client";

import type { TableCell } from "@/lib/types";
import { formatBBox, formatBBoxLong } from "@/lib/coords";

/** Renders one cell as <th> when is_header is true, else <td>. The header style
 *  is bold + slightly tinted background. If is_header is missing/false, the
 *  cell renders as a normal data row, which is the correct fallback for
 *  upstream tools that don't tag headers (img2table, paddle, camelot, custom). */
export function TableCellView({ cell, showCoords = false }: { cell: TableCell | null | undefined; showCoords?: boolean }) {
  if (!cell) {
    return <td />;
  }
  if (cell.is_header) {
    return (
      <th
        scope="col"
        style={{
          background: "#eaf6ff",
          color: "#0550ae",
          fontWeight: 700,
          textAlign: "left",
        }}
        title="identified as header by upstream solution"
      >
        {cell.text}
        {showCoords && cell.bbox && (
          <div
            className="muted"
            title={formatBBoxLong(cell.bbox)}
            style={{ fontFamily: "ui-monospace, SFMono-Regular, monospace", fontSize: 10, opacity: 0.6, fontWeight: 400 }}
          >
            {formatBBox(cell.bbox)}
          </div>
        )}
      </th>
    );
  }
  return (
    <td>
      {cell.text}
      {showCoords && cell.bbox && (
        <div
          className="muted"
          title={formatBBoxLong(cell.bbox)}
          style={{ fontFamily: "ui-monospace, SFMono-Regular, monospace", fontSize: 10, opacity: 0.6 }}
        >
          {formatBBox(cell.bbox)}
        </div>
      )}
    </td>
  );
}
