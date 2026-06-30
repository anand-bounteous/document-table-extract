"use client";

import type { PiiOccurrenceEntry } from "@/lib/types";

const SOURCE_COLOR: Record<string, string> = {
  lib: "#1a7f37",
  both: "#0969da",
  search_only: "#bf8700",
  manual_only: "#8250df",
};

export function PiiOccurrenceList({ occurrences }: { occurrences: Record<string, PiiOccurrenceEntry> }) {
  const entries = Object.values(occurrences);
  if (!entries.length) return <div className="muted" style={{ fontSize: 11 }}>no occurrences yet</div>;
  entries.sort((a, b) => b.doc_count - a.doc_count);
  return (
    <table style={{ width: "100%", fontSize: 11 }}>
      <thead>
        <tr style={{ background: "#f6f8fa" }}>
          <th style={{ textAlign: "left" }}>value</th>
          <th>type</th>
          <th>pages</th>
          <th>doc</th>
          <th style={{ textAlign: "left" }}>discovery</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e) => (
          <tr key={`${e.text}::${e.entity_type}`} style={{ borderTop: "1px solid var(--border)" }}>
            <td><code style={{ background: "#f6f8fa", padding: "0 4px" }}>{e.text}</code></td>
            <td style={{ textAlign: "center" }}><code>{e.entity_type}</code></td>
            <td style={{ textAlign: "center" }}>{e.page_count}</td>
            <td style={{ textAlign: "center", fontWeight: 600 }}>{e.doc_count}</td>
            <td>
              <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
                {Object.entries(e.by_source)
                  .filter(([, n]) => n > 0)
                  .map(([src, n]) => (
                    <span
                      key={src}
                      style={{
                        fontSize: 10,
                        padding: "0 6px",
                        borderRadius: 999,
                        background: (SOURCE_COLOR[src] ?? "#57606a") + "1a",
                        color: SOURCE_COLOR[src] ?? "#57606a",
                        border: `1px solid ${SOURCE_COLOR[src] ?? "#57606a"}55`,
                      }}
                    >
                      {src}: {n}
                    </span>
                  ))}
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
