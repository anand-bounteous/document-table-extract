"use client";

import { useState } from "react";
import Link from "next/link";
import type { Category, CategoryAccept, CategoryRejection, PageReview, SolutionLifecycle, SolutionResult, SolutionStatusEntry } from "@/lib/types";
import { solutionLogUrl } from "@/lib/api";
import { SOLUTION_GROUPS, TECH_TAGS, TECH_TAG_COLOR, TECH_TAG_DESCRIPTION, estimateLlmCost, type TechTag } from "@/lib/solutionDocs";
import type { LlmUsage } from "@/lib/types";
import { TechTagBadge } from "./SolutionPicker";

const ALL_TAGS: TechTag[] = ["OCR", "Vision", "LLM", "Vector PDF", "Subprocess"];
import { AnnotatedImageViewer } from "./AnnotatedImageViewer";
import { AuditTimeline } from "./AuditTimeline";
import { BpmnViewerCard } from "./BpmnViewerCard";
import { CustomTablePanel } from "./CustomTablePanel";
import { FeatureRegionsPanel } from "./FeatureRegionsPanel";
import { PiiPanel } from "./PiiPanel";
import { RegionTable } from "./RegionTable";
import { TableWithCoordsToggle } from "./TableWithCoordsToggle";

const CATEGORIES: { key: Category; label: string }[] = [
  { key: "tables", label: "Tables" },
  { key: "text", label: "Text" },
  { key: "pii", label: "PII" },
  { key: "layout", label: "Layout" },
];

export interface CategoryEditPayload {
  category: Category;
  order?: number;
  comment: string;
}

const LIFECYCLE_LABEL: Record<SolutionLifecycle, string> = {
  pending: "Pending",
  running: "Processing…",
  done: "Completed",
  error: "Error",
  skipped: "Skipped",
  partial: "Partial",
};

const LIFECYCLE_COLOR: Record<SolutionLifecycle, string> = {
  pending: "#9a6700",      // amber
  running: "#0969da",      // blue
  done: "#1a7f37",         // green
  error: "#cf222e",        // red
  skipped: "#57606a",      // grey
  partial: "#bf8700",      // orange — recovered some pages, sub-stage failed
};

export interface SolutionTile {
  name: string;
  status: SolutionLifecycle;
  entry?: SolutionStatusEntry;
  result?: SolutionResult;
}

function renderCard(
  tile: SolutionTile,
  runId: string,
  pageIndex: number,
  pageReview: PageReview | undefined,
  onAcceptCategory: ((solution: string, payload: CategoryEditPayload) => void) | undefined,
  onRevokeCategory: ((solution: string, category: Category) => void) | undefined,
  onRejectCategory: ((solution: string, category: Category, reason: string) => void) | undefined,
  onUnrejectCategory: ((solution: string, category: Category) => void) | undefined,
  piiV2RunId: string | null | undefined,
  onResumeSolution: ((solution: string) => void) | undefined,
) {
  return (
    <SolutionCard
      key={tile.name}
      runId={runId}
      pageIndex={pageIndex}
      tile={tile}
      pageReview={pageReview}
      piiV2RunId={piiV2RunId ?? null}
      onAcceptCategory={onAcceptCategory ? (p) => onAcceptCategory(tile.name, p) : undefined}
      onRevokeCategory={onRevokeCategory ? (cat) => onRevokeCategory(tile.name, cat) : undefined}
      onRejectCategory={onRejectCategory ? (cat, reason) => onRejectCategory(tile.name, cat, reason) : undefined}
      onUnrejectCategory={onUnrejectCategory ? (cat) => onUnrejectCategory(tile.name, cat) : undefined}
      onResumeSolution={onResumeSolution ? () => onResumeSolution(tile.name) : undefined}
    />
  );
}

export function SolutionCompareGrid({
  runId,
  pageIndex,
  tiles,
  pageReview,
  piiV2RunId,
  onAcceptCategory,
  onRevokeCategory,
  onRejectCategory,
  onUnrejectCategory,
  onResumeSolution,
}: {
  runId: string;
  pageIndex: number;
  tiles: SolutionTile[];
  pageReview?: PageReview;
  piiV2RunId?: string | null;
  onAcceptCategory?: (solution: string, payload: CategoryEditPayload) => void;
  onRevokeCategory?: (solution: string, category: Category) => void;
  onRejectCategory?: (solution: string, category: Category, reason: string) => void;
  onUnrejectCategory?: (solution: string, category: Category) => void;
  onResumeSolution?: (solution: string) => void;
}) {
  const [tagFilter, setTagFilter] = useState<Set<TechTag>>(new Set());
  // Status filter: "all" | "done" | "error" | "running" | "pending" | "skipped"
  const [statusFilter, setStatusFilter] = useState<SolutionLifecycle | "all">("all");

  function toggleTag(tag: TechTag) {
    setTagFilter((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag); else next.add(tag);
      return next;
    });
  }

  function matchesFilter(name: string): boolean {
    if (tagFilter.size === 0) return true;
    const tags = TECH_TAGS[name] ?? [];
    return [...tagFilter].every((t) => tags.includes(t));
  }

  function matchesStatus(tile: SolutionTile): boolean {
    return statusFilter === "all" || tile.status === statusFilter;
  }

  const tileByName = Object.fromEntries(tiles.map((t) => [t.name, t]));

  // Build groups that have at least one tile in this run
  const groups = SOLUTION_GROUPS.map((g) => ({
    ...g,
    members: g.solutions.map((n) => tileByName[n]).filter(Boolean) as SolutionTile[],
  })).filter((g) => g.members.length > 0);

  const groupedNames = new Set(SOLUTION_GROUPS.flatMap((g) => g.solutions));
  const ungrouped = tiles.filter((t) => !groupedNames.has(t.name));

  const args = [runId, pageIndex, pageReview, onAcceptCategory, onRevokeCategory, onRejectCategory, onUnrejectCategory, piiV2RunId, onResumeSolution] as const;

  // Status counts for filter bar
  const statusCounts: Partial<Record<SolutionLifecycle, number>> = {};
  for (const t of tiles) statusCounts[t.status] = (statusCounts[t.status] ?? 0) + 1;
  const availableStatuses = (["running", "done", "error", "skipped", "pending"] as SolutionLifecycle[]).filter(
    (s) => (statusCounts[s] ?? 0) > 0
  );

  const filterBar = (
    <div
      className="row"
      style={{
        flexWrap: "wrap", gap: 6, padding: "8px 10px",
        border: "1px solid var(--border)", borderRadius: 8,
        background: "#f6f8fa", marginBottom: 16, alignItems: "center",
      }}
    >
      <span className="muted" style={{ fontSize: 11, marginRight: 2 }}>filter by tag:</span>
      {ALL_TAGS.map((tag) => {
        const active = tagFilter.has(tag);
        const c = TECH_TAG_COLOR[tag];
        return (
          <button
            key={tag}
            onClick={() => toggleTag(tag)}
            title={TECH_TAG_DESCRIPTION[tag]}
            style={{
              padding: "2px 10px", borderRadius: 999,
              border: `1px solid ${active ? c : c + "55"}`,
              background: active ? c + "22" : "white",
              color: active ? c : c + "99",
              fontSize: 11, fontWeight: active ? 700 : 400, cursor: "pointer",
            }}
          >
            {tag}
          </button>
        );
      })}
      {availableStatuses.length > 1 && (
        <>
          <span style={{ width: 1, height: 16, background: "var(--border)", margin: "0 4px" }} />
          <span className="muted" style={{ fontSize: 11 }}>status:</span>
          <button
            onClick={() => setStatusFilter("all")}
            style={{
              padding: "2px 10px", borderRadius: 999, cursor: "pointer",
              border: `1px solid ${statusFilter === "all" ? "#0969da" : "#0969da55"}`,
              background: statusFilter === "all" ? "#0969da22" : "white",
              color: statusFilter === "all" ? "#0969da" : "#0969da99",
              fontSize: 11, fontWeight: statusFilter === "all" ? 700 : 400,
            }}
          >
            all ({tiles.length})
          </button>
          {availableStatuses.map((s) => {
            const c = LIFECYCLE_COLOR[s];
            const active = statusFilter === s;
            return (
              <button
                key={s}
                onClick={() => setStatusFilter(active ? "all" : s)}
                style={{
                  padding: "2px 10px", borderRadius: 999, cursor: "pointer",
                  border: `1px solid ${active ? c : c + "55"}`,
                  background: active ? c + "22" : "white",
                  color: active ? c : c + "99",
                  fontSize: 11, fontWeight: active ? 700 : 400,
                }}
              >
                {s} ({statusCounts[s]})
              </button>
            );
          })}
        </>
      )}
      {(tagFilter.size > 0 || statusFilter !== "all") && (
        <>
          <span style={{ flex: 1 }} />
          <button
            className="btn"
            style={{ fontSize: 11, padding: "2px 10px" }}
            onClick={() => { setTagFilter(new Set()); setStatusFilter("all"); }}
          >
            clear filters
          </button>
        </>
      )}
    </div>
  );

  if (groups.length === 0) {
    return (
      <div>
        {filterBar}
        <div className="grid cols-3">
          {tiles
            .filter((tile) => matchesStatus(tile))
            .map((tile) => (
              <div key={tile.name} style={{ opacity: matchesFilter(tile.name) ? 1 : 0.35 }}>
                {renderCard(tile, ...args)}
              </div>
            ))}
        </div>
      </div>
    );
  }

  return (
    <div>
      {filterBar}
      {groups.map((g) => {
        const visible = g.members.filter((t) => matchesStatus(t));
        if (visible.length === 0) return null;
        return (
          <div key={g.key} style={{ marginBottom: 24 }}>
            <div className="row" style={{ alignItems: "center", gap: 8, marginBottom: 8 }}>
              <h3 style={{ margin: 0, fontSize: 14 }}>{g.label}</h3>
              <span className="muted" style={{ fontSize: 12 }}>{g.description}</span>
            </div>
            <div className="grid cols-3">
              {visible.map((tile) => (
                <div key={tile.name} style={{ opacity: matchesFilter(tile.name) ? 1 : 0.35 }}>
                  {renderCard(tile, ...args)}
                </div>
              ))}
            </div>
          </div>
        );
      })}
      {ungrouped.filter((t) => matchesStatus(t)).length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h3 style={{ margin: "0 0 8px", fontSize: 14 }}>Other</h3>
          <div className="grid cols-3">
            {ungrouped.filter((t) => matchesStatus(t)).map((tile) => (
              <div key={tile.name} style={{ opacity: matchesFilter(tile.name) ? 1 : 0.35 }}>
                {renderCard(tile, ...args)}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


function StatusPill({
  status,
  progress,
}: {
  status: SolutionLifecycle;
  progress?: { current_page: number; total_pages: number } | null;
}) {
  const c = LIFECYCLE_COLOR[status];
  const showProgress =
    status === "running" && progress && progress.total_pages > 0;
  return (
    <span
      style={{
        background: c + "22",
        color: c,
        border: `1px solid ${c}55`,
        padding: "1px 8px",
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 600,
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
      }}
    >
      {status === "running" && (
        <span
          style={{
            width: 8, height: 8, borderRadius: "50%",
            background: c,
            animation: "ote-pulse 1.2s ease-in-out infinite",
          }}
        />
      )}
      {LIFECYCLE_LABEL[status]}
      {showProgress && (
        <span style={{ opacity: 0.85, fontWeight: 500 }}>
          · page {progress!.current_page}/{progress!.total_pages}
        </span>
      )}
    </span>
  );
}

function SolutionCard({
  runId, pageIndex, tile, pageReview, piiV2RunId, onAcceptCategory, onRevokeCategory, onRejectCategory, onUnrejectCategory, onResumeSolution,
}: {
  runId: string;
  pageIndex: number;
  tile: SolutionTile;
  pageReview?: PageReview;
  piiV2RunId?: string | null;
  onAcceptCategory?: (payload: CategoryEditPayload) => void;
  onRevokeCategory?: (category: Category) => void;
  onRejectCategory?: (category: Category, reason: string) => void;
  onUnrejectCategory?: (category: Category) => void;
  onResumeSolution?: () => void;
}) {
  const { name, status, entry, result } = tile;
  const page = result?.pages.find((p) => p.page_index === pageIndex) ?? result?.pages[0];

  // Aggregate LLM usage across all audit steps that have usage data
  const llmUsage: LlmUsage | null = (() => {
    if (!result?.audit) return null;
    const steps = result.audit.filter((s) => s.usage && (s.usage.input_tokens || s.usage.output_tokens));
    if (steps.length === 0) return null;
    const model = steps[steps.length - 1].usage?.model;
    return {
      model,
      input_tokens: steps.reduce((n, s) => n + (s.usage?.input_tokens ?? 0), 0),
      output_tokens: steps.reduce((n, s) => n + (s.usage?.output_tokens ?? 0), 0),
    };
  })();
  const piiCount = page?.regions.reduce((n, r) => n + r.pii_spans.length, 0) ?? 0;
  const cats = (pageReview?.categories ?? {}) as Partial<Record<Category, CategoryAccept[]>>;
  const rejections = (pageReview?.rejections ?? {}) as Partial<Record<Category, CategoryRejection[]>>;
  function myEntry(category: Category): CategoryAccept | undefined {
    return (cats[category] ?? []).find((e) => e.solution === name);
  }
  const ownsCategories = CATEGORIES.filter((c) => myEntry(c.key) !== undefined).map((c) => c.key);
  const isAccepted = ownsCategories.length > 0;
  const allFour = ownsCategories.length === 4;

  return (
    <div
      className="card"
      style={isAccepted ? { borderColor: "#1a7f37", borderWidth: 2, background: "#f0fff4" } : undefined}
    >
      <style>{`@keyframes ote-pulse { 0%,100% { opacity: 0.35 } 50% { opacity: 1 } }`}</style>

      <div className="row" style={{ marginBottom: 4, justifyContent: "space-between" }}>
        <Link href={`/runs/${runId}/solutions/${encodeURIComponent(name)}`} style={{ fontWeight: 600 }}>
          {name}
        </Link>
        <div className="row" style={{ gap: 6, alignItems: "center" }}>
          {piiV2RunId && (
            <Link
              href={`/pii-benchmarks/${piiV2RunId}`}
              title="Open the paired PII benchmark dashboard"
              style={{
                fontSize: 10,
                padding: "1px 8px",
                borderRadius: 999,
                border: "1px solid #8250df55",
                color: "#8250df",
                background: "#8250df11",
                textDecoration: "none",
                fontWeight: 600,
              }}
            >
              🔗 pii benchmark
            </Link>
          )}
          <StatusPill status={status} progress={entry?.progress ?? null} />
        </div>
      </div>

      {(TECH_TAGS[name] ?? []).length > 0 && (
        <div className="row" style={{ gap: 4, flexWrap: "wrap", marginBottom: 6 }}>
          {(TECH_TAGS[name] ?? []).map((t) => <TechTagBadge key={t} tag={t} />)}
        </div>
      )}

      {(() => {
        // Per-page execution strip: shows done / running / queued dots so
        // the user sees exactly which pages are already on disk (and won't
        // be re-executed on Resume) versus which are still to do.
        const expected = entry?.n_pages_expected ?? result?.pages?.length ?? 0;
        const donePages = new Set((result?.pages ?? []).map((p) => p.page_index));
        const runningPage = entry?.progress?.current_page
          ? entry.progress.current_page - 1
          : null;
        const isRunning = status === "running" || status === "pending";
        // Only worth showing when we have multiple pages AND the run is
        // either incomplete or actively in progress.
        const showStrip = expected > 1 && (donePages.size < expected || isRunning);
        if (!showStrip) return null;
        return (
          <div style={{ marginBottom: 6 }}>
            <div className="row" style={{ gap: 6, fontSize: 10, marginBottom: 3, alignItems: "center" }}>
              <span className="muted">pages:</span>
              <span style={{ color: "#1a7f37" }}>● done {donePages.size}</span>
              {runningPage !== null && !donePages.has(runningPage) && (
                <span style={{ color: "#0969da" }}>● running 1</span>
              )}
              <span className="muted">○ queued {Math.max(0, expected - donePages.size - (runningPage !== null && !donePages.has(runningPage) ? 1 : 0))}</span>
              <span className="muted" style={{ marginLeft: "auto" }}>{donePages.size}/{expected}</span>
            </div>
            <div className="row" style={{ gap: 2, flexWrap: "wrap" }}>
              {Array.from({ length: expected }).map((_, i) => {
                const isDone = donePages.has(i);
                const isCurrent = !isDone && runningPage === i;
                const bg = isDone ? "#1a7f37" : isCurrent ? "#0969da" : "#dde";
                return (
                  <span
                    key={i}
                    title={
                      isDone
                        ? `page ${i + 1} · done (Resume will skip)`
                        : isCurrent
                        ? `page ${i + 1} · running now`
                        : `page ${i + 1} · queued`
                    }
                    style={{
                      width: 12,
                      height: 12,
                      borderRadius: 2,
                      background: bg,
                      border: "1px solid rgba(0,0,0,0.1)",
                      flexShrink: 0,
                      animation: isCurrent ? "ote-pulse 1.4s ease-in-out infinite" : undefined,
                    }}
                  />
                );
              })}
            </div>
          </div>
        );
      })()}

      {(() => {
        // Internal-result inspection — does THIS card need work?
        const done = entry?.n_pages_done ?? (result?.pages?.length ?? 0);
        const expected = entry?.n_pages_expected ?? 0;
        const pageDeficit = expected > 0 && done < expected;
        const stateFailed = status === "error" || status === "partial";
        const resultFailed =
          entry?.result_status === "error" || entry?.result_status === "partial";
        const needsResume = pageDeficit || stateFailed || resultFailed;
        if (!needsResume) return null;
        const missing = pageDeficit ? expected - done : 0;
        const detail = pageDeficit
          ? `${missing} page${missing > 1 ? "s" : ""} skipped due to timeout/failure`
          : entry?.error ?? "this solution failed — Resume to re-execute it on the same run_id";
        return (
          <div
            className="row"
            style={{
              gap: 8,
              alignItems: "center",
              padding: "6px 8px",
              marginBottom: 6,
              background: "#fff8c5",
              border: "1px solid #bf870077",
              borderRadius: 6,
              fontSize: 11,
            }}
            title={entry?.error ?? detail}
          >
            <span style={{ fontSize: 14 }}>⚠</span>
            {pageDeficit ? (
              <strong style={{ color: "#bf8700" }}>{done}/{expected} pages</strong>
            ) : (
              <strong style={{ color: "#bf8700" }}>{status}</strong>
            )}
            <span className="muted" style={{ flex: 1 }}>· {detail}</span>
            {onResumeSolution && (
              <button
                className="btn primary"
                onClick={onResumeSolution}
                style={{ padding: "2px 10px", fontSize: 11 }}
                title="re-run only this solution on the same run_id (keeps other cards intact)"
              >
                Resume ▶
              </button>
            )}
          </div>
        );
      })()}

      {llmUsage && (
        <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 6, fontSize: 11 }}>
          {llmUsage.model && (
            <span style={{ color: "#8250df", background: "#8250df18", border: "1px solid #8250df44", padding: "1px 7px", borderRadius: 999 }}>
              {llmUsage.model}
            </span>
          )}
          <span className="pill" title="Input tokens">↑ {(llmUsage.input_tokens ?? 0).toLocaleString()} in</span>
          <span className="pill" title="Output tokens">↓ {(llmUsage.output_tokens ?? 0).toLocaleString()} out</span>
          {estimateLlmCost(llmUsage) != null && (
            <span className="pill" title="Estimated API cost">
              ~${estimateLlmCost(llmUsage)!.toFixed(4)}
            </span>
          )}
        </div>
      )}

      <div className="row" style={{ marginBottom: 8, fontSize: 11, flexWrap: "wrap", gap: 6 }}>
        {result && <span className="pill">conf {result.overall_confidence.toFixed(2)}</span>}
        {(entry?.duration_ms || result?.timings.total_ms) && (
          <span className="pill">{(entry?.duration_ms ?? result?.timings.total_ms ?? 0).toFixed(0)} ms</span>
        )}
        {page?.doc_format && (
          <span
            className="pill"
            title={
              Object.entries(page.doc_format_scores ?? {})
                .sort((a, b) => b[1] - a[1])
                .map(([k, v]) => `${k}: ${(v * 100).toFixed(0)}%`)
                .join(" · ") || "page-level layout shape"
            }
            style={{
              background: "#fff8e1",
              color: "#9a6700",
              border: "1px solid #d4a72c55",
            }}
          >
            format: {page.doc_format}
          </span>
        )}
        <Link className="btn" href={`/runs/${runId}/solutions/${encodeURIComponent(name)}`} style={{ padding: "2px 8px", fontSize: 11 }}>
          details ↗
        </Link>
        <a className="btn" href={solutionLogUrl(runId, name)} target="_blank" rel="noreferrer" style={{ padding: "2px 8px", fontSize: 11 }}>
          log ↗
        </a>
        {allFour && <span className="pill ok">all categories</span>}
      </div>


      {status === "pending" && (
        <p className="muted" style={{ fontSize: 12 }}>Waiting in queue…</p>
      )}
      {status === "running" && (
        <p className="muted" style={{ fontSize: 12 }}>
          Working — started {entry?.started_at ? new Date(entry.started_at).toLocaleTimeString() : "just now"}.
        </p>
      )}
      {status === "skipped" && result && (
        <p><em>skipped:</em> {result.skipped_reason}</p>
      )}
      {status === "error" && (
        <p style={{ color: "#cf222e", fontSize: 12 }}>
          <em>error:</em> {result?.error ?? entry?.error ?? "unknown"}
        </p>
      )}

      {page && (
        <>
          <AnnotatedImageViewer runId={runId} page={page} caption={`${name} · page ${page.page_index + 1}`} />
          <details style={{ marginTop: 10 }}>
            <summary>Regions ({page.regions.length})</summary>
            <RegionTable regions={page.regions} />
          </details>
          {page.tables.length > 0 && (
            <details>
              <summary>Tables ({page.tables.length})</summary>
              {page.tables.map((t, ti) => (
                <TableWithCoordsToggle key={ti} table={t} />
              ))}
            </details>
          )}
          {/* Per-feature panels (Images, Logos, Signatures, Seals, Watermarks,
              Hyperlinks, PDF Annotations, KV pairs) — only rendered for the
              feature types this solution actually emitted on this page. */}
          <FeatureRegionsPanel page={page} />
          {piiCount > 0 && (
            <details>
              <summary style={{ color: "#cf222e" }}>PII ({piiCount} spans)</summary>
              <PiiPanel runId={runId} solution={name} pageIndex={pageIndex} />
            </details>
          )}
          <details style={{ marginTop: 6 }}>
            <summary>
              Custom-code tables {page.custom_tables && page.custom_tables.length > 0
                ? `(${page.custom_tables.length})`
                : `· ${page.custom_table_status ?? "not_found"}`}
            </summary>
            <CustomTablePanel page={page} />
          </details>
        </>
      )}
      {result && (
        <details style={{ marginTop: 10 }}>
          <summary>Audit ({result.audit.length})</summary>
          <AuditTimeline audit={result.audit} />
        </details>
      )}
      {result && (
        <details style={{ marginTop: 6 }}>
          <summary>Execution flow (BPMN)</summary>
          <div style={{ marginTop: 6 }}>
            <BpmnViewerCard solutionName={name} audit={result.audit} />
          </div>
        </details>
      )}
      {onAcceptCategory && status === "done" && (
        <div style={{ marginTop: 12 }}>
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
            Accept best for page {pageIndex + 1} per category (multiple solutions, lower order = better):
          </div>
          <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
            {CATEGORIES.map(({ key, label }) => (
              <CategoryPill
                key={key}
                solutionName={name}
                category={key}
                label={label}
                entries={cats[key] ?? []}
                onAccept={onAcceptCategory}
                onRevoke={onRevokeCategory}
              />
            ))}
          </div>
          <div className="row" style={{ gap: 4, flexWrap: "wrap", marginTop: 4 }}>
            {CATEGORIES.map(({ key, label }) => (
              <RejectPill
                key={key}
                solutionName={name}
                category={key}
                label={label}
                rejectionEntry={(rejections[key] ?? []).find((r) => r.solution === name)}
                onReject={onRejectCategory ? (reason) => onRejectCategory(key, reason) : undefined}
                onUnreject={onUnrejectCategory ? () => onUnrejectCategory(key) : undefined}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function RejectPill({
  solutionName, category, label, rejectionEntry, onReject, onUnreject,
}: {
  solutionName: string;
  category: Category;
  label: string;
  rejectionEntry?: CategoryRejection;
  onReject?: (reason: string) => void;
  onUnreject?: () => void;
}) {
  const rejected = rejectionEntry !== undefined;
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState(rejectionEntry?.reason ?? "");

  function save() {
    onReject?.(reason);
    setOpen(false);
  }

  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => {
          setReason(rejectionEntry?.reason ?? "");
          setOpen((o) => !o);
        }}
        title={rejected ? `rejected: ${rejectionEntry?.reason || "(no reason)"}` : "mark as negative for this category"}
        style={{
          padding: "3px 9px",
          borderRadius: 999,
          border: `1px solid ${rejected ? "#cf222e" : "#cf222e88"}`,
          background: rejected ? "#fff0f0" : "white",
          color: rejected ? "#cf222e" : "#cf222eaa",
          fontSize: 11,
          fontWeight: rejected ? 600 : 400,
          cursor: "pointer",
        }}
      >
        {rejected ? `✗ ${label}` : `− ${label}`}
      </button>
      {open && (
        <div
          className="card"
          style={{
            position: "absolute", top: "calc(100% + 4px)", left: 0, zIndex: 50,
            minWidth: 260, background: "white", boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
            Reject {label} for {solutionName}
          </div>
          {rejected && rejectionEntry?.reason && (
            <p style={{ fontSize: 11, color: "#cf222e", margin: "0 0 6px" }}>
              Current reason: {rejectionEntry.reason}
            </p>
          )}
          <label style={{ display: "block", fontSize: 11 }}>
            reason
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="why is this solution bad for this category?"
              rows={3}
              style={{ width: "100%", marginTop: 2, padding: 4, fontSize: 12, resize: "vertical" }}
            />
          </label>
          <div className="row" style={{ gap: 6, marginTop: 8, justifyContent: "flex-end" }}>
            {rejected && onUnreject && (
              <button className="btn" onClick={() => { onUnreject(); setOpen(false); }}>
                remove
              </button>
            )}
            <button className="btn" onClick={() => setOpen(false)}>cancel</button>
            {onReject && (
              <button className="btn" style={{ background: "#fff0f0", color: "#cf222e", borderColor: "#cf222e" }} onClick={save}>
                {rejected ? "update" : "reject"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function CategoryPill({
  solutionName, category, label, entries, onAccept, onRevoke,
}: {
  solutionName: string;
  category: Category;
  label: string;
  entries: CategoryAccept[];
  onAccept: (payload: CategoryEditPayload) => void;
  onRevoke?: (category: Category) => void;
}) {
  const mine = entries.find((e) => e.solution === solutionName);
  const owned = mine !== undefined;
  const otherCount = entries.length - (owned ? 1 : 0);
  const [open, setOpen] = useState(false);
  const [comment, setComment] = useState(mine?.comment ?? "");
  const [order, setOrder] = useState<number | "">(mine?.order ?? "");

  function save() {
    onAccept({
      category,
      order: order === "" ? undefined : Number(order),
      comment,
    });
    setOpen(false);
  }

  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => {
          setComment(mine?.comment ?? "");
          setOrder(mine?.order ?? "");
          setOpen((o) => !o);
        }}
        title={owned ? `accepted at #${mine?.order}: ${mine?.comment || "(no comment)"}` : otherCount ? `${otherCount} other accept(s)` : "click to accept"}
        style={{
          padding: "3px 9px",
          borderRadius: 999,
          border: `1px solid ${owned ? "#1a7f37" : "#0969da"}`,
          background: owned ? "#dafbe1" : "white",
          color: owned ? "#1a7f37" : "#0969da",
          fontSize: 11,
          fontWeight: owned ? 600 : 400,
          cursor: "pointer",
        }}
      >
        {owned ? `✓ ${label} (${mine?.order})` : `+ ${label}`}
        {otherCount > 0 && <span className="muted" style={{ marginLeft: 4, fontSize: 10 }}>· {otherCount} other</span>}
      </button>
      {open && (
        <div
          className="card"
          style={{
            position: "absolute", top: "calc(100% + 4px)", left: 0, zIndex: 50,
            minWidth: 260, background: "white", boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>{label} for page · {solutionName}</div>
          <label style={{ display: "block", fontSize: 11, marginBottom: 4 }}>
            rank
            <input
              type="number"
              min={1}
              placeholder={`auto (${entries.length + (owned ? 0 : 1)})`}
              value={order}
              onChange={(e) => setOrder(e.target.value === "" ? "" : Number(e.target.value))}
              style={{ width: "100%", marginTop: 2, padding: 4, fontSize: 12 }}
            />
          </label>
          <label style={{ display: "block", fontSize: 11, marginTop: 6 }}>
            comment
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="what does this solution do well / poorly here?"
              rows={3}
              style={{ width: "100%", marginTop: 2, padding: 4, fontSize: 12, resize: "vertical" }}
            />
          </label>
          <div className="row" style={{ gap: 6, marginTop: 8, justifyContent: "flex-end" }}>
            {owned && onRevoke && (
              <button className="btn" onClick={() => { onRevoke(category); setOpen(false); }}>
                revoke
              </button>
            )}
            <button className="btn" onClick={() => setOpen(false)}>cancel</button>
            <button className="btn primary" onClick={save}>{owned ? "update" : "accept"}</button>
          </div>
        </div>
      )}
    </div>
  );
}
