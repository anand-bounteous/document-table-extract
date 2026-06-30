"use client";

import { useState } from "react";
import type { PageResult, Region } from "@/lib/types";
import { copyBBox, formatBBox } from "@/lib/coords";

// Buckets the user wants visible per card "as applicable" — only rendered if
// the solution actually emitted any matching regions. Tables and PII have
// their own panels already; this catches everything else.
//
// `match` runs against region.attributes so a solution that subtypes
// `kv_pair` (e.g. pdfplumber → hyperlink / annotation) gets its own panel.
type Bucket = {
  key: string;
  label: string;
  color: string;
  types: string[];
  match?: (r: Region) => boolean;
  // What to render as the "primary content" column for each row.
  pickText?: (r: Region) => string;
  // Optional URL link rendered next to the text (hyperlinks).
  pickHref?: (r: Region) => string | null;
};

const BUCKETS: Bucket[] = [
  {
    key: "images",
    label: "Images",
    color: "#8c5a3c",
    types: ["image"],
    pickText: (r) => String(r.attributes?.name ?? r.text ?? ""),
  },
  {
    key: "logos",
    label: "Logos",
    color: "#00b400",
    types: ["logo"],
  },
  {
    key: "signatures",
    label: "Signatures",
    color: "#f08c00",
    types: ["handwriting_signature"],
  },
  {
    key: "seals",
    label: "Seals / Stamps",
    color: "#a03cc8",
    types: ["seal"],
  },
  {
    key: "watermarks",
    label: "Watermarks",
    color: "#dcc800",
    types: ["watermark"],
  },
  {
    key: "hyperlinks",
    label: "Hyperlinks",
    color: "#3ca0a0",
    types: ["kv_pair"],
    match: (r) => r.attributes?.object_type === "hyperlink",
    pickText: (r) => String(r.attributes?.uri ?? r.text ?? ""),
    pickHref: (r) => {
      const u = (r.attributes?.uri ?? r.text) as string | undefined;
      return u ? String(u) : null;
    },
  },
  {
    key: "annotations",
    label: "PDF Annotations",
    color: "#3ca0a0",
    types: ["kv_pair"],
    match: (r) => r.attributes?.object_type === "annotation",
    pickText: (r) => {
      const sub = r.attributes?.subtype ? `[${r.attributes.subtype}] ` : "";
      return `${sub}${r.text || ""}`;
    },
  },
  {
    key: "kv_pairs",
    label: "Key-Value pairs",
    color: "#3ca0a0",
    types: ["kv_pair"],
    match: (r) => {
      const ot = r.attributes?.object_type;
      return ot !== "hyperlink" && ot !== "annotation";
    },
  },
];

export function FeatureRegionsPanel({ page }: { page: PageResult }) {
  // Group regions by bucket once; nothing renders if a bucket is empty.
  const buckets = BUCKETS.map((b) => ({
    bucket: b,
    items: page.regions.filter(
      (r) => b.types.includes(r.type) && (b.match ? b.match(r) : true)
    ),
  })).filter((g) => g.items.length > 0);

  if (buckets.length === 0) return null;

  return (
    <>
      {buckets.map(({ bucket, items }) => (
        <FeatureBucket key={bucket.key} bucket={bucket} items={items} />
      ))}
    </>
  );
}

function FeatureBucket({ bucket, items }: { bucket: Bucket; items: Region[] }) {
  const [copied, setCopied] = useState<string | null>(null);
  async function copy(r: Region) {
    if (await copyBBox(r.bbox)) {
      setCopied(r.id);
      setTimeout(() => setCopied((c) => (c === r.id ? null : c)), 1000);
    }
  }

  return (
    <details style={{ marginTop: 6 }}>
      <summary style={{ color: bucket.color, fontWeight: 600 }}>
        {bucket.label} ({items.length})
      </summary>
      <table>
        <thead>
          <tr>
            <th style={{ width: 24 }}>#</th>
            <th>bbox</th>
            <th>conf</th>
            <th>tool</th>
            <th>{bucket.label === "Images" ? "name" : "text / uri / note"}</th>
            <th>attributes</th>
          </tr>
        </thead>
        <tbody>
          {items.slice(0, 50).map((r, i) => {
            const text = (bucket.pickText ?? ((rr: Region) => rr.text))(r);
            const href = bucket.pickHref ? bucket.pickHref(r) : null;
            const attrs = formatAttrs(r.attributes);
            return (
              <tr key={r.id}>
                <td style={{ color: "var(--muted)", fontSize: 11 }}>{i + 1}</td>
                <td
                  onClick={() => copy(r)}
                  title={copied === r.id ? "copied" : "click to copy bbox"}
                  style={{
                    cursor: "pointer",
                    fontFamily: "ui-monospace, SFMono-Regular, monospace",
                    fontSize: 11,
                    whiteSpace: "nowrap",
                    background: copied === r.id ? "#dafbe1" : undefined,
                  }}
                >
                  {formatBBox(r.bbox)}
                </td>
                <td style={{ fontSize: 11 }}>{r.confidence.toFixed(2)}</td>
                <td style={{ fontSize: 11 }}>{r.source_tool}</td>
                <td style={{ whiteSpace: "pre-wrap", fontSize: 12, maxWidth: 280 }}>
                  {href ? (
                    <a href={href} target="_blank" rel="noreferrer">{text.slice(0, 200)}</a>
                  ) : (
                    text.slice(0, 200) || <span className="muted">(no text)</span>
                  )}
                </td>
                <td style={{ fontSize: 10, color: "var(--muted)", maxWidth: 200 }}>{attrs}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {items.length > 50 && (
        <p className="muted" style={{ fontSize: 11, marginTop: 4 }}>
          showing first 50 of {items.length}
        </p>
      )}
    </details>
  );
}

function formatAttrs(attrs: Record<string, unknown> | undefined | null): string {
  if (!attrs) return "";
  const skip = new Set(["uri", "object_type"]);
  const parts: string[] = [];
  for (const [k, v] of Object.entries(attrs)) {
    if (skip.has(k)) continue;
    if (v === null || v === undefined || v === "") continue;
    const s = typeof v === "object" ? JSON.stringify(v) : String(v);
    parts.push(`${k}=${s.length > 40 ? s.slice(0, 40) + "…" : s}`);
  }
  return parts.join(" · ");
}
