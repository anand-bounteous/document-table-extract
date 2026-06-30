"use client";

import { useState } from "react";
import type { Region } from "@/lib/types";
import { copyBBox, formatBBox, formatBBoxLong } from "@/lib/coords";

type Attrs = Record<string, unknown> | undefined;

function asStr(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined;
}

function asBool(v: unknown): boolean | undefined {
  return typeof v === "boolean" ? v : undefined;
}

function asNum(v: unknown): number | undefined {
  return typeof v === "number" ? v : undefined;
}

function StyleChips({ attrs }: { attrs: Attrs }) {
  if (!attrs) return null;
  const chips: React.ReactNode[] = [];
  const font = asStr(attrs.font);
  const size = asNum(attrs.font_size);
  const color = asStr(attrs.font_color);
  const bold = asBool(attrs.bold);
  const italic = asBool(attrs.italic);
  const underline = asBool(attrs.underline);
  const bg = asStr(attrs.bg_color);

  if (font) {
    chips.push(
      <span key="f" className="chip" title={font} style={chipStyle}>
        {font.split(/[-,]/)[0].slice(0, 14)}
        {size ? ` · ${size.toFixed(0)}pt` : ""}
      </span>,
    );
  }
  if (color) {
    chips.push(
      <span key="c" title={`color ${color}`} style={{ ...chipStyle, color, borderColor: color }}>
        <span style={{ ...swatch, background: color }} /> {color}
      </span>,
    );
  }
  if (bg) {
    chips.push(
      <span key="bg" title={`bg ${bg}`} style={chipStyle}>
        <span style={{ ...swatch, background: bg }} /> bg {bg}
      </span>,
    );
  }
  if (bold) chips.push(<span key="b" style={{ ...chipStyle, fontWeight: 700 }}>B</span>);
  if (italic) chips.push(<span key="i" style={{ ...chipStyle, fontStyle: "italic" }}>I</span>);
  if (underline) chips.push(<span key="u" style={{ ...chipStyle, textDecoration: "underline" }}>U</span>);
  return chips.length ? <span style={{ display: "inline-flex", gap: 4, flexWrap: "wrap" }}>{chips}</span> : null;
}

function VisualCodeChip({ attrs }: { attrs: Attrs }) {
  if (!attrs || attrs.object_type !== "visual_code") return null;
  const type = asStr(attrs.code_type) ?? "code";
  return (
    <span style={{ ...chipStyle, background: "#fff7d6", borderColor: "#bf8700" }} title={`visual code · ${asStr(attrs.source) ?? ""}`}>
      📷 {type}
    </span>
  );
}

const chipStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 3,
  fontSize: 10,
  padding: "1px 4px",
  border: "1px solid var(--border)",
  borderRadius: 3,
  background: "#f6f8fa",
  lineHeight: 1.4,
};

const swatch: React.CSSProperties = {
  width: 8,
  height: 8,
  borderRadius: 2,
  border: "1px solid rgba(0,0,0,0.2)",
};

export function RegionTable({ regions }: { regions: Region[] }) {
  const [copied, setCopied] = useState<string | null>(null);
  async function copy(r: Region) {
    if (await copyBBox(r.bbox)) {
      setCopied(r.id);
      setTimeout(() => setCopied((c) => (c === r.id ? null : c)), 1000);
    }
  }
  // Only show the style column when at least one region in this slice carries
  // font/style attributes (keeps the layout compact for solutions that don't
  // expose any styling data).
  const sliced = regions.slice(0, 80);
  const hasStyle = sliced.some((r) => {
    const a = r.attributes as Attrs;
    if (!a) return false;
    return (
      a.font !== undefined ||
      a.bold !== undefined ||
      a.italic !== undefined ||
      a.underline !== undefined ||
      a.bg_color !== undefined ||
      a.object_type === "visual_code"
    );
  });

  return (
    <table>
      <thead>
        <tr>
          <th>type</th>
          <th>conf</th>
          <th>tool</th>
          <th>bbox</th>
          {hasStyle && <th>style</th>}
          <th>text</th>
        </tr>
      </thead>
      <tbody>
        {sliced.map((r) => {
          const attrs = r.attributes as Attrs;
          return (
            <tr key={r.id}>
              <td>{r.type}</td>
              <td>{r.confidence.toFixed(2)}</td>
              <td>{r.source_tool}</td>
              <td
                onClick={() => copy(r)}
                title={formatBBoxLong(r.bbox) + (copied === r.id ? " · copied" : " · click to copy")}
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
              {hasStyle && (
                <td style={{ whiteSpace: "nowrap" }}>
                  <StyleChips attrs={attrs} />
                  <VisualCodeChip attrs={attrs} />
                </td>
              )}
              <td style={{ whiteSpace: "pre-wrap" }}>{r.text.slice(0, 200)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
