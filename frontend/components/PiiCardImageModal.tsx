"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  addManualAnnotation,
  getPiiCell,
  getPiiTextLayout,
  getPiiVisualCodes,
  listManualAnnotations,
  piiPageImageUrl,
} from "@/lib/api";
import type {
  PiiCellResult,
  PiiManualAnnotation,
  PiiRegionSpan,
  PiiV2Entity,
  PiiVisualCode,
} from "@/lib/types";
import { ModalShell } from "@/components/PiiCapabilityModal";

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

interface OverlayBox {
  id: string;
  category: string;
  entityType: string;
  label: string;
  bbox: { x: number; y: number; w: number; h: number };
  isManual?: boolean;
  discovery?: string;
}

export function PiiCardImageModal({
  piiRunId,
  documentId,
  initialPage,
  ocr,
  detector,
  totalPages,
  onClose,
}: {
  piiRunId: string;
  documentId: string;
  initialPage: number;
  ocr: string;
  detector: string;
  totalPages: number;
  onClose: () => void;
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
  const [pendingBox, setPendingBox] = useState<null | { x: number; y: number; w: number; h: number }>(null);
  const [pendingType, setPendingType] = useState("PERSON");
  const [pendingText, setPendingText] = useState("");
  const [pendingScope, setPendingScope] = useState<"doc" | "run">("doc");
  const [enabledCategories, setEnabledCategories] = useState<Set<string>>(
    new Set(["PII", "Network", "Location", "Visual", "Manual"]),
  );
  const [maxOverlaysOverride, setMaxOverlaysOverride] = useState(false);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    setCell(null);
    setLayout([]);
    setVisual([]);
    setImageReady(false);
    Promise.all([
      getPiiCell(piiRunId, documentId, pageIndex, ocr, detector),
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
    // PII entity bboxes resolved via the region index
    cell?.entities?.forEach((e: PiiV2Entity, i: number) => {
      const bbox = bboxForCharSpan(e.start, e.end, layout);
      if (!bbox) return;
      out.push({
        id: `e${i}`,
        category: categoryFor(e.entity_type),
        entityType: e.entity_type,
        label: `${e.entity_type}: ${e.text}`,
        bbox,
        discovery: (e.metadata?.discovery as string) ?? "lib",
      });
    });
    // Visual codes (QR + barcode) — pixel bboxes already
    visual.forEach((v, i) => {
      out.push({
        id: `v${i}`,
        category: "Visual",
        entityType: v.type,
        label: `${v.type}: ${v.payload.slice(0, 32)}`,
        bbox: v.bbox_px,
      });
    });
    // Manual annotations on this page
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

  async function submitAnnotation() {
    if (!pendingBox || !pendingText.trim()) return;
    const ann = await addManualAnnotation(piiRunId, documentId, {
      page_index: pageIndex,
      entity_type: pendingType,
      text: pendingText.trim(),
      bbox_px: pendingBox,
      scope: pendingScope,
    });
    setManuals((prev) => [...prev, ann]);
    setPendingBox(null);
    setPendingText("");
    setDrawMode(false);
  }

  return (
    <ModalShell title={`Image · ${ocr} · ${detector} · page ${pageIndex + 1}/${totalPages}`} onClose={onClose} width={980}>
      <div className="row" style={{ gap: 10, alignItems: "center", marginBottom: 8, fontSize: 12 }}>
        <button
          className="btn"
          onClick={() => setPageIndex(Math.max(0, pageIndex - 1))}
          disabled={pageIndex <= 0}
        >
          ← prev
        </button>
        <span>page {pageIndex + 1} / {totalPages}</span>
        <button
          className="btn"
          onClick={() => setPageIndex(Math.min(totalPages - 1, pageIndex + 1))}
          disabled={pageIndex >= totalPages - 1}
        >
          next →
        </button>
        <span style={{ flex: 1 }} />
        <button
          className={`btn ${drawMode ? "primary" : ""}`}
          onClick={() => { setDrawMode(!drawMode); setPendingBox(null); }}
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
          <button
            onClick={() => setMaxOverlaysOverride((v) => !v)}
            className="btn"
            style={{ padding: "1px 10px", fontSize: 11 }}
          >
            {maxOverlaysOverride ? `cap to ${MAX_OVERLAYS_DEFAULT}` : `show all ${overlays.length}`}
          </button>
        )}
        <span className="muted">{visibleOverlays.length} / {overlays.length} overlays</span>
      </div>

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
          if (w < 6 || h < 6) return; // ignore tiny click-and-release
          setPendingBox({ x, y, w, h });
        }}
        style={{
          position: "relative",
          width: "100%",
          background: "#f6f8fa",
          border: "1px solid var(--border)",
          borderRadius: 6,
          overflow: "hidden",
          cursor: drawMode ? "crosshair" : "default",
        }}
      >
        <img
          ref={imageRef}
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
                  x={o.bbox.x}
                  y={o.bbox.y}
                  width={o.bbox.w}
                  height={o.bbox.h}
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

      {pendingBox && (
        <div style={{ marginTop: 10, padding: 10, border: "1px solid var(--border)", borderRadius: 6, background: "#fff8c5" }}>
          <div className="row" style={{ gap: 6, alignItems: "center" }}>
            <strong style={{ fontSize: 12 }}>New annotation</strong>
            <span className="muted" style={{ fontSize: 11 }}>
              ({Math.round(pendingBox.w)}×{Math.round(pendingBox.h)} px)
            </span>
          </div>
          <div className="row" style={{ gap: 8, marginTop: 6, flexWrap: "wrap" }}>
            <select value={pendingType} onChange={(e) => setPendingType(e.target.value)}>
              {["PERSON", "UK_ADDRESS", "ORGANISATION", "EMAIL_ADDRESS", "UK_POSTCODE", "UK_PHONE_NUMBER", "OTHER"].map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <input
              type="text"
              placeholder="text the box contains"
              value={pendingText}
              onChange={(e) => setPendingText(e.target.value)}
              style={{ flex: 1, minWidth: 220 }}
            />
            <label className="row" style={{ gap: 4, fontSize: 11 }}>
              <input
                type="checkbox"
                checked={pendingScope === "run"}
                onChange={(e) => setPendingScope(e.target.checked ? "run" : "doc")}
              />
              keep just for this run
            </label>
            <button className="btn primary" onClick={submitAnnotation} disabled={!pendingText.trim()}>
              save
            </button>
            <button className="btn" onClick={() => { setPendingBox(null); setPendingText(""); }}>cancel</button>
          </div>
        </div>
      )}
    </ModalShell>
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
