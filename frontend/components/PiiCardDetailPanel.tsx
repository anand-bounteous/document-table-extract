"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  addManualAnnotation,
  getDetectorCapability,
  getPiiCell,
  getPiiTextLayout,
  getPiiVisualCodes,
  listManualAnnotations,
  piiPageImageUrl,
  processPendingAnnotations,
  type ProcessedAnnotation,
} from "@/lib/api";
import type {
  PiiAuditStep,
  PiiCellResult,
  PiiCellSummary,
  PiiDetectorCapability,
  PiiManualAnnotation,
  PiiOccurrenceEntry,
  PiiRegionSpan,
  PiiV2Entity,
  PiiVisualCode,
} from "@/lib/types";
import { PiiAuditTimeline } from "@/components/PiiAuditTimeline";
import { PiiOccurrenceList } from "@/components/PiiOccurrenceList";
import { PiiSidePanel, type SidePanelTab } from "@/components/PiiSidePanel";

const CATEGORY_COLOR: Record<string, string> = {
  PII: "#8250df",
  Network: "#0969da",
  Location: "#1a7f37",
  Visual: "#9a6700",
  Manual: "#bf8700",
};

const MAX_OVERLAYS_DEFAULT = 50;

function categoryFor(entityType: string): string {
  if (entityType === "QR_CODE" || entityType === "BAR_CODE") return "Visual";
  if (entityType.startsWith("MAP_URL_") || entityType === "LAT_LONG_PAIR") return "Location";
  if (entityType === "EMAIL_ADDRESS" || entityType === "URL") return "Network";
  return "PII";
}

export interface CompareTarget {
  ocr: string;
  detector: string;
  cell?: PiiCellSummary;
}

/**
 * Side-panel drill-down for one (or multiple) PII cards.
 *
 * In single-card mode (``target`` set), the panel renders five tabs:
 * image / spans / occurrences / audit / capabilities. The image tab carries
 * the bbox-overlay viewer + box-draw box for manual annotations.
 *
 * In compare mode (``compareTargets`` set), the only tab is a side-by-side
 * table comparing entity counts, latency, audit, and discovery breakdowns
 * across the selected cards.
 */
export function PiiCardDetailPanel({
  open,
  onClose,
  piiRunId,
  documentId,
  pageIndex,
  totalPages,
  target,
  initialTab = "image",
  compareTargets,
  pairedRunId,
  mode = "drawer",
}: {
  open: boolean;
  onClose: () => void;
  piiRunId: string;
  documentId: string;
  pageIndex: number;
  totalPages: number;
  target?: { ocr: string; detector: string; cell?: PiiCellSummary };
  initialTab?: SidePanelTab;
  compareTargets?: CompareTarget[];
  pairedRunId?: string | null;
  mode?: "drawer" | "fullscreen";
}) {
  const inCompareMode = (compareTargets?.length ?? 0) >= 2;
  const [tab, setTab] = useState<SidePanelTab>(inCompareMode ? "compare" : initialTab);
  useEffect(() => {
    setTab(inCompareMode ? "compare" : initialTab);
  }, [inCompareMode, initialTab, target?.ocr, target?.detector]);

  if (inCompareMode) {
    return (
      <PiiSidePanel
        open={open}
        onClose={onClose}
        title={`Compare · ${compareTargets!.length} cards · page ${pageIndex + 1}`}
        tabs={[{ key: "compare", label: "Comparison" }]}
        activeTab="compare"
        onTabChange={() => undefined}
      >
        <ComparisonView
          piiRunId={piiRunId}
          documentId={documentId}
          pageIndex={pageIndex}
          targets={compareTargets!}
        />
      </PiiSidePanel>
    );
  }

  if (!target) return null;
  const { ocr, detector, cell } = target;
  const tabs = [
    { key: "image" as SidePanelTab, label: "🖼 image" },
    {
      key: "redaction" as SidePanelTab,
      label: "🛡 redaction",
      badge: cell?.redaction?.n_mocks,
    },
    { key: "spans" as SidePanelTab, label: "spans", badge: cell?.entity_count },
    {
      key: "occurrences" as SidePanelTab,
      label: "occurrences",
      badge: cell?.occurrence_count,
    },
    { key: "audit" as SidePanelTab, label: "audit", badge: cell?.audit_step_count },
    { key: "capabilities" as SidePanelTab, label: "🛈 caps" },
  ];

  return (
    <PiiSidePanel
      open={open}
      onClose={onClose}
      title={`${ocr} → ${detector} · page ${pageIndex + 1}/${totalPages}`}
      tabs={tabs}
      activeTab={tab}
      onTabChange={setTab}
      mode={mode}
      openInNewTabHref={
        `/pii-benchmarks/${encodeURIComponent(piiRunId)}/cell/${encodeURIComponent(documentId)}` +
        `/${pageIndex}/${encodeURIComponent(ocr)}/${encodeURIComponent(detector)}?tab=${tab}`
      }
    >
      {tab === "image" && (
        <ImageTab
          piiRunId={piiRunId}
          documentId={documentId}
          pageIndex={pageIndex}
          totalPages={totalPages}
          ocr={ocr}
          detector={detector}
        />
      )}
      {tab === "redaction" && (
        <RedactionTab
          piiRunId={piiRunId}
          documentId={documentId}
          pageIndex={pageIndex}
          ocr={ocr}
          detector={detector}
        />
      )}
      {tab === "spans" && (
        <SpansTab
          piiRunId={piiRunId}
          documentId={documentId}
          pageIndex={pageIndex}
          ocr={ocr}
          detector={detector}
        />
      )}
      {tab === "occurrences" && (
        <OccurrencesTab
          piiRunId={piiRunId}
          documentId={documentId}
          pageIndex={pageIndex}
          ocr={ocr}
          detector={detector}
        />
      )}
      {tab === "audit" && (
        <AuditTab
          piiRunId={piiRunId}
          documentId={documentId}
          pageIndex={pageIndex}
          ocr={ocr}
          detector={detector}
        />
      )}
      {tab === "capabilities" && (
        <CapabilitiesTab detectorName={detector} cell={cell} />
      )}
      {pairedRunId && (
        <div style={{ marginTop: 12, paddingTop: 8, borderTop: "1px solid var(--border)" }}>
          <Link href={`/runs/${pairedRunId}?focus=${encodeURIComponent(ocr)}`} className="btn" style={{ fontSize: 11 }}>
            🔗 open OCR card in paired /runs ↗
          </Link>
        </div>
      )}
    </PiiSidePanel>
  );
}

/* ---------- Individual tabs ---------- */

function useCell(
  piiRunId: string,
  documentId: string,
  pageIndex: number,
  ocr: string,
  detector: string,
) {
  const [cell, setCell] = useState<PiiCellResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setCell(null);
    setErr(null);
    getPiiCell(piiRunId, documentId, pageIndex, ocr, detector)
      .then(setCell)
      .catch((e) => setErr(String(e)));
  }, [piiRunId, documentId, pageIndex, ocr, detector]);
  return { cell, err };
}

function SpansTab(p: { piiRunId: string; documentId: string; pageIndex: number; ocr: string; detector: string }) {
  const { cell, err } = useCell(p.piiRunId, p.documentId, p.pageIndex, p.ocr, p.detector);
  if (err) return <p style={{ color: "#cf222e" }}>{err}</p>;
  if (!cell) return <p className="muted">loading…</p>;
  if (!cell.entities || cell.entities.length === 0) {
    return <p className="muted">no entities detected</p>;
  }
  return (
    <table style={{ width: "100%", fontSize: 12 }}>
      <thead>
        <tr style={{ background: "#f6f8fa", textAlign: "left" }}>
          <th style={{ padding: "6px 8px" }}>type</th>
          <th style={{ padding: "6px 8px" }}>value</th>
          <th>score</th>
          <th>risk</th>
          <th>discovery</th>
        </tr>
      </thead>
      <tbody>
        {cell.entities.map((e, i) => (
          <tr key={i} style={{ borderTop: "1px solid var(--border)" }}>
            <td style={{ padding: "6px 8px" }}><code>{e.entity_type}</code></td>
            <td style={{ padding: "6px 8px" }}>
              <code style={{ background: "#f6f8fa", padding: "0 4px" }}>{e.text}</code>
            </td>
            <td style={{ textAlign: "center" }}>{e.score.toFixed(2)}</td>
            <td style={{ textAlign: "center" }}>{e.risk_level ?? "—"}</td>
            <td style={{ textAlign: "center", fontSize: 11, color: "var(--muted)" }}>
              {(e.metadata?.discovery as string) ?? "lib"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function OccurrencesTab(p: { piiRunId: string; documentId: string; pageIndex: number; ocr: string; detector: string }) {
  const { cell, err } = useCell(p.piiRunId, p.documentId, p.pageIndex, p.ocr, p.detector);
  if (err) return <p style={{ color: "#cf222e" }}>{err}</p>;
  if (!cell) return <p className="muted">loading…</p>;
  const occ = (cell.metadata?.occurrences as Record<string, PiiOccurrenceEntry> | undefined) ?? {};
  return <PiiOccurrenceList occurrences={occ} />;
}

function AuditTab(p: { piiRunId: string; documentId: string; pageIndex: number; ocr: string; detector: string }) {
  const { cell, err } = useCell(p.piiRunId, p.documentId, p.pageIndex, p.ocr, p.detector);
  if (err) return <p style={{ color: "#cf222e" }}>{err}</p>;
  if (!cell) return <p className="muted">loading…</p>;
  const audit = (cell.metadata?.audit as PiiAuditStep[] | undefined) ?? [];
  return <PiiAuditTimeline steps={audit} />;
}

function RedactionTab(p: {
  piiRunId: string;
  documentId: string;
  pageIndex: number;
  ocr: string;
  detector: string;
}) {
  const [data, setData] = useState<import("@/lib/types").RedactionPayload | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [revealAll, setRevealAll] = useState(false);
  const [imageZoom, setImageZoom] = useState(1);   // shared zoom for both panes

  useEffect(() => {
    setData(null);
    setErr(null);
    import("@/lib/api").then(({ getPiiRedaction }) =>
      getPiiRedaction(p.piiRunId, p.documentId, p.pageIndex, p.ocr, p.detector)
        .then(setData)
        .catch((e) => setErr(String(e))),
    );
  }, [p.piiRunId, p.documentId, p.pageIndex, p.ocr, p.detector]);

  if (err) {
    return (
      <div style={{ fontSize: 12 }}>
        <p style={{ color: "#cf222e" }}>{err}</p>
        <p className="muted">
          This usually means no PII was detected in this cell, or the
          redaction step was disabled (<code>PII_V2_REDACTION_ENABLED=false</code>).
        </p>
      </div>
    );
  }
  if (!data) return <p className="muted">loading…</p>;

  const orig = reconstructOriginal(data);
  return (
    <div>
      <div className="row" style={{ gap: 12, alignItems: "baseline", marginBottom: 8, fontSize: 12 }}>
        <strong>{data.diff_spans.length} spans redacted</strong>
        <span className="muted">
          · {Object.entries(data.mapping_index?.entity_types ?? {}).map(([k, v]) => `${k}×${v}`).join(", ")}
        </span>
        <span style={{ flex: 1 }} />
        <a
          className="btn"
          href={`/api/pii-benchmarks/${encodeURIComponent(p.piiRunId)}/redaction/${encodeURIComponent(p.documentId)}/${p.pageIndex}/${encodeURIComponent(p.ocr)}/${encodeURIComponent(p.detector)}/mapping?reveal=true`}
          download="mapping.fernet"
          style={{ fontSize: 11 }}
          title="Download the Fernet-encrypted mock→original mapping for later restore"
        >
          ⬇ mapping.fernet
        </a>
      </div>

      <h3 style={{ fontSize: 12, margin: "8px 0 4px" }}>Side-by-side text</h3>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <DiffTextColumn title="Original" text={orig} spans={data.diff_spans} side="original" />
        <DiffTextColumn title="Redacted" text={data.redacted_text} spans={data.diff_spans} side="mock" />
      </div>

      <FileDiffSection
        original={orig}
        redacted={data.redacted_text}
        spans={data.diff_spans}
      />

      {data.has_image && (
        <>
          <div className="row" style={{ gap: 8, alignItems: "baseline", margin: "12px 0 4px" }}>
            <h3 style={{ fontSize: 12, margin: 0 }}>Side-by-side image</h3>
            <span className="muted" style={{ fontSize: 10 }}>
              left = original w/ PII bboxes · right = redacted PNG (annotated)
            </span>
            <span style={{ flex: 1 }} />
            <ZoomToolbar zoom={imageZoom} onChange={setImageZoom} />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <SideBySideImage
              title="Original (with PII bboxes)"
              src={`/api/pii-benchmarks/${encodeURIComponent(p.piiRunId)}/page-image/${encodeURIComponent(p.documentId)}/${p.pageIndex}`}
              spans={data.diff_spans}
              stroke="#cf222e"
              zoom={imageZoom}
            />
            <SideBySideImage
              title="Redacted (annotated)"
              src={`/api/pii-benchmarks/${encodeURIComponent(p.piiRunId)}/redaction/${encodeURIComponent(p.documentId)}/${p.pageIndex}/${encodeURIComponent(p.ocr)}/${encodeURIComponent(p.detector)}/image?annotated=true`}
              spans={[]}
              stroke="#1a7f37"
              zoom={imageZoom}
            />
          </div>
          <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>
            Clean (no annotations) variant for the LLM is served at{" "}
            <a
              href={`/api/pii-benchmarks/${encodeURIComponent(p.piiRunId)}/redaction/${encodeURIComponent(p.documentId)}/${p.pageIndex}/${encodeURIComponent(p.ocr)}/${encodeURIComponent(p.detector)}/image`}
              target="_blank"
              rel="noreferrer"
            >
              redacted_page.png ↗
            </a>
          </div>
        </>
      )}

      <h3 style={{ fontSize: 12, margin: "12px 0 4px" }}>
        Mapping table
        <button
          className="btn"
          onClick={() => setRevealAll((v) => !v)}
          style={{ marginLeft: 8, padding: "1px 8px", fontSize: 10 }}
        >
          {revealAll ? "👁 hide originals" : "👁 reveal originals"}
        </button>
      </h3>
      <MappingTable spans={data.diff_spans} revealAll={revealAll} />
    </div>
  );
}

function reconstructOriginal(data: import("@/lib/types").RedactionPayload): string {
  // The /redaction endpoint returns the redacted text; reconstruct the
  // original by splicing the diff spans back in (mocks have identical
  // length to originals so offsets line up exactly).
  const spans = [...data.diff_spans].sort((a, b) => a.start - b.start);
  let out = "";
  let cursor = 0;
  for (const s of spans) {
    out += data.redacted_text.slice(cursor, s.start);
    out += s.original;
    cursor = s.end;
  }
  out += data.redacted_text.slice(cursor);
  return out;
}

function DiffTextColumn({
  title,
  text,
  spans,
  side,
}: {
  title: string;
  text: string;
  spans: import("@/lib/types").RedactionDiffSpan[];
  side: "original" | "mock";
}) {
  // Render the text with each span wrapped in a colored <mark>.
  const sorted = [...spans].sort((a, b) => a.start - b.start);
  const chunks: React.ReactNode[] = [];
  let cursor = 0;
  sorted.forEach((s, i) => {
    if (cursor < s.start) {
      chunks.push(<span key={`p${i}`}>{text.slice(cursor, s.start)}</span>);
    }
    const value = side === "original" ? s.original : s.mock;
    const col = CATEGORY_COLOR[categoryFor(s.entity_type)] ?? "#cf222e";
    chunks.push(
      <mark
        key={`s${i}`}
        title={`${s.entity_type}: "${s.original}" → "${s.mock}"`}
        style={{
          background: col + "33",
          color: col,
          padding: "0 2px",
          borderRadius: 2,
          fontWeight: 600,
        }}
      >
        {value}
      </mark>,
    );
    cursor = s.end;
  });
  if (cursor < text.length) chunks.push(<span key="tail">{text.slice(cursor)}</span>);

  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: 6,
        background: "#fbfbfd",
      }}
    >
      <div
        className="muted"
        style={{ fontSize: 11, padding: "4px 8px", borderBottom: "1px solid var(--border)" }}
      >
        {title}
      </div>
      <pre
        style={{
          margin: 0,
          padding: 8,
          fontSize: 11,
          whiteSpace: "pre-wrap",
          maxHeight: 220,
          overflow: "auto",
          fontFamily: "ui-monospace, SFMono-Regular, monospace",
        }}
      >
        {chunks}
      </pre>
    </div>
  );
}

type FileDiffSpan = import("@/lib/types").RedactionDiffSpan;

type FileDiffLine = {
  index: number;
  original: string;
  redacted: string;
  originalSpans: Array<{ start: number; end: number; span: FileDiffSpan }>;
  redactedSpans: Array<{ start: number; end: number; span: FileDiffSpan }>;
  changed: boolean;
};

function buildLineDiff(
  original: string,
  redacted: string,
  spans: FileDiffSpan[],
): FileDiffLine[] {
  // Mocks are length-preserving, so a char index maps to the same line in both
  // texts. Build per-line bounds from the original and translate every span
  // onto that grid; redacted bounds stay byte-aligned because the substitution
  // is in-place. If the two texts ever diverge in length (e.g. a future
  // non-length-preserving generator), fall back to two independent splits.
  const sameLength = original.length === redacted.length;
  const origLines = original.split("\n");
  const redLines = sameLength ? splitSameAsOriginal(redacted, origLines) : redacted.split("\n");
  const maxLen = Math.max(origLines.length, redLines.length);

  const lineStarts: number[] = [];
  let cur = 0;
  for (const ln of origLines) {
    lineStarts.push(cur);
    cur += ln.length + 1; // +1 for the consumed "\n"
  }

  const sorted = [...spans].sort((a, b) => a.start - b.start);
  const out: FileDiffLine[] = [];
  for (let i = 0; i < maxLen; i++) {
    const orig = origLines[i] ?? "";
    const red = redLines[i] ?? "";
    const lineStart = lineStarts[i] ?? 0;
    const lineEnd = lineStart + orig.length;
    const lineSpans = sorted.filter((s) => s.start < lineEnd && s.end > lineStart);
    const originalSpans = lineSpans.map((s) => ({
      start: Math.max(0, s.start - lineStart),
      end: Math.min(orig.length, s.end - lineStart),
      span: s,
    }));
    const redactedSpans = lineSpans.map((s) => ({
      start: Math.max(0, s.start - lineStart),
      end: Math.min(red.length, s.end - lineStart),
      span: s,
    }));
    out.push({
      index: i,
      original: orig,
      redacted: red,
      originalSpans,
      redactedSpans,
      changed: orig !== red,
    });
  }
  return out;
}

function splitSameAsOriginal(redacted: string, origLines: string[]): string[] {
  // Same-length redaction means the newline positions in `redacted` match the
  // positions implied by `origLines`. Re-slice on those offsets so a mock that
  // contains a "\n" inside a span (shouldn't happen but defensive) doesn't
  // re-split lines.
  const out: string[] = [];
  let cur = 0;
  for (const ln of origLines) {
    out.push(redacted.slice(cur, cur + ln.length));
    cur += ln.length + 1;
  }
  return out;
}

function renderSpansForLine(
  text: string,
  marks: Array<{ start: number; end: number; span: FileDiffSpan }>,
  side: "original" | "mock",
): React.ReactNode[] {
  if (marks.length === 0) return [text];
  const chunks: React.ReactNode[] = [];
  let cursor = 0;
  marks
    .slice()
    .sort((a, b) => a.start - b.start)
    .forEach((m, i) => {
      if (cursor < m.start) chunks.push(<span key={`p${i}`}>{text.slice(cursor, m.start)}</span>);
      const value = side === "original" ? text.slice(m.start, m.end) : text.slice(m.start, m.end);
      const col = CATEGORY_COLOR[categoryFor(m.span.entity_type)] ?? "#cf222e";
      chunks.push(
        <mark
          key={`m${i}`}
          title={`${m.span.entity_type}: "${m.span.original}" → "${m.span.mock}"`}
          style={{
            background: col + "33",
            color: col,
            padding: "0 1px",
            borderRadius: 2,
            fontWeight: 600,
          }}
        >
          {value}
        </mark>,
      );
      cursor = m.end;
    });
  if (cursor < text.length) chunks.push(<span key="tail">{text.slice(cursor)}</span>);
  return chunks;
}

function FileDiffSection({
  original,
  redacted,
  spans,
}: {
  original: string;
  redacted: string;
  spans: FileDiffSpan[];
}) {
  const [view, setView] = useState<"split" | "unified">("split");
  const [hideUnchanged, setHideUnchanged] = useState(false);
  const lines = useMemo(
    () => buildLineDiff(original, redacted, spans),
    [original, redacted, spans],
  );
  const changedCount = lines.filter((l) => l.changed).length;
  const visibleLines = hideUnchanged ? lines.filter((l) => l.changed) : lines;

  const gutterStyle: React.CSSProperties = {
    width: 36,
    padding: "0 6px",
    textAlign: "right",
    color: "var(--muted)",
    background: "#f6f8fa",
    borderRight: "1px solid var(--border)",
    userSelect: "none",
    fontVariantNumeric: "tabular-nums",
  };
  const cellStyle: React.CSSProperties = {
    padding: "0 6px",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  };

  return (
    <div style={{ marginTop: 12 }}>
      <div
        className="row"
        style={{ gap: 8, alignItems: "baseline", margin: "8px 0 4px", flexWrap: "wrap" }}
      >
        <h3 style={{ fontSize: 12, margin: 0 }}>File diff</h3>
        <span className="muted" style={{ fontSize: 11 }}>
          {changedCount} of {lines.length} lines changed
        </span>
        <div style={{ flex: 1 }} />
        <div
          role="tablist"
          style={{
            display: "inline-flex",
            border: "1px solid var(--border)",
            borderRadius: 6,
            overflow: "hidden",
            fontSize: 11,
          }}
        >
          <button
            type="button"
            onClick={() => setView("split")}
            style={{
              padding: "2px 8px",
              border: 0,
              background: view === "split" ? "#dbeafe" : "transparent",
              color: view === "split" ? "#0969da" : "var(--fg)",
              cursor: "pointer",
              fontWeight: view === "split" ? 600 : 400,
            }}
          >
            Side-by-side
          </button>
          <button
            type="button"
            onClick={() => setView("unified")}
            style={{
              padding: "2px 8px",
              border: 0,
              borderLeft: "1px solid var(--border)",
              background: view === "unified" ? "#dbeafe" : "transparent",
              color: view === "unified" ? "#0969da" : "var(--fg)",
              cursor: "pointer",
              fontWeight: view === "unified" ? 600 : 400,
            }}
          >
            Unified
          </button>
        </div>
        <label
          className="muted"
          style={{ fontSize: 11, display: "inline-flex", gap: 4, alignItems: "center" }}
        >
          <input
            type="checkbox"
            checked={hideUnchanged}
            onChange={(e) => setHideUnchanged(e.target.checked)}
          />
          Hide unchanged
        </label>
      </div>

      <div
        style={{
          border: "1px solid var(--border)",
          borderRadius: 6,
          background: "#fbfbfd",
          maxHeight: 320,
          overflow: "auto",
          fontFamily: "ui-monospace, SFMono-Regular, monospace",
          fontSize: 11,
          lineHeight: 1.55,
        }}
      >
        {view === "split" ? (
          <table style={{ borderCollapse: "collapse", width: "100%", tableLayout: "fixed" }}>
            <colgroup>
              <col style={{ width: 36 }} />
              <col style={{ width: "calc(50% - 36px)" }} />
              <col style={{ width: 36 }} />
              <col style={{ width: "calc(50% - 36px)" }} />
            </colgroup>
            <tbody>
              {visibleLines.map((l) => {
                const rowBg = l.changed ? "#fff8e1" : "transparent";
                const leftBg = l.changed ? "#ffeef0" : rowBg;
                const rightBg = l.changed ? "#e6ffec" : rowBg;
                return (
                  <tr key={l.index}>
                    <td style={{ ...gutterStyle, background: leftBg }}>{l.index + 1}</td>
                    <td style={{ ...cellStyle, background: leftBg }}>
                      {renderSpansForLine(l.original, l.originalSpans, "original")}
                    </td>
                    <td style={{ ...gutterStyle, background: rightBg }}>{l.index + 1}</td>
                    <td style={{ ...cellStyle, background: rightBg }}>
                      {renderSpansForLine(l.redacted, l.redactedSpans, "mock")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <table style={{ borderCollapse: "collapse", width: "100%", tableLayout: "fixed" }}>
            <colgroup>
              <col style={{ width: 24 }} />
              <col style={{ width: 36 }} />
              <col />
            </colgroup>
            <tbody>
              {visibleLines.flatMap((l) => {
                if (!l.changed) {
                  return [
                    <tr key={`u${l.index}`}>
                      <td style={{ ...gutterStyle, width: 24, color: "#8c959f" }}> </td>
                      <td style={gutterStyle}>{l.index + 1}</td>
                      <td style={cellStyle}>{l.original}</td>
                    </tr>,
                  ];
                }
                return [
                  <tr key={`m${l.index}`}>
                    <td
                      style={{
                        ...gutterStyle,
                        width: 24,
                        background: "#ffeef0",
                        color: "#cf222e",
                      }}
                    >
                      −
                    </td>
                    <td style={{ ...gutterStyle, background: "#ffeef0" }}>{l.index + 1}</td>
                    <td style={{ ...cellStyle, background: "#ffeef0" }}>
                      {renderSpansForLine(l.original, l.originalSpans, "original")}
                    </td>
                  </tr>,
                  <tr key={`p${l.index}`}>
                    <td
                      style={{
                        ...gutterStyle,
                        width: 24,
                        background: "#e6ffec",
                        color: "#1a7f37",
                      }}
                    >
                      +
                    </td>
                    <td style={{ ...gutterStyle, background: "#e6ffec" }}>{l.index + 1}</td>
                    <td style={{ ...cellStyle, background: "#e6ffec" }}>
                      {renderSpansForLine(l.redacted, l.redactedSpans, "mock")}
                    </td>
                  </tr>,
                ];
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function SideBySideImage({
  title,
  src,
  spans,
  stroke,
  zoom = 1,
}: {
  title: string;
  src: string;
  spans: import("@/lib/types").RedactionDiffSpan[];
  stroke: string;
  zoom?: number;
}) {
  const [dims, setDims] = useState<{ w: number; h: number } | null>(null);
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 6, background: "#f6f8fa" }}>
      <div className="muted" style={{ fontSize: 11, padding: "4px 8px", borderBottom: "1px solid var(--border)" }}>
        {title}
      </div>
      <div
        style={{
          width: "100%",
          maxHeight: zoom > 1 ? "60vh" : undefined,
          overflow: zoom > 1 ? "auto" : "visible",
        }}
      >
        <div
          style={{
            position: "relative",
            width: `${zoom * 100}%`,
            minWidth: zoom <= 1 ? "100%" : undefined,
          }}
        >
          <img
            src={src}
            alt={title}
            onLoad={(e) => {
              const img = e.currentTarget;
              setDims({ w: img.naturalWidth, h: img.naturalHeight });
            }}
            style={{ width: "100%", display: "block" }}
          />
          {dims && spans.length > 0 && (
            <svg
              viewBox={`0 0 ${dims.w} ${dims.h}`}
              preserveAspectRatio="none"
              style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
            >
              {spans.filter((s) => s.bbox_px).map((s, i) => {
                const b = s.bbox_px!;
                return (
                  <rect
                    key={i}
                    x={b.x}
                    y={b.y}
                    width={b.w}
                    height={b.h}
                    fill="none"
                    stroke={stroke}
                    strokeWidth={2}
                  />
                );
              })}
            </svg>
          )}
        </div>
      </div>
    </div>
  );
}

function ZoomToolbar({ zoom, onChange }: { zoom: number; onChange: (z: number) => void }) {
  return (
    <div className="row" style={{ gap: 4, alignItems: "center", fontSize: 10 }}>
      <span className="muted">zoom:</span>
      <button
        className="btn"
        onClick={() => onChange(Math.max(0.5, +(zoom - 0.25).toFixed(2)))}
        disabled={zoom <= 0.5}
        style={{ padding: "0 6px" }}
        title="zoom out"
      >−</button>
      <span style={{ minWidth: 40, textAlign: "center", fontFamily: "ui-monospace, monospace" }}>
        {Math.round(zoom * 100)}%
      </span>
      <button
        className="btn"
        onClick={() => onChange(Math.min(4, +(zoom + 0.25).toFixed(2)))}
        disabled={zoom >= 4}
        style={{ padding: "0 6px" }}
        title="zoom in"
      >+</button>
      {[1, 1.5, 2, 3].map((p) => (
        <button
          key={p}
          onClick={() => onChange(p)}
          className={`btn ${zoom === p ? "primary" : ""}`}
          style={{ padding: "0 6px", fontSize: 10 }}
        >
          {p === 1 ? "fit" : `${p}×`}
        </button>
      ))}
    </div>
  );
}

function MappingTable({
  spans,
  revealAll,
}: {
  spans: import("@/lib/types").RedactionDiffSpan[];
  revealAll: boolean;
}) {
  // Dedup by (entity_type, mock) — same value across multiple pages of the
  // run gets the same mock, so we only show the mapping once.
  type Row = { entity_type: string; original: string; mock: string; occurrences: number };
  const byKey: Record<string, Row> = {};
  for (const s of spans) {
    const k = `${s.entity_type}::${s.mock}`;
    if (byKey[k]) byKey[k].occurrences += 1;
    else byKey[k] = { entity_type: s.entity_type, original: s.original, mock: s.mock, occurrences: 1 };
  }
  const rows = Object.values(byKey).sort((a, b) => b.occurrences - a.occurrences);
  return (
    <table style={{ width: "100%", fontSize: 11 }}>
      <thead style={{ background: "#f6f8fa" }}>
        <tr>
          <th style={{ textAlign: "left", padding: "4px 8px" }}>Entity type</th>
          <th style={{ textAlign: "left", padding: "4px 8px" }}>Original</th>
          <th style={{ textAlign: "left", padding: "4px 8px" }}>Mock</th>
          <th style={{ textAlign: "right", padding: "4px 8px" }}>Occurrences</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} style={{ borderTop: "1px solid var(--border)" }}>
            <td style={{ padding: "4px 8px" }}>
              <code style={{ fontSize: 10 }}>{r.entity_type}</code>
            </td>
            <td style={{ padding: "4px 8px" }}>
              {revealAll ? (
                <code>{r.original}</code>
              ) : (
                <span className="muted">••• click reveal •••</span>
              )}
            </td>
            <td style={{ padding: "4px 8px" }}>
              <code>{r.mock}</code>
            </td>
            <td style={{ textAlign: "right", padding: "4px 8px" }}>{r.occurrences}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CapabilitiesTab({ detectorName, cell }: { detectorName: string; cell?: PiiCellSummary }) {
  const [cap, setCap] = useState<PiiDetectorCapability | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    getDetectorCapability(detectorName).then(setCap).catch((e) => setErr(String(e)));
  }, [detectorName]);
  if (err) return <p style={{ color: "#cf222e" }}>{err}</p>;
  if (!cap) return <p className="muted">loading…</p>;
  const found = new Set(Object.keys(cell?.entity_types ?? {}));
  return (
    <div>
      <p style={{ marginTop: 0, fontSize: 13 }}>{cap.description}</p>
      <h3 style={{ fontSize: 12, margin: "12px 0 4px" }}>Jurisdictions</h3>
      <div className="row" style={{ flexWrap: "wrap", gap: 4 }}>
        {cap.jurisdictions.map((j) => (
          <span key={j} style={{
            fontSize: 11,
            padding: "1px 8px",
            borderRadius: 999,
            background: "#0969da11",
            border: "1px solid #0969da55",
            color: "#0969da",
          }}>{j}</span>
        ))}
      </div>
      {cap.requires_models.length > 0 && (
        <>
          <h3 style={{ fontSize: 12, margin: "12px 0 4px" }}>Models</h3>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 11 }}>
            {cap.requires_models.map((m) => <li key={m}><code>{m}</code></li>)}
          </ul>
        </>
      )}
      <h3 style={{ fontSize: 12, margin: "12px 0 4px" }}>
        Entity taxonomy ({cap.entity_types.length})
        <span className="muted" style={{ fontWeight: 400 }}>
          {" "}· ● found in this cell · ○ supported only
        </span>
      </h3>
      <table style={{ width: "100%", fontSize: 11 }}>
        <thead style={{ background: "#f6f8fa" }}>
          <tr>
            <th></th>
            <th style={{ textAlign: "left" }}>type</th>
            <th>category</th>
            <th style={{ textAlign: "left" }}>jurisdictions</th>
            <th>validator?</th>
          </tr>
        </thead>
        <tbody>
          {cap.entity_types.map((t) => (
            <tr key={t.entity_type} style={{ borderTop: "1px solid var(--border)" }}>
              <td style={{ textAlign: "center", color: found.has(t.entity_type) ? "#1a7f37" : "var(--muted)" }}>
                {found.has(t.entity_type) ? "●" : "○"}
              </td>
              <td style={{ padding: "2px 6px" }}><code>{t.entity_type}</code></td>
              <td style={{ textAlign: "center" }}>
                <span style={{
                  fontSize: 10,
                  padding: "1px 6px",
                  borderRadius: 999,
                  background: (CATEGORY_COLOR[t.category] ?? "#57606a") + "1a",
                  color: CATEGORY_COLOR[t.category] ?? "#57606a",
                }}>{t.category}</span>
              </td>
              <td style={{ padding: "2px 6px", color: "var(--muted)" }}>{t.jurisdictions.join(", ")}</td>
              <td style={{ textAlign: "center" }}>{t.has_validator ? "✓" : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {cap.architecture && cap.architecture.length > 0 && (
        <details open style={{ marginTop: 14 }}>
          <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 12 }}>
            🏛 How it works (HLD) <span className="muted" style={{ fontWeight: 400 }}>· pipeline stages, top → bottom</span>
          </summary>
          <ol style={{ margin: "6px 0 0", paddingLeft: 22, fontSize: 11, lineHeight: 1.5 }}>
            {cap.architecture.map((s, i) => (
              <li key={i} style={{ marginBottom: 6 }}>
                <strong>{s.stage}</strong>
                <span className="muted"> · <code style={{ fontSize: 10 }}>{s.tool}</code></span>
                {s.blurb && <div style={{ marginTop: 2 }}>{s.blurb}</div>}
              </li>
            ))}
          </ol>
        </details>
      )}

      {cap.customisation && cap.customisation.length > 0 && (
        <details open style={{ marginTop: 12 }}>
          <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 12 }}>
            ⚙ Customisation
            <span className="muted" style={{ fontWeight: 400 }}>
              {" "}· current values for env knobs that affect this detector
            </span>
          </summary>
          <table style={{ width: "100%", fontSize: 11, marginTop: 4 }}>
            <thead style={{ background: "#f6f8fa" }}>
              <tr>
                <th style={{ textAlign: "left", padding: "4px 8px" }}>knob</th>
                <th style={{ textAlign: "left", padding: "4px 8px" }}>current value</th>
                <th style={{ textAlign: "left", padding: "4px 8px" }}>purpose</th>
              </tr>
            </thead>
            <tbody>
              {cap.customisation.map((k) => (
                <tr key={k.name} style={{ borderTop: "1px solid var(--border)" }}>
                  <td style={{ padding: "4px 8px", width: "30%" }}><code>{k.name}</code></td>
                  <td style={{ padding: "4px 8px", fontFamily: "ui-monospace, monospace" }}>
                    <code style={{ background: "#fff8c5", padding: "0 4px", borderRadius: 3 }}>
                      {k.value || "(empty)"}
                    </code>
                  </td>
                  <td style={{ padding: "4px 8px", color: "var(--muted)" }}>{k.purpose}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {cap.user_custom_dictionary && cap.user_custom_dictionary.total_entries > 0 && (
            <div style={{ marginTop: 8, padding: 8, border: "1px solid #8250df44", background: "#8250df0a", borderRadius: 4 }}>
              <strong style={{ fontSize: 11 }}>
                USER_CUSTOM dictionary ({cap.user_custom_dictionary.total_entries} entries)
              </strong>
              <div className="muted" style={{ fontSize: 10, marginTop: 2 }}>
                Promoted from manual annotations. presidio_regex picks these up automatically on every run.
              </div>
              {Object.entries(cap.user_custom_dictionary.jurisdictions).map(([j, entries]) => (
                <div key={j} style={{ marginTop: 6 }}>
                  <code style={{ fontSize: 10 }}>{j}</code>
                  <ul style={{ margin: "2px 0 0", paddingLeft: 16, fontSize: 11 }}>
                    {entries.slice(0, 10).map((e, i) => (
                      <li key={i}>
                        <code>{e.entity_type}</code>: <code style={{ background: "#f6f8fa", padding: "0 3px" }}>{e.text}</code>
                      </li>
                    ))}
                    {entries.length > 10 && <li className="muted">+{entries.length - 10} more</li>}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </details>
      )}

      <h3 style={{ fontSize: 12, margin: "12px 0 4px" }}>Config knobs (reference)</h3>
      <table style={{ width: "100%", fontSize: 11 }}>
        <tbody>
          {cap.config_knobs.map((k) => (
            <tr key={k.name} style={{ borderTop: "1px solid var(--border)" }}>
              <td style={{ padding: "4px 8px", width: "40%" }}><code>{k.name}</code></td>
              <td style={{ padding: "4px 8px", color: "var(--muted)" }}>{k.purpose}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- Image tab with bbox overlay + manual annotation ---------- */

interface OverlayBox {
  id: string;
  category: string;
  entityType: string;
  label: string;
  bbox: { x: number; y: number; w: number; h: number };
  isManual?: boolean;
}

function ImageTab({
  piiRunId,
  documentId,
  pageIndex: initialPage,
  totalPages,
  ocr,
  detector,
}: {
  piiRunId: string;
  documentId: string;
  pageIndex: number;
  totalPages: number;
  ocr: string;
  detector: string;
}) {
  const [pageIndex, setPageIndex] = useState(initialPage);
  const [cell, setCell] = useState<PiiCellResult | null>(null);
  const [layout, setLayout] = useState<PiiRegionSpan[]>([]);
  const [visual, setVisual] = useState<PiiVisualCode[]>([]);
  const [manuals, setManuals] = useState<PiiManualAnnotation[]>([]);
  const [imageReady, setImageReady] = useState(false);
  const [imageDims, setImageDims] = useState<{ w: number; h: number } | null>(null);
  const [drawMode, setDrawMode] = useState(false);
  const [drawState, setDrawState] = useState<null | { x0: number; y0: number; x1: number; y1: number }>(null);

  // Pending annotation workflow:
  //   pendingBoxes  – user-drawn boxes (not yet processed or saved)
  //   processed     – per-box OCR/visual/matched-by output ready for review
  //   review form   – editable {entity_type, text, scope} per processed box
  type PendingBox = { id: string; bbox: { x: number; y: number; w: number; h: number } };
  type ReviewRow = ProcessedAnnotation & {
    id: string;
    entity_type: string;
    text: string;
    scope: "doc" | "run";
  };
  const [pendingBoxes, setPendingBoxes] = useState<PendingBox[]>([]);
  const [reviewRows, setReviewRows] = useState<ReviewRow[] | null>(null);
  const [processing, setProcessing] = useState(false);

  const [enabledCategories, setEnabledCategories] = useState<Set<string>>(
    new Set(["PII", "Network", "Location", "Visual", "Manual"]),
  );
  const [maxOverlaysOverride, setMaxOverlaysOverride] = useState(false);
  const [zoom, setZoom] = useState(1);   // 1 = fit-width; >1 zooms in
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    setCell(null);
    setLayout([]);
    setVisual([]);
    setImageReady(false);
    Promise.all([
      getPiiCell(piiRunId, documentId, pageIndex, ocr, detector).catch(() => null),
      getPiiTextLayout(piiRunId, documentId, pageIndex, ocr).catch(() => ({ region_index: [] })),
      getPiiVisualCodes(piiRunId, documentId, pageIndex).catch(() => ({ codes: [], skipped: [] })),
      listManualAnnotations(piiRunId, documentId),
    ]).then(([cellData, layoutData, visualData, manualData]) => {
      if (cancelled) return;
      setCell(cellData);
      setLayout(layoutData.region_index);
      setVisual(visualData.codes);
      setManuals([...manualData.doc_scope, ...manualData.run_scope]);
    });
    return () => { cancelled = true; };
  }, [piiRunId, documentId, pageIndex, ocr, detector]);

  const overlays: OverlayBox[] = useMemo(() => {
    const out: OverlayBox[] = [];
    cell?.entities?.forEach((e: PiiV2Entity, i: number) => {
      const bbox = bboxForCharSpan(e.start, e.end, layout);
      if (!bbox) return;
      out.push({
        id: `e${i}`,
        category: categoryFor(e.entity_type),
        entityType: e.entity_type,
        label: `${e.entity_type}: ${e.text}`,
        bbox,
      });
    });
    visual.forEach((v, i) => {
      out.push({
        id: `v${i}`,
        category: "Visual",
        entityType: v.type,
        label: `${v.type}: ${v.payload.slice(0, 32)}`,
        bbox: v.bbox_px,
      });
    });
    manuals
      .filter((m) => m.page_index === pageIndex && m.bbox_px)
      .forEach((m, i) => {
        out.push({
          id: `m${i}`,
          category: "Manual",
          entityType: m.entity_type,
          label: `${m.entity_type}: ${m.text}`,
          bbox: m.bbox_px!,
          isManual: true,
        });
      });
    return out;
  }, [cell, layout, visual, manuals, pageIndex]);

  const visibleOverlays = useMemo(() => {
    const filtered = overlays.filter((o) => enabledCategories.has(o.category));
    const cap = maxOverlaysOverride ? filtered.length : MAX_OVERLAYS_DEFAULT;
    return filtered.slice(0, cap);
  }, [overlays, enabledCategories, maxOverlaysOverride]);

  function toggleCategory(c: string) {
    setEnabledCategories((prev) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return next;
    });
  }

  function pointerOnImage(ev: React.PointerEvent<HTMLDivElement>) {
    if (!imageDims || !wrapperRef.current) return null;
    const rect = wrapperRef.current.getBoundingClientRect();
    const xRel = (ev.clientX - rect.left) / rect.width;
    const yRel = (ev.clientY - rect.top) / rect.height;
    return { x: xRel * imageDims.w, y: yRel * imageDims.h };
  }

  function addPendingBox(bbox: { x: number; y: number; w: number; h: number }) {
    setPendingBoxes((prev) => [
      ...prev,
      { id: `p${Date.now()}-${prev.length}`, bbox },
    ]);
  }

  function removePendingBox(id: string) {
    setPendingBoxes((prev) => prev.filter((b) => b.id !== id));
  }

  async function processAll() {
    if (pendingBoxes.length === 0) return;
    setProcessing(true);
    try {
      const resp = await processPendingAnnotations(
        piiRunId,
        documentId,
        pageIndex,
        pendingBoxes.map((b) => ({ bbox_px: b.bbox })),
      );
      const rows: ReviewRow[] = resp.processed_annotations.map((p, i) => ({
        ...p,
        id: pendingBoxes[i]?.id ?? `r${i}`,
        entity_type: p.suggested_entity_type || "OTHER",
        text: p.extracted_text || "",
        scope: "doc",
      }));
      setReviewRows(rows);
    } catch (e) {
      alert(`process failed: ${e}`);
    } finally {
      setProcessing(false);
    }
  }

  function updateReviewRow(id: string, patch: Partial<ReviewRow>) {
    setReviewRows((prev) => (prev ? prev.map((r) => (r.id === id ? { ...r, ...patch } : r)) : prev));
  }

  function removeReviewRow(id: string) {
    setReviewRows((prev) => (prev ? prev.filter((r) => r.id !== id) : prev));
    setPendingBoxes((prev) => prev.filter((b) => b.id !== id));
  }

  async function saveAllReviewed() {
    if (!reviewRows) return;
    const usable = reviewRows.filter((r) => r.text.trim().length > 0);
    if (usable.length === 0) return;
    try {
      const created: PiiManualAnnotation[] = [];
      for (const row of usable) {
        const ann = await addManualAnnotation(piiRunId, documentId, {
          page_index: pageIndex,
          entity_type: row.entity_type,
          text: row.text.trim(),
          bbox_px: row.bbox_px,
          scope: row.scope,
        });
        created.push(ann);
      }
      setManuals((prev) => [...prev, ...created]);
      setPendingBoxes([]);
      setReviewRows(null);
      setDrawMode(false);
    } catch (e) {
      alert(`save failed: ${e}`);
    }
  }

  function cancelReview() {
    setReviewRows(null);
  }

  return (
    <div>
      <div className="row" style={{ gap: 8, alignItems: "center", marginBottom: 8, fontSize: 12 }}>
        <button className="btn" disabled={pageIndex <= 0} onClick={() => setPageIndex(Math.max(0, pageIndex - 1))}>← prev</button>
        <span>page {pageIndex + 1} / {totalPages}</span>
        <button className="btn" disabled={pageIndex >= totalPages - 1} onClick={() => setPageIndex(Math.min(totalPages - 1, pageIndex + 1))}>next →</button>
        <span style={{ flex: 1 }} />
        <button
          className={`btn ${drawMode ? "primary" : ""}`}
          onClick={() => setDrawMode(!drawMode)}
          title={drawMode ? "click again to stop drawing" : "draw boxes to mark missed PII"}
        >
          {drawMode ? "✓ drawing" : "✎ annotate"}
        </button>
      </div>

      <div className="row" style={{ flexWrap: "wrap", gap: 6, marginBottom: 8, fontSize: 11 }}>
        <span className="muted">overlays:</span>
        {["PII", "Network", "Location", "Visual", "Manual"].map((c) => {
          const active = enabledCategories.has(c);
          const col = CATEGORY_COLOR[c];
          return (
            <button
              key={c}
              onClick={() => toggleCategory(c)}
              style={{
                padding: "1px 10px",
                borderRadius: 999,
                border: `1px solid ${active ? col : col + "55"}`,
                background: active ? col + "22" : "white",
                color: active ? col : col + "99",
                fontWeight: active ? 700 : 400,
                cursor: "pointer",
              }}
            >
              {c}
            </button>
          );
        })}
        <span style={{ flex: 1 }} />
        {overlays.length > MAX_OVERLAYS_DEFAULT && (
          <button onClick={() => setMaxOverlaysOverride((v) => !v)} className="btn" style={{ padding: "1px 10px", fontSize: 11 }}>
            {maxOverlaysOverride ? `cap to ${MAX_OVERLAYS_DEFAULT}` : `show all ${overlays.length}`}
          </button>
        )}
        <span className="muted">{visibleOverlays.length} / {overlays.length}</span>
      </div>

      <div className="row" style={{ gap: 4, marginBottom: 8, fontSize: 11, alignItems: "center" }}>
        <span className="muted">zoom:</span>
        <button
          className="btn"
          onClick={() => setZoom((z) => Math.max(0.5, +(z - 0.25).toFixed(2)))}
          disabled={zoom <= 0.5}
          style={{ padding: "1px 8px" }}
          title="zoom out"
        >−</button>
        <span style={{ minWidth: 48, textAlign: "center", fontFamily: "ui-monospace, monospace" }}>
          {Math.round(zoom * 100)}%
        </span>
        <button
          className="btn"
          onClick={() => setZoom((z) => Math.min(4, +(z + 0.25).toFixed(2)))}
          disabled={zoom >= 4}
          style={{ padding: "1px 8px" }}
          title="zoom in"
        >+</button>
        {[0.5, 1, 1.5, 2, 3].map((p) => (
          <button
            key={p}
            onClick={() => setZoom(p)}
            className={`btn ${zoom === p ? "primary" : ""}`}
            style={{ padding: "1px 8px", fontSize: 10 }}
          >
            {p === 1 ? "fit" : `${p}×`}
          </button>
        ))}
      </div>

      <div
        style={{
          width: "100%",
          maxHeight: zoom > 1 ? "65vh" : undefined,
          overflow: zoom > 1 ? "auto" : "visible",
          border: "1px solid var(--border)",
          borderRadius: 6,
          background: "#f6f8fa",
        }}
      >
      <div
        ref={wrapperRef}
        onPointerDown={(ev) => {
          if (!drawMode) return;
          const pt = pointerOnImage(ev);
          if (!pt) return;
          setDrawState({ x0: pt.x, y0: pt.y, x1: pt.x, y1: pt.y });
        }}
        onPointerMove={(ev) => {
          if (!drawMode || !drawState) return;
          const pt = pointerOnImage(ev);
          if (!pt) return;
          setDrawState({ ...drawState, x1: pt.x, y1: pt.y });
        }}
        onPointerUp={() => {
          if (!drawMode || !drawState) return;
          const x = Math.min(drawState.x0, drawState.x1);
          const y = Math.min(drawState.y0, drawState.y1);
          const w = Math.abs(drawState.x1 - drawState.x0);
          const h = Math.abs(drawState.y1 - drawState.y0);
          setDrawState(null);
          if (w < 6 || h < 6) return;
          addPendingBox({ x, y, w, h });
        }}
        style={{
          position: "relative",
          width: `${zoom * 100}%`,
          minWidth: zoom <= 1 ? "100%" : undefined,
          background: "#f6f8fa",
          border: "1px solid var(--border)",
          borderRadius: 6,
          overflow: "hidden",
          cursor: drawMode ? "crosshair" : "default",
        }}
      >
        <img
          src={piiPageImageUrl(piiRunId, documentId, pageIndex)}
          alt={`page ${pageIndex + 1}`}
          onLoad={(e) => {
            const img = e.currentTarget;
            setImageDims({ w: img.naturalWidth, h: img.naturalHeight });
            setImageReady(true);
          }}
          onError={() => setImageReady(false)}
          style={{ width: "100%", display: "block" }}
        />
        {imageDims && (
          <svg
            viewBox={`0 0 ${imageDims.w} ${imageDims.h}`}
            preserveAspectRatio="none"
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
          >
            {visibleOverlays.map((o) => (
              <g key={o.id}>
                <rect
                  x={o.bbox.x} y={o.bbox.y}
                  width={o.bbox.w} height={o.bbox.h}
                  fill={(CATEGORY_COLOR[o.category] ?? "#cf222e") + "22"}
                  stroke={CATEGORY_COLOR[o.category] ?? "#cf222e"}
                  strokeWidth={2}
                />
                <text
                  x={o.bbox.x + 2}
                  y={Math.max(12, o.bbox.y - 4)}
                  fill={CATEGORY_COLOR[o.category] ?? "#cf222e"}
                  fontSize={Math.max(10, Math.min(14, o.bbox.h * 0.6))}
                  fontWeight={600}
                >
                  {o.label}
                </text>
              </g>
            ))}
            {pendingBoxes.map((pb) => (
              <g key={pb.id}>
                <rect
                  x={pb.bbox.x}
                  y={pb.bbox.y}
                  width={pb.bbox.w}
                  height={pb.bbox.h}
                  fill="#bf870033"
                  stroke="#bf8700"
                  strokeWidth={3}
                  strokeDasharray="8,4"
                />
                <text
                  x={pb.bbox.x + 4}
                  y={Math.max(14, pb.bbox.y - 6)}
                  fill="#bf8700"
                  fontSize={Math.max(11, Math.min(16, pb.bbox.h * 0.5))}
                  fontWeight={700}
                >
                  pending
                </text>
              </g>
            ))}
            {drawState && (
              <rect
                x={Math.min(drawState.x0, drawState.x1)}
                y={Math.min(drawState.y0, drawState.y1)}
                width={Math.abs(drawState.x1 - drawState.x0)}
                height={Math.abs(drawState.y1 - drawState.y0)}
                fill="#bf870033"
                stroke="#bf8700"
                strokeWidth={2}
                strokeDasharray="6,3"
              />
            )}
          </svg>
        )}
        {!imageReady && (
          <div style={{ padding: 20, textAlign: "center" }}>
            <p className="muted">loading page image…</p>
          </div>
        )}
      </div>
      </div>

      {pendingBoxes.length > 0 && reviewRows === null && (
        <div
          style={{
            marginTop: 10,
            padding: 10,
            border: "1px solid var(--border)",
            borderRadius: 6,
            background: "#fff8c5",
          }}
        >
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
            <strong style={{ fontSize: 12 }}>
              Pending annotations ({pendingBoxes.length})
            </strong>
            <div className="row" style={{ gap: 6 }}>
              <button
                className="btn primary"
                onClick={processAll}
                disabled={processing}
              >
                {processing ? "processing…" : `Process ${pendingBoxes.length}`}
              </button>
              <button className="btn" onClick={() => setPendingBoxes([])}>
                clear all
              </button>
            </div>
          </div>
          <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>
            Draw more boxes on the image, then click <em>Process</em> to run OCR
            + QR/barcode detection on each crop and check which existing
            detectors already cover the region.
          </div>
          <table style={{ width: "100%", fontSize: 11 }}>
            <thead>
              <tr style={{ background: "#fff4a3" }}>
                <th style={{ textAlign: "left", padding: "4px 8px" }}>#</th>
                <th style={{ textAlign: "left", padding: "4px 8px" }}>bbox (px)</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {pendingBoxes.map((b, i) => (
                <tr key={b.id} style={{ borderTop: "1px solid #ffe27a" }}>
                  <td style={{ padding: "3px 8px" }}>{i + 1}</td>
                  <td style={{ padding: "3px 8px", fontFamily: "ui-monospace, monospace" }}>
                    {Math.round(b.bbox.x)},{Math.round(b.bbox.y)} ·{" "}
                    {Math.round(b.bbox.w)}×{Math.round(b.bbox.h)}
                  </td>
                  <td style={{ textAlign: "right", padding: "3px 8px" }}>
                    <button
                      onClick={() => removePendingBox(b.id)}
                      className="btn"
                      style={{ padding: "0 6px", fontSize: 11 }}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {reviewRows && (
        <ReviewPanel
          rows={reviewRows}
          onChangeRow={updateReviewRow}
          onRemoveRow={removeReviewRow}
          onCancel={cancelReview}
          onSaveAll={saveAllReviewed}
        />
      )}
    </div>
  );
}

function ReviewPanel({
  rows,
  onChangeRow,
  onRemoveRow,
  onCancel,
  onSaveAll,
}: {
  rows: (ProcessedAnnotation & {
    id: string;
    entity_type: string;
    text: string;
    scope: "doc" | "run";
  })[];
  onChangeRow: (id: string, patch: any) => void;
  onRemoveRow: (id: string) => void;
  onCancel: () => void;
  onSaveAll: () => void;
}) {
  const usable = rows.filter((r) => r.text.trim().length > 0).length;
  return (
    <div
      style={{
        marginTop: 10,
        padding: 12,
        border: "1px solid var(--border)",
        borderRadius: 6,
        background: "#dafbe1",
      }}
    >
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <strong style={{ fontSize: 12 }}>
          Review processed annotations ({usable} ready / {rows.length})
        </strong>
        <div className="row" style={{ gap: 6 }}>
          <button className="btn primary" onClick={onSaveAll} disabled={usable === 0}>
            Save all
          </button>
          <button className="btn" onClick={onCancel}>cancel</button>
        </div>
      </div>
      {rows.map((row, i) => (
        <div
          key={row.id}
          style={{
            padding: 10,
            border: "1px solid #b4e3c0",
            borderRadius: 6,
            background: "white",
            marginBottom: 8,
          }}
        >
          <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
            <strong style={{ fontSize: 12 }}>
              #{i + 1} ·{" "}
              <span style={{ fontFamily: "ui-monospace, monospace", fontWeight: 400 }}>
                {Math.round(row.bbox_px.x)},{Math.round(row.bbox_px.y)} · {Math.round(row.bbox_px.w)}×{Math.round(row.bbox_px.h)}
              </span>
            </strong>
            <button
              className="btn"
              onClick={() => onRemoveRow(row.id)}
              style={{ padding: "0 8px", fontSize: 11 }}
            >
              discard
            </button>
          </div>
          {row.error && (
            <div style={{ color: "#cf222e", fontSize: 11, marginBottom: 4 }}>{row.error}</div>
          )}
          {row.visual_codes.length > 0 && (
            <div className="row" style={{ gap: 4, marginBottom: 6 }}>
              {row.visual_codes.map((v, j) => (
                <span
                  key={j}
                  style={{
                    fontSize: 10,
                    padding: "1px 6px",
                    background: "#9a670022",
                    border: "1px solid #9a670077",
                    color: "#9a6700",
                    borderRadius: 999,
                  }}
                >
                  {v.type}: {v.payload.slice(0, 40)}
                </span>
              ))}
            </div>
          )}
          {row.matched_by.length > 0 && (
            <div style={{ marginBottom: 6 }}>
              <div className="muted" style={{ fontSize: 10, marginBottom: 2 }}>
                already detected by:
              </div>
              <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
                {row.matched_by.map((m, j) => (
                  <span
                    key={j}
                    style={{
                      fontSize: 10,
                      padding: "1px 6px",
                      background: "#1a7f3722",
                      border: "1px solid #1a7f3777",
                      color: "#1a7f37",
                      borderRadius: 999,
                    }}
                    title={`IoU ${m.iou.toFixed(2)}`}
                  >
                    {m.ocr} → {m.detector}: {m.entity_type}
                  </span>
                ))}
              </div>
            </div>
          )}
          <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <select
              value={row.entity_type}
              onChange={(e) => onChangeRow(row.id, { entity_type: e.target.value })}
            >
              {[
                "PERSON",
                "ORGANISATION",
                "UK_ADDRESS",
                "UK_POSTCODE",
                "UK_PHONE_NUMBER",
                "EMAIL_ADDRESS",
                "URL",
                "UK_NATIONAL_INSURANCE_NUMBER",
                "UK_SORT_CODE",
                "UK_BANK_ACCOUNT_NUMBER",
                "CREDIT_CARD_NUMBER",
                "QR_CODE",
                "BAR_CODE",
                "OTHER",
              ].map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <input
              type="text"
              value={row.text}
              onChange={(e) => onChangeRow(row.id, { text: e.target.value })}
              placeholder="extracted text — edit if wrong"
              style={{ flex: 1, minWidth: 220 }}
            />
            <label className="row" style={{ gap: 4, fontSize: 11 }}>
              <input
                type="checkbox"
                checked={row.scope === "run"}
                onChange={(e) =>
                  onChangeRow(row.id, { scope: e.target.checked ? "run" : "doc" })
                }
              />
              just this run
            </label>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ---------- Compare tab ---------- */

interface CompareRow {
  label: string;
  values: (string | number)[];
}

function ComparisonView({
  piiRunId,
  documentId,
  pageIndex,
  targets,
}: {
  piiRunId: string;
  documentId: string;
  pageIndex: number;
  targets: CompareTarget[];
}) {
  const [cells, setCells] = useState<(PiiCellResult | null)[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setCells(targets.map(() => null));
    Promise.all(
      targets.map((t) =>
        getPiiCell(piiRunId, documentId, pageIndex, t.ocr, t.detector).catch(() => null),
      ),
    ).then(setCells).catch((e) => setErr(String(e)));
  }, [piiRunId, documentId, pageIndex, targets]);

  if (err) return <p style={{ color: "#cf222e" }}>{err}</p>;
  if (cells.length === 0) return <p className="muted">loading…</p>;

  const allTypes = new Set<string>();
  for (const c of cells) {
    for (const e of c?.entities ?? []) allTypes.add(e.entity_type);
  }
  const typeList = Array.from(allTypes).sort();
  const allDiscoveries = ["lib", "search_only", "manual_only", "both"];

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "#f6f8fa" }}>
            <th style={{ textAlign: "left", padding: "6px 8px" }}>metric</th>
            {targets.map((t, i) => (
              <th key={i} style={{ padding: "6px 8px", textAlign: "left", borderLeft: "1px solid var(--border)" }}>
                <div style={{ fontFamily: "ui-monospace, monospace", fontSize: 11 }}>{t.ocr}</div>
                <div style={{ fontFamily: "ui-monospace, monospace", fontSize: 11, color: "var(--muted)" }}>
                  → {t.detector}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <CompareRowEl
            label="Status"
            values={targets.map((t) => t.cell?.status ?? "—")}
          />
          <CompareRowEl
            label="Entity count"
            values={targets.map((t) => t.cell?.entity_count ?? 0)}
          />
          <CompareRowEl
            label="Latency (ms)"
            values={targets.map((t) => (t.cell?.latency_ms ? Math.round(t.cell.latency_ms) : "—"))}
          />
          <CompareRowEl
            label="Audit steps"
            values={targets.map((t) => t.cell?.audit_step_count ?? 0)}
          />
          <CompareRowEl
            label="Manual / search additions"
            values={targets.map((t) =>
              `${t.cell?.manual_annotation_count ?? 0} / ${t.cell?.search_only_count ?? 0}`,
            )}
          />
          <tr><td colSpan={targets.length + 1} style={{ padding: "8px 8px 4px", fontWeight: 600, fontSize: 11 }}>By category</td></tr>
          {["PII", "Network", "Location", "Visual"].map((cat) => (
            <CompareRowEl
              key={cat}
              label={cat}
              values={targets.map((t) => t.cell?.category_counts?.[cat] ?? 0)}
            />
          ))}
          {typeList.length > 0 && (
            <tr><td colSpan={targets.length + 1} style={{ padding: "8px 8px 4px", fontWeight: 600, fontSize: 11 }}>By entity type</td></tr>
          )}
          {typeList.map((type) => (
            <CompareRowEl
              key={type}
              label={type}
              values={cells.map((c) => c?.entities.filter((e) => e.entity_type === type).length ?? 0)}
              code
            />
          ))}
          <tr><td colSpan={targets.length + 1} style={{ padding: "8px 8px 4px", fontWeight: 600, fontSize: 11 }}>Discovery</td></tr>
          {allDiscoveries.map((src) => (
            <CompareRowEl
              key={src}
              label={src}
              values={cells.map((c) =>
                (c?.entities ?? []).filter(
                  (e) => ((e.metadata?.discovery as string) ?? "lib") === src,
                ).length,
              )}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CompareRowEl({
  label,
  values,
  code,
}: {
  label: string;
  values: (string | number)[];
  code?: boolean;
}) {
  return (
    <tr style={{ borderTop: "1px solid var(--border)" }}>
      <td style={{ padding: "4px 8px", color: "var(--muted)" }}>
        {code ? <code>{label}</code> : label}
      </td>
      {values.map((v, i) => (
        <td
          key={i}
          style={{
            padding: "4px 8px",
            borderLeft: "1px solid var(--border)",
            fontFamily: typeof v === "number" ? "ui-monospace, monospace" : undefined,
            fontWeight: typeof v === "number" && v > 0 ? 600 : 400,
            color: typeof v === "number" && v === 0 ? "var(--muted)" : undefined,
          }}
        >
          {v}
        </td>
      ))}
    </tr>
  );
}

function bboxForCharSpan(
  start: number,
  end: number,
  index: PiiRegionSpan[],
): { x: number; y: number; w: number; h: number } | null {
  const overlapping = index.filter((rs) => !(rs.end <= start || end <= rs.start));
  if (overlapping.length === 0) return null;
  const boxes: { x: number; y: number; x2: number; y2: number }[] = [];
  for (const rs of overlapping) {
    const tl = rs.text_len || Math.max(1, rs.end - rs.start);
    const xpc = rs.bbox.w / Math.max(1, tl);
    const localStart = Math.max(0, start - rs.start);
    const localEnd = Math.min(tl, end - rs.start);
    if (localEnd <= localStart) continue;
    const x = rs.bbox.x + xpc * localStart;
    const x2 = rs.bbox.x + xpc * localEnd;
    boxes.push({ x, y: rs.bbox.y, x2, y2: rs.bbox.y + rs.bbox.h });
  }
  if (boxes.length === 0) return null;
  const x = Math.min(...boxes.map((b) => b.x));
  const y = Math.min(...boxes.map((b) => b.y));
  const x2 = Math.max(...boxes.map((b) => b.x2));
  const y2 = Math.max(...boxes.map((b) => b.y2));
  return { x, y, w: Math.max(2, x2 - x), h: Math.max(2, y2 - y) };
}
