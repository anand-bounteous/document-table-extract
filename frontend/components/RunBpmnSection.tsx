"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import { getMasterBpmn } from "@/lib/api";
import type { AuditStep, SolutionResult } from "@/lib/types";
import type { ClickedElement, TaskOverlay, TaskStatus } from "./BpmnViewer";

// ── client-only BpmnViewer ────────────────────────────────────────────────
const BpmnViewer = dynamic(
  () => import("./BpmnViewer").then((m) => ({ default: m.BpmnViewer })),
  {
    ssr: false,
    loading: () => (
      <div style={{ height: 520, display: "flex", alignItems: "center", justifyContent: "center", background: "#fafbfc", border: "1px solid var(--border)", borderRadius: 6 }}>
        <span className="muted" style={{ fontSize: 11 }}>Loading master pipeline diagram…</span>
      </div>
    ),
  }
);

// ── master pipeline definition (mirrors backend/app/bpmn/generator.py) ────

interface Branch { label: string; tasks: string[] }
interface Group  { id: string; branches: Branch[] }

const MASTER_GROUPS: Group[] = [
  { id: "preprocessing", branches: [
    { label: "OpenCV Pre-process", tasks: ["preprocess_opencv", "layout_ruled_table"] },
    { label: "skip",               tasks: [] },
  ]},
  { id: "ocr", branches: [
    { label: "Tesseract OCR", tasks: ["ocr_tesseract"] },
    { label: "EasyOCR",       tasks: ["ocr_easyocr"] },
    { label: "DocTR",         tasks: ["ocr_doctr"] },
    { label: "skip",          tasks: [] },
  ]},
  { id: "img2table", branches: [
    { label: "img2table · Tesseract", tasks: ["tables_img2table_tesseract"] },
    { label: "img2table · EasyOCR",  tasks: ["tables_img2table_easyocr"] },
    { label: "img2table · DocTR",    tasks: ["tables_img2table_doctr"] },
    { label: "img2table · Paddle",   tasks: ["tables_img2table_paddle"] },
    { label: "skip",                 tasks: [] },
  ]},
  { id: "vector_tables", branches: [
    { label: "Camelot (both)",    tasks: ["tables_camelot"] },
    { label: "Camelot Lattice",   tasks: ["tables_camelot_lattice"] },
    { label: "Camelot Stream",    tasks: ["tables_camelot_stream"] },
    { label: "Tabula (both)",     tasks: ["tables_tabula"] },
    { label: "Tabula Lattice",    tasks: ["tables_tabula_lattice"] },
    { label: "Tabula Stream",     tasks: ["tables_tabula_stream"] },
    { label: "skip",              tasks: [] },
  ]},
  { id: "vision_llm", branches: [
    { label: "Claude Vision",         tasks: ["vision_claude"] },
    { label: "OpenAI Vision",         tasks: ["vision_openai"] },
    { label: "Gemini Vision",         tasks: ["vision_gemini"] },
    { label: "Paddle Structure",      tasks: ["vision_paddle_structure"] },
    { label: "Docling",               tasks: ["vision_docling"] },
    { label: "skip",                  tasks: [] },
  ]},
];

const COMMON_TAIL = [
  "pii_presidio", "layout_custom_table", "table_crop", "table_obfuscate", "annotate_render",
];

// ── status helpers ────────────────────────────────────────────────────────

const STATUS_COLOR: Record<TaskStatus, string> = {
  pending: "#9a6700", running: "#0969da",
  done: "#1a7f37",   error: "#cf222e", skipped: "#57606a",
};
const STATUS_BG: Record<TaskStatus, string> = {
  pending: "#fff8e0", running: "#dbeafe",
  done: "#dcfce7",   error: "#fee2e2", skipped: "#f3f4f6",
};

type StepStatus = "done" | "error" | "skipped";

function stageStatus(step: AuditStep): StepStatus {
  if (step.status === "error") return "error";
  if (step.status === "skipped") return "skipped";
  return "done";
}

function worstOf(statuses: StepStatus[]): TaskStatus {
  if (statuses.includes("error")) return "error";
  if (statuses.includes("done"))  return "done";
  return "skipped";
}

// ── flow computation ──────────────────────────────────────────────────────

function computeFlowHighlights(results: SolutionResult[]): Set<string> {
  const hl = new Set<string>();
  if (!results.length) return hl;

  let prevId = "Start";

  for (const group of MASTER_GROUPS) {
    const splitId = `gw_split_${group.id}`;
    const joinId  = `gw_join_${group.id}`;

    hl.add(`flow_${prevId}_${splitId}`);

    const takenBranchIndices = new Set<number>();

    for (const result of results) {
      const executed = new Set(result.audit.map((a) => a.stage_name));
      let found = -1;
      for (let bIdx = 0; bIdx < group.branches.length; bIdx++) {
        const { tasks } = group.branches[bIdx];
        if (tasks.length > 0 && tasks.some((t) => executed.has(t))) { found = bIdx; break; }
      }
      // If no matching branch found, this solution took the skip path
      const skipIdx = group.branches.findIndex((b) => b.tasks.length === 0);
      takenBranchIndices.add(found === -1 ? skipIdx : found);
    }

    for (const bIdx of takenBranchIndices) {
      const branch = group.branches[bIdx];
      if (branch.tasks.length === 0) {
        hl.add(`flow_${splitId}_skip${bIdx}_${joinId}`);
      } else {
        hl.add(`flow_${splitId}_${branch.tasks[0]}`);
        for (let t = 0; t < branch.tasks.length - 1; t++) {
          hl.add(`flow_${branch.tasks[t]}_${branch.tasks[t + 1]}`);
        }
        hl.add(`flow_${branch.tasks[branch.tasks.length - 1]}_${joinId}`);
      }
    }

    prevId = joinId;
  }

  // Common tail
  const anyTail = results.some((r) => r.audit.some((a) => COMMON_TAIL.includes(a.stage_name)));
  if (anyTail) {
    hl.add(`flow_${prevId}_${COMMON_TAIL[0]}`);
    for (let i = 0; i < COMMON_TAIL.length - 1; i++) {
      hl.add(`flow_${COMMON_TAIL[i]}_${COMMON_TAIL[i + 1]}`);
    }
    hl.add(`flow_${COMMON_TAIL[COMMON_TAIL.length - 1]}_End`);
  }

  return hl;
}

// ── stage aggregation ─────────────────────────────────────────────────────

interface StageInfo {
  stage_name: string;
  steps: Array<{ solution: string; step: AuditStep }>;
  worstStatus: TaskStatus;
}

function buildStageMap(results: SolutionResult[]): Map<string, StageInfo> {
  const m = new Map<string, StageInfo>();
  for (const result of results) {
    for (const step of result.audit) {
      let info = m.get(step.stage_name);
      if (!info) { info = { stage_name: step.stage_name, steps: [], worstStatus: "done" }; m.set(step.stage_name, info); }
      info.steps.push({ solution: result.solution_name, step });
    }
  }
  for (const info of m.values()) {
    info.worstStatus = worstOf(info.steps.map(({ step }) => stageStatus(step)));
  }
  return m;
}

// ── gateway branch routing ────────────────────────────────────────────────

interface BranchRouting {
  branch: Branch;
  solutions: string[];
}

function gatewayRouting(groupId: string, results: SolutionResult[]): BranchRouting[] {
  const group = MASTER_GROUPS.find((g) => g.id === groupId);
  if (!group) return [];

  const map = new Map<number, string[]>();
  for (const result of results) {
    const executed = new Set(result.audit.map((a) => a.stage_name));
    let found = group.branches.findIndex((b) => b.tasks.length > 0 && b.tasks.some((t) => executed.has(t)));
    if (found === -1) found = group.branches.findIndex((b) => b.tasks.length === 0);
    if (found !== -1) {
      if (!map.has(found)) map.set(found, []);
      map.get(found)!.push(result.solution_name);
    }
  }

  return group.branches.map((branch, idx) => ({
    branch,
    solutions: map.get(idx) ?? [],
  }));
}

// ── main component ────────────────────────────────────────────────────────

interface Props { results: SolutionResult[] }

export function RunBpmnSection({ results }: Props) {
  const [xml, setXml]         = useState<string | null>(null);
  const [err, setErr]         = useState<string | null>(null);
  const [selected, setSelected] = useState<ClickedElement | null>(null);

  useEffect(() => {
    getMasterBpmn().then(setXml).catch((e) => setErr(String(e)));
  }, []);

  const stageMap  = useMemo(() => buildStageMap(results), [results]);
  const flowHighlights = useMemo(() => [...computeFlowHighlights(results)], [results]);

  const overlays: TaskOverlay[] = useMemo(() =>
    Array.from(stageMap.values()).map((info) => ({
      id: info.stage_name,
      status: info.worstStatus,
      durationMs: info.steps.reduce((s, { step }) => s + step.duration_ms, 0) / info.steps.length,
    })),
  [stageMap]);

  const handleClick = (el: ClickedElement) => {
    setSelected((prev) => (prev?.id === el.id ? null : el));
  };

  if (err)  return <p className="muted" style={{ fontSize: 11 }}>⚠ Could not load master BPMN: {err}</p>;
  if (!xml) return <p className="muted" style={{ fontSize: 11 }}>Loading pipeline diagram…</p>;

  return (
    <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
      {/* ── BPMN canvas ── */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <BpmnViewer
          bpmnXml={xml}
          overlays={overlays}
          flowHighlights={flowHighlights}
          selectedElementId={selected?.id ?? null}
          height={520}
          onElementClick={handleClick}
        />
        <p className="muted" style={{ fontSize: 10, margin: "4px 0 0" }}>
          Click any task or gateway to inspect its details →
        </p>
      </div>

      {/* ── right inspector panel ── */}
      <div style={{
        width: 320, flexShrink: 0,
        border: "1px solid var(--border)", borderRadius: 8,
        background: "#fff", fontSize: 12, minHeight: 520,
        display: "flex", flexDirection: "column",
      }}>
        {selected
          ? <Inspector el={selected} stageMap={stageMap} results={results} onClose={() => setSelected(null)} />
          : <EmptyInspector stageMap={stageMap} results={results} />
        }
      </div>
    </div>
  );
}

// ── empty / default inspector ─────────────────────────────────────────────

function EmptyInspector({ stageMap, results }: { stageMap: Map<string, StageInfo>; results: SolutionResult[] }) {
  const totalMs = results.reduce((s, r) => s + (r.timings?.total_ms ?? 0), 0);
  const totalStages = Array.from(stageMap.values()).reduce((s, info) => s + info.steps.length, 0);

  return (
    <div style={{ padding: 16 }}>
      <p style={{ fontWeight: 700, fontSize: 13, marginBottom: 12 }}>Pipeline Inspector</p>
      <p className="muted" style={{ fontSize: 11, marginBottom: 16 }}>
        Click any task (rectangle) or gateway (diamond) in the diagram to inspect its details.
      </p>

      <Section label="Run Summary">
        <KVTable data={{
          "Solutions run": results.length,
          "Unique stages executed": stageMap.size,
          "Total stage invocations": totalStages,
          "Combined wall time": `${(totalMs / 1000).toFixed(1)}s`,
        }} />
      </Section>

      <Section label="Flow legend">
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          {(["done", "error", "skipped"] as TaskStatus[]).map((s) => (
            <div key={s} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ width: 28, height: 3, background: STATUS_COLOR[s], borderRadius: 2 }} />
              <div style={{ width: 12, height: 12, borderRadius: 2, background: STATUS_BG[s], border: `1px solid ${STATUS_COLOR[s]}` }} />
              <span style={{ color: "#57606a" }}>{s}</span>
            </div>
          ))}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{ width: 28, height: 3, background: "#d0d7de", borderRadius: 2 }} />
            <div style={{ width: 12, height: 12, borderRadius: 2, background: "#eaeef2", border: "1px solid #d0d7de" }} />
            <span style={{ color: "#57606a" }}>not executed</span>
          </div>
        </div>
      </Section>
    </div>
  );
}

// ── element inspector ─────────────────────────────────────────────────────

function Inspector({
  el, stageMap, results, onClose,
}: {
  el: ClickedElement;
  stageMap: Map<string, StageInfo>;
  results: SolutionResult[];
  onClose: () => void;
}) {
  const Header = (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 14px 0", marginBottom: 10 }}>
      <span className="muted" style={{ fontSize: 10, fontFamily: "monospace" }}>{el.id}</span>
      <button onClick={onClose} style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 18, lineHeight: 1, color: "#57606a" }}>×</button>
    </div>
  );

  // ── Gateway ──
  if (el.type === "bpmn:ExclusiveGateway") {
    const isJoin = el.id.startsWith("gw_join_");
    const groupId = el.id.replace(/^gw_(split|join)_/, "");
    const group = MASTER_GROUPS.find((g) => g.id === groupId);
    const routings = group ? gatewayRouting(groupId, results) : [];

    return (
      <div style={{ padding: "0 14px 14px", overflowY: "auto", flex: 1 }}>
        {Header}
        <p style={{ fontWeight: 700, fontSize: 13, marginBottom: 2 }}>
          {isJoin ? "Join" : "Split"} Gateway
        </p>
        <p className="muted" style={{ fontSize: 11, marginBottom: 12 }}>
          {group ? `Group: ${group.id.replace(/_/g, " ")}` : el.id}
        </p>

        {!group && <p className="muted" style={{ fontSize: 11 }}>No branch info available.</p>}

        {group && routings.map(({ branch, solutions }, idx) => {
          const taken = solutions.length > 0;
          return (
            <div key={idx} style={{
              marginBottom: 8, padding: "8px 10px",
              border: `1px solid ${taken ? STATUS_COLOR.done + "44" : "var(--border)"}`,
              borderRadius: 6,
              background: taken ? STATUS_BG.done : "#fafbfc",
            }}>
              <div style={{ fontWeight: 600, marginBottom: 4, color: taken ? STATUS_COLOR.done : "#57606a" }}>
                {branch.label}
              </div>
              {branch.tasks.length > 0 && (
                <div className="muted" style={{ fontSize: 10, marginBottom: 6, fontFamily: "monospace" }}>
                  {branch.tasks.join(" → ")}
                </div>
              )}
              {solutions.length > 0
                ? <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {solutions.map((s) => <span key={s} className="pill ok" style={{ fontSize: 10 }}>{s}</span>)}
                  </div>
                : <span className="muted" style={{ fontSize: 10 }}>No solution took this path</span>
              }
            </div>
          );
        })}
      </div>
    );
  }

  // ── Sequence flow ──
  if (el.type === "bpmn:SequenceFlow") {
    return (
      <div style={{ padding: "0 14px 14px", overflowY: "auto", flex: 1 }}>
        {Header}
        <p style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>Sequence Flow</p>
        <p className="muted" style={{ fontSize: 11 }}>
          This connection links two pipeline elements. Select a task or gateway for detailed inspection.
        </p>
      </div>
    );
  }

  // ── Task ──
  const info = stageMap.get(el.id);
  if (!info) {
    return (
      <div style={{ padding: "0 14px 14px", flex: 1 }}>
        {Header}
        <p style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>{el.id.replace(/_/g, " ")}</p>
        <p className="muted" style={{ fontSize: 11 }}>This stage was not executed in this run.</p>
      </div>
    );
  }

  const color = STATUS_COLOR[info.worstStatus];
  const bg    = STATUS_BG[info.worstStatus];

  return (
    <div style={{ padding: "0 14px 14px", overflowY: "auto", flex: 1 }}>
      {Header}
      <div style={{ marginBottom: 10 }}>
        <span style={{ background: bg, color, border: `1px solid ${color}66`, borderRadius: 4, padding: "1px 7px", fontSize: 10, fontWeight: 700, marginRight: 6 }}>
          {info.worstStatus}
        </span>
        <strong style={{ fontSize: 13 }}>{info.stage_name.replace(/_/g, " ")}</strong>
      </div>

      {info.steps.map(({ solution, step }) => (
        <StepDetail key={solution} solution={solution} step={step} />
      ))}
    </div>
  );
}

// ── per-solution step detail ──────────────────────────────────────────────

function StepDetail({ solution, step }: { solution: string; step: AuditStep }) {
  const [open, setOpen] = useState(true);
  const sc = step.status === "error" ? STATUS_COLOR.error : step.status === "skipped" ? STATUS_COLOR.skipped : STATUS_COLOR.done;

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 6, marginBottom: 8 }}>
      <button onClick={() => setOpen((o) => !o)} style={{
        width: "100%", textAlign: "left", padding: "6px 10px",
        background: "#f6f8fa", border: "none", cursor: "pointer",
        borderRadius: open ? "6px 6px 0 0" : 6, fontWeight: 600, fontSize: 11,
        display: "flex", justifyContent: "space-between",
      }}>
        <span style={{ color: sc }}>● </span>
        <span style={{ flex: 1, marginLeft: 4 }}>{solution}</span>
        <span className="muted" style={{ fontWeight: 400, fontSize: 10 }}>
          {step.duration_ms.toFixed(0)}ms {open ? "▲" : "▼"}
        </span>
      </button>

      {open && (
        <div style={{ padding: "8px 10px" }}>
          {Object.keys(step.params ?? {}).length > 0 && (
            <Section label="Params"><KVTable data={step.params as Record<string, unknown>} /></Section>
          )}
          {(step.inputs ?? []).length > 0 && (
            <Section label="Inputs">
              <ArtifactList names={step.inputs} kind="in" />
            </Section>
          )}
          {(step.outputs ?? []).length > 0 && (
            <Section label="Outputs">
              <ArtifactList names={step.outputs} kind="out" />
            </Section>
          )}
          {step.usage && Object.keys(step.usage).length > 0 && (
            <Section label="LLM Usage">
              {step.usage.model && <div className="muted" style={{ marginBottom: 4 }}>{step.usage.model}</div>}
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {step.usage.input_tokens != null  && <span className="pill">↑ {step.usage.input_tokens.toLocaleString()} in</span>}
                {step.usage.output_tokens != null && <span className="pill">↓ {step.usage.output_tokens.toLocaleString()} out</span>}
              </div>
            </Section>
          )}
          {step.message && (
            <div style={{ marginTop: 4, padding: "4px 6px", background: "#fee2e2", borderRadius: 4, color: "#cf222e", fontSize: 11 }}>
              {step.message}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── shared sub-components ─────────────────────────────────────────────────

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: "#57606a", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
        {label}
      </div>
      {children}
    </div>
  );
}

function ArtifactList({ names, kind }: { names: string[]; kind: "in" | "out" }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "2px 4px" }}>
      {names.map((n) => {
        const short = n.split("/").pop() ?? n;
        return (
          <div key={n} title={n} style={{
            background: kind === "out" ? "#dcfce7" : "#f6f8fa",
            border: `1px solid ${kind === "out" ? "#1a7f3733" : "var(--border)"}`,
            borderRadius: 4, padding: "1px 6px", fontSize: 10, wordBreak: "break-all",
          }}>{short}</div>
        );
      })}
    </div>
  );
}

function KVTable({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(([, v]) => v !== null && v !== undefined);
  if (!entries.length) return null;
  return (
    <table style={{ fontSize: 11, borderCollapse: "collapse", width: "100%" }}>
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k}>
            <td style={{ padding: "2px 4px", color: "#57606a", whiteSpace: "nowrap", border: "1px solid var(--border)", verticalAlign: "top" }}>{k}</td>
            <td style={{ padding: "2px 4px", border: "1px solid var(--border)", wordBreak: "break-all" }}>
              {typeof v === "object" ? JSON.stringify(v) : String(v)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
