"use client";

import { useEffect, useRef, useState } from "react";

export type TaskStatus = "pending" | "running" | "done" | "error" | "skipped";

export interface TaskOverlay {
  id: string;       // BPMN element ID = stage_name
  status: TaskStatus;
  durationMs?: number;
}

export interface ClickedElement {
  id: string;
  type: string;     // e.g. "bpmn:ServiceTask", "bpmn:ExclusiveGateway", "bpmn:SequenceFlow"
}

const STATUS_COLOR: Record<TaskStatus, string> = {
  pending: "#9a6700", running: "#0969da",
  done:    "#1a7f37", error:   "#cf222e", skipped: "#57606a",
};

const STATUS_BG: Record<TaskStatus, string> = {
  pending: "#fff8e0", running: "#dbeafe",
  done:    "#dcfce7", error:   "#fee2e2", skipped: "#f3f4f6",
};

// CSS marker classes that may be applied to any element
const ALL_TASK_MARKERS = [
  "ote-task-done", "ote-task-error", "ote-task-running", "ote-task-skipped", "ote-task-pending",
];
const ALL_FLOW_MARKERS = ["ote-flow-done", "ote-flow-error", "ote-flow-skipped", "ote-flow-selected"];

interface Props {
  bpmnXml: string;
  overlays?: TaskOverlay[];
  flowHighlights?: string[];       // sequence flow IDs to highlight
  selectedElementId?: string | null;
  height?: number;
  onElementClick?: (el: ClickedElement) => void;
}

export function BpmnViewer({
  bpmnXml,
  overlays = [],
  flowHighlights = [],
  selectedElementId = null,
  height = 240,
  onElementClick,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef    = useRef<any>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const onClickRef = useRef(onElementClick);
  onClickRef.current = onElementClick;

  // ── init viewer ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;
    let cancelled = false;

    async function init() {
      try {
        const { default: NavigatedViewer } = await import(
          /* webpackChunkName: "bpmn-navigated-viewer" */
          "bpmn-js/lib/NavigatedViewer" as any
        );
        if (cancelled || !containerRef.current) return;

        const viewer = new NavigatedViewer({ container: containerRef.current });
        viewerRef.current = viewer;

        const { warnings } = await viewer.importXML(bpmnXml);
        if (warnings?.length) console.warn("bpmn-js warnings:", warnings);
        if (cancelled) return;

        viewer.get("canvas").zoom("fit-viewport", "auto");
        applyAll(viewer, overlays, flowHighlights, selectedElementId);

        viewer.get("eventBus").on("element.click", (e: any) => {
          const el = e.element;
          if (el && onClickRef.current) {
            onClickRef.current({ id: el.id, type: el.type ?? "" });
          }
        });
      } catch (err: any) {
        if (!cancelled) setLoadError(String(err?.message ?? err));
      }
    }

    init();
    return () => {
      cancelled = true;
      viewerRef.current?.destroy();
      viewerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bpmnXml]);

  // ── re-apply markers/overlays when data changes ───────────────────────────
  useEffect(() => {
    if (viewerRef.current) applyAll(viewerRef.current, overlays, flowHighlights, selectedElementId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overlays, flowHighlights, selectedElementId]);

  if (loadError) {
    return (
      <div style={{ padding: 12, background: "#fee2e2", border: "1px solid #cf222e55", borderRadius: 6, fontSize: 11, color: "#cf222e" }}>
        Could not render BPMN diagram: {loadError}
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height, border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden", background: "#fafbfc" }}
    />
  );
}

// ── helpers ───────────────────────────────────────────────────────────────

function applyAll(
  viewer: any,
  overlays: TaskOverlay[],
  flowHighlights: string[],
  selectedId: string | null,
) {
  try {
    const overlayApi = viewer.get("overlays");
    const canvas     = viewer.get("canvas");
    const registry   = viewer.get("elementRegistry");
    const allEls: any[] = registry.filter(() => true);

    // Clear previous markers
    overlayApi.clear();
    const allMarkers = [...ALL_TASK_MARKERS, ...ALL_FLOW_MARKERS];
    allEls.forEach((el: any) => {
      allMarkers.forEach((cls) => { try { canvas.removeMarker(el.id, cls); } catch {} });
    });

    // Task node markers + overlays
    for (const o of overlays) {
      try { canvas.addMarker(o.id, `ote-task-${o.status}`); } catch {}
      const color  = STATUS_COLOR[o.status];
      const bg     = STATUS_BG[o.status];
      const dur    = o.durationMs != null ? ` · ${o.durationMs.toFixed(0)}ms` : "";
      try {
        overlayApi.add(o.id, "status-badge", {
          position: { bottom: -2, left: 0 },
          html: `<div style="background:${bg};color:${color};border:1px solid ${color}66;border-radius:3px;padding:0 5px;font-size:9px;font-weight:700;line-height:1.7;pointer-events:none;white-space:nowrap">${o.status}${dur}</div>`,
        });
      } catch {}
    }

    // Sequence flow highlighting
    for (const flowId of flowHighlights) {
      try { canvas.addMarker(flowId, "ote-flow-done"); } catch {}
    }

    // Selected element highlight
    if (selectedId) {
      try { canvas.addMarker(selectedId, "ote-flow-selected"); } catch {}
    }
  } catch (err) {
    console.warn("bpmn overlay error:", err);
  }
}
