"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { getSolutionBpmn } from "@/lib/api";
import type { AuditStep } from "@/lib/types";
import type { TaskOverlay, TaskStatus } from "./BpmnViewer";

// Load BpmnViewer only on the client — bpmn-js touches the DOM at module init
const BpmnViewer = dynamic(
  () => import("./BpmnViewer").then((m) => ({ default: m.BpmnViewer })),
  {
    ssr: false,
    loading: () => (
      <div style={{ height: 240, display: "flex", alignItems: "center", justifyContent: "center", background: "#fafbfc", border: "1px solid var(--border)", borderRadius: 6 }}>
        <span className="muted" style={{ fontSize: 11 }}>Loading BPMN diagram…</span>
      </div>
    ),
  }
);

interface Props {
  solutionName: string;
  audit?: AuditStep[];
}

export function BpmnViewerCard({ solutionName, audit = [] }: Props) {
  const [xml, setXml] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getSolutionBpmn(solutionName)
      .then(setXml)
      .catch((e) => setErr(String(e)));
  }, [solutionName]);

  const overlays: TaskOverlay[] = audit.map((step) => ({
    id: step.stage_name,
    status: step.status as TaskStatus,
    durationMs: step.duration_ms,
  }));

  if (err) {
    return <p className="muted" style={{ fontSize: 11, margin: "6px 0 0" }}>⚠ Could not load diagram: {err}</p>;
  }
  if (!xml) {
    return <p className="muted" style={{ fontSize: 11, margin: "6px 0 0" }}>Loading…</p>;
  }

  return <BpmnViewer bpmnXml={xml} overlays={overlays} />;
}
