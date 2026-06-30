"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { PiiCellSummary } from "@/lib/types";
import { PiiCardDetailPanel, type CompareTarget } from "@/components/PiiCardDetailPanel";
import type { SidePanelTab } from "@/components/PiiSidePanel";

const RISK_COLOR: Record<string, string> = {
  high: "#cf222e",
  medium: "#9a6700",
  low: "#1a7f37",
};

const STATUS_COLOR: Record<string, string> = {
  ok: "#1a7f37",
  skipped: "#57606a",
  error: "#cf222e",
  pending: "#9a6700",
};

type GroupBy = "ocr" | "detector" | "flat";
type StatusFilter = "all" | "ok" | "skipped" | "error";

interface Card {
  ocr: string;
  detector: string;
  cell?: PiiCellSummary;
}

export function PiiBenchmarkGrid({
  piiRunId,
  documentId,
  pageIndex,
  ocrProducers,
  detectorNames,
  pages,
  pairedRunId,
  totalPages = 1,
  categoryFilter,
  onResumePiiDoc,
}: {
  piiRunId: string;
  documentId: string;
  pageIndex: number;
  ocrProducers: string[];
  detectorNames: string[];
  pages: Record<string, Record<string, Record<string, PiiCellSummary>>>;
  pairedRunId?: string | null;
  totalPages?: number;
  categoryFilter?: "PII" | "Network" | "Location" | "Visual";
  onResumePiiDoc?: () => void;
}) {
  const [groupBy, setGroupBy] = useState<GroupBy>("ocr");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [ocrFilter, setOcrFilter] = useState<Set<string>>(new Set());
  const [detFilter, setDetFilter] = useState<Set<string>>(new Set());

  // Side-panel state — replaces the in-card accordions and modals.
  const [panel, setPanel] = useState<{
    target?: { ocr: string; detector: string; cell?: PiiCellSummary };
    initialTab: SidePanelTab;
    compareTargets?: CompareTarget[];
  } | null>(null);

  // Comparison selection (keyed by `${ocr}__${detector}`).
  const [compareSelection, setCompareSelection] = useState<Set<string>>(new Set());
  const compareKeys = Array.from(compareSelection);
  const compareCount = compareKeys.length;

  function toggleCompare(ocr: string, detector: string) {
    setCompareSelection((prev) => {
      const next = new Set(prev);
      const key = `${ocr}__${detector}`;
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const pageKey = String(pageIndex);
  const pageMatrix = pages[pageKey] ?? {};

  const allCards: Card[] = useMemo(() => {
    const out: Card[] = [];
    for (const ocr of ocrProducers) {
      for (const det of detectorNames) {
        const cell = pageMatrix[ocr]?.[det];
        if (categoryFilter) {
          const count = cell?.category_counts?.[categoryFilter] ?? 0;
          // Only render this card in this section if the cell has at least
          // one entity in the requested category, OR if the cell is in an
          // error/skipped state (so the user still sees pipeline coverage).
          if (count === 0 && (cell?.status === "ok" || cell?.status === undefined)) continue;
        }
        out.push({ ocr, detector: det, cell });
      }
    }
    return out;
  }, [ocrProducers, detectorNames, pageMatrix, categoryFilter]);

  const filteredCards = useMemo(() => {
    return allCards.filter((c) => {
      if (ocrFilter.size > 0 && !ocrFilter.has(c.ocr)) return false;
      if (detFilter.size > 0 && !detFilter.has(c.detector)) return false;
      if (statusFilter !== "all") {
        const s = c.cell?.status ?? "pending";
        if (s !== statusFilter) return false;
      }
      return true;
    });
  }, [allCards, ocrFilter, detFilter, statusFilter]);

  const groups = useMemo(() => buildGroups(filteredCards, groupBy), [filteredCards, groupBy]);

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = { ok: 0, skipped: 0, error: 0, pending: 0 };
    for (const c of allCards) {
      const s = c.cell?.status ?? "pending";
      counts[s] = (counts[s] ?? 0) + 1;
    }
    return counts;
  }, [allCards]);

  function toggle(set: Set<string>, setter: (s: Set<string>) => void, key: string) {
    const next = new Set(set);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setter(next);
  }

  return (
    <div>
      <FilterBar
        groupBy={groupBy}
        onGroupByChange={setGroupBy}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        statusCounts={statusCounts}
        ocrProducers={ocrProducers}
        ocrFilter={ocrFilter}
        onOcrToggle={(k) => toggle(ocrFilter, setOcrFilter, k)}
        detectorNames={detectorNames}
        detFilter={detFilter}
        onDetToggle={(k) => toggle(detFilter, setDetFilter, k)}
        nVisible={filteredCards.length}
        nTotal={allCards.length}
      />

      {groups.map((g) => (
        <div key={g.key} style={{ marginBottom: 18 }}>
          <div className="row" style={{ gap: 6, alignItems: "baseline", marginBottom: 6 }}>
            <strong style={{ fontSize: 13 }}>{g.label}</strong>
            <span className="muted" style={{ fontSize: 11 }}>({g.cards.length} card{g.cards.length !== 1 ? "s" : ""})</span>
            {g.kind === "ocr" && pairedRunId && (
              <Link
                href={`/runs/${pairedRunId}?focus=${encodeURIComponent(g.key)}`}
                style={{ fontSize: 11, color: "var(--muted)", marginLeft: 6 }}
              >
                🔗 ocr source
              </Link>
            )}
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
              gap: 12,
            }}
          >
            {g.cards.map((card) => {
              const selKey = `${card.ocr}__${card.detector}`;
              return (
                <PiiCard
                  key={selKey}
                  piiRunId={piiRunId}
                  documentId={documentId}
                  pageIndex={pageIndex}
                  ocr={card.ocr}
                  detector={card.detector}
                  cell={card.cell}
                  pairedRunId={pairedRunId ?? null}
                  groupBy={groupBy}
                  totalPages={totalPages}
                  categoryFilter={categoryFilter}
                  isSelected={compareSelection.has(selKey)}
                  onToggleCompare={() => toggleCompare(card.ocr, card.detector)}
                  onOpenPanel={(initialTab) =>
                    setPanel({
                      target: { ocr: card.ocr, detector: card.detector, cell: card.cell },
                      initialTab,
                    })
                  }
                  onResume={onResumePiiDoc}
                />
              );
            })}
          </div>
        </div>
      ))}

      {groups.length === 0 && (
        <p className="muted" style={{ fontSize: 12 }}>No cards match the current filters.</p>
      )}

      {compareCount >= 2 && (
        <div
          style={{
            position: "fixed",
            bottom: 24,
            right: 24,
            background: "white",
            border: "1px solid var(--border)",
            boxShadow: "0 6px 24px rgba(0,0,0,0.18)",
            borderRadius: 8,
            padding: "10px 14px",
            display: "flex",
            gap: 10,
            alignItems: "center",
            zIndex: 50,
          }}
        >
          <span style={{ fontSize: 12 }}>
            <strong>{compareCount}</strong> cards selected
          </span>
          <button
            className="btn primary"
            onClick={() => {
              const targets: CompareTarget[] = compareKeys
                .map((k) => {
                  const [ocr, detector] = k.split("__");
                  const cell = (pages[String(pageIndex)] ?? {})[ocr]?.[detector];
                  return { ocr, detector, cell };
                })
                .filter((t) => t.ocr && t.detector);
              setPanel({ initialTab: "compare", compareTargets: targets });
            }}
          >
            Compare ↗
          </button>
          <button className="btn" onClick={() => setCompareSelection(new Set())}>
            clear
          </button>
        </div>
      )}

      <PiiCardDetailPanel
        open={panel !== null}
        onClose={() => setPanel(null)}
        piiRunId={piiRunId}
        documentId={documentId}
        pageIndex={pageIndex}
        totalPages={totalPages}
        target={panel?.target}
        initialTab={panel?.initialTab ?? "image"}
        compareTargets={panel?.compareTargets}
        pairedRunId={pairedRunId ?? null}
      />
    </div>
  );
}

function buildGroups(cards: Card[], groupBy: GroupBy):
  Array<{ key: string; label: string; cards: Card[]; kind: GroupBy }> {
  if (groupBy === "flat") {
    return cards.length > 0 ? [{ key: "all", label: "All cards", cards, kind: "flat" }] : [];
  }
  const buckets = new Map<string, Card[]>();
  for (const c of cards) {
    const key = groupBy === "ocr" ? c.ocr : c.detector;
    const list = buckets.get(key) ?? [];
    list.push(c);
    buckets.set(key, list);
  }
  return Array.from(buckets.entries()).map(([key, cards]) => ({
    key,
    label: `${groupBy === "ocr" ? "OCR" : "Detector"} · ${key}`,
    cards,
    kind: groupBy,
  }));
}

function FilterBar({
  groupBy,
  onGroupByChange,
  statusFilter,
  onStatusFilterChange,
  statusCounts,
  ocrProducers,
  ocrFilter,
  onOcrToggle,
  detectorNames,
  detFilter,
  onDetToggle,
  nVisible,
  nTotal,
}: {
  groupBy: GroupBy;
  onGroupByChange: (g: GroupBy) => void;
  statusFilter: StatusFilter;
  onStatusFilterChange: (s: StatusFilter) => void;
  statusCounts: Record<string, number>;
  ocrProducers: string[];
  ocrFilter: Set<string>;
  onOcrToggle: (k: string) => void;
  detectorNames: string[];
  detFilter: Set<string>;
  onDetToggle: (k: string) => void;
  nVisible: number;
  nTotal: number;
}) {
  return (
    <div
      style={{
        marginBottom: 12,
        padding: "8px 12px",
        border: "1px solid var(--border)",
        borderRadius: 8,
        background: "#f6f8fa",
        display: "flex",
        flexWrap: "wrap",
        gap: 10,
        alignItems: "center",
        fontSize: 11,
      }}
    >
      <span className="muted">group by:</span>
      {([
        ["ocr", "OCR producer"],
        ["detector", "Detector"],
        ["flat", "flat"],
      ] as [GroupBy, string][]).map(([k, label]) => {
        const active = groupBy === k;
        return (
          <button
            key={k}
            onClick={() => onGroupByChange(k)}
            style={{
              padding: "2px 10px",
              borderRadius: 999,
              border: `1px solid ${active ? "#0969da" : "#0969da55"}`,
              background: active ? "#0969da22" : "white",
              color: active ? "#0969da" : "#0969da99",
              fontWeight: active ? 700 : 400,
              cursor: "pointer",
            }}
          >
            {label}
          </button>
        );
      })}

      <span style={{ width: 1, height: 16, background: "var(--border)" }} />

      <span className="muted">status:</span>
      {(["all", "ok", "skipped", "error"] as StatusFilter[]).map((s) => {
        const active = statusFilter === s;
        const c = s === "all" ? "#0969da" : STATUS_COLOR[s] ?? "#57606a";
        const count = s === "all" ? Object.values(statusCounts).reduce((a, b) => a + b, 0) : (statusCounts[s] ?? 0);
        return (
          <button
            key={s}
            onClick={() => onStatusFilterChange(s)}
            style={{
              padding: "2px 10px",
              borderRadius: 999,
              border: `1px solid ${active ? c : c + "55"}`,
              background: active ? c + "22" : "white",
              color: active ? c : c + "99",
              fontWeight: active ? 700 : 400,
              cursor: "pointer",
            }}
          >
            {s} ({count})
          </button>
        );
      })}

      <details style={{ position: "relative" }}>
        <summary style={{ cursor: "pointer", color: "#0969da" }}>
          OCR filter {ocrFilter.size > 0 ? `(${ocrFilter.size})` : ""}
        </summary>
        <div
          style={{
            position: "absolute",
            zIndex: 10,
            top: "100%",
            left: 0,
            marginTop: 4,
            padding: 8,
            background: "white",
            border: "1px solid var(--border)",
            borderRadius: 8,
            boxShadow: "0 4px 14px rgba(0,0,0,0.08)",
            minWidth: 200,
          }}
        >
          {ocrProducers.map((p) => (
            <label key={p} className="row" style={{ gap: 6, fontSize: 11 }}>
              <input type="checkbox" checked={ocrFilter.has(p)} onChange={() => onOcrToggle(p)} />
              <code>{p}</code>
            </label>
          ))}
        </div>
      </details>

      <details style={{ position: "relative" }}>
        <summary style={{ cursor: "pointer", color: "#0969da" }}>
          Detector filter {detFilter.size > 0 ? `(${detFilter.size})` : ""}
        </summary>
        <div
          style={{
            position: "absolute",
            zIndex: 10,
            top: "100%",
            left: 0,
            marginTop: 4,
            padding: 8,
            background: "white",
            border: "1px solid var(--border)",
            borderRadius: 8,
            boxShadow: "0 4px 14px rgba(0,0,0,0.08)",
            minWidth: 200,
          }}
        >
          {detectorNames.map((d) => (
            <label key={d} className="row" style={{ gap: 6, fontSize: 11 }}>
              <input type="checkbox" checked={detFilter.has(d)} onChange={() => onDetToggle(d)} />
              <code>{d}</code>
            </label>
          ))}
        </div>
      </details>

      <span style={{ flex: 1 }} />
      <span className="muted">{nVisible} / {nTotal} cards</span>
    </div>
  );
}

function PiiCard({
  ocr,
  detector,
  cell,
  pairedRunId,
  groupBy,
  isSelected,
  onToggleCompare,
  onOpenPanel,
  onResume,
}: {
  piiRunId: string;
  documentId: string;
  pageIndex: number;
  ocr: string;
  detector: string;
  cell?: PiiCellSummary;
  pairedRunId?: string | null;
  groupBy: GroupBy;
  totalPages: number;
  categoryFilter?: "PII" | "Network" | "Location" | "Visual";
  isSelected: boolean;
  onToggleCompare: () => void;
  onOpenPanel: (initialTab: SidePanelTab) => void;
  onResume?: () => void;
}) {
  const status = cell?.status ?? "pending";
  const reason = cell?.reason;
  const statusColor = STATUS_COLOR[status] ?? "#57606a";

  const types = Object.entries(cell?.entity_types ?? {}).sort((a, b) => b[1] - a[1]);
  const headerLabel = groupBy === "ocr" ? detector : groupBy === "detector" ? ocr : `${ocr} → ${detector}`;
  const subLabel = groupBy === "ocr" ? `OCR · ${ocr}` : groupBy === "detector" ? `Detector · ${detector}` : null;
  const manualChip = (cell?.manual_annotation_count ?? 0) > 0;
  const searchChip = (cell?.search_only_count ?? 0) > 0;
  const redactionChip = (cell?.redaction?.n_mocks ?? 0) > 0;

  return (
    <div
      className="card"
      style={{
        opacity: status === "skipped" ? 0.65 : 1,
        borderColor: isSelected ? "#0969da" : status === "error" ? "#cf222e" : undefined,
        borderWidth: isSelected ? 2 : 1,
        position: "relative",
      }}
    >
      <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
        <label className="row" style={{ gap: 6, alignItems: "center", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={isSelected}
            onChange={onToggleCompare}
            title="Select for comparison"
            aria-label="select for comparison"
          />
          <div style={{ fontWeight: 600, fontSize: 13 }}>
            <code>{headerLabel}</code>
          </div>
        </label>
        <span
          style={{
            background: statusColor + "1a",
            color: statusColor,
            border: `1px solid ${statusColor}55`,
            padding: "1px 8px",
            borderRadius: 999,
            fontSize: 11,
            fontWeight: 600,
          }}
        >
          {status}
        </span>
      </div>

      {subLabel && (
        <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>{subLabel}</div>
      )}

      {status !== "ok" && (
        <div style={{ marginBottom: 6 }}>
          <div className="muted" style={{ fontSize: 11, fontStyle: "italic" }}>
            {reason ?? "no detection run for this combination"}
          </div>
          {status === "error" && onResume && (
            <button
              className="btn primary"
              onClick={onResume}
              style={{ padding: "2px 10px", fontSize: 11, marginTop: 6 }}
              title="re-run this document's PII pipeline on the same pii_run_id"
            >
              Resume ▶
            </button>
          )}
        </div>
      )}

      {status === "ok" && (
        <>
          <div className="row" style={{ gap: 6, alignItems: "baseline", marginBottom: 6 }}>
            <strong style={{ fontSize: 18 }}>{cell?.entity_count ?? 0}</strong>
            <span className="muted" style={{ fontSize: 11 }}>
              entit{(cell?.entity_count ?? 0) === 1 ? "y" : "ies"} · {Math.round(cell?.latency_ms ?? 0)}ms
            </span>
            {pairedRunId && (
              <Link
                href={`/runs/${pairedRunId}?focus=${encodeURIComponent(ocr)}`}
                style={{ fontSize: 10, color: "var(--muted)", marginLeft: "auto" }}
                title="Open the OCR card in the paired /runs dashboard"
              >
                🔗 ocr
              </Link>
            )}
          </div>

          {(manualChip || searchChip || redactionChip) && (
            <div className="row" style={{ gap: 4, flexWrap: "wrap", marginBottom: 6, fontSize: 10 }}>
              {redactionChip && (
                <span
                  onClick={() => onOpenPanel("redaction")}
                  style={{
                    cursor: "pointer",
                    padding: "1px 8px",
                    background: "#8250df22",
                    border: "1px solid #8250df77",
                    color: "#8250df",
                    borderRadius: 999,
                    fontWeight: 600,
                  }}
                  title="Same-length mock data ready for LLM. Click to review."
                >
                  🛡 redacted: {cell?.redaction?.n_mocks}
                </span>
              )}
              {manualChip && (
                <span
                  onClick={() => onOpenPanel("image")}
                  style={{
                    cursor: "pointer",
                    padding: "1px 8px",
                    background: "#bf870022",
                    border: "1px solid #bf870077",
                    color: "#bf8700",
                    borderRadius: 999,
                    fontWeight: 600,
                  }}
                  title="User manually annotated PII the lib missed"
                >
                  +{cell?.manual_annotation_count} manual
                </span>
              )}
              {searchChip && (
                <span
                  onClick={() => onOpenPanel("spans")}
                  style={{
                    cursor: "pointer",
                    padding: "1px 8px",
                    background: "#9a670022",
                    border: "1px solid #9a670077",
                    color: "#9a6700",
                    borderRadius: 999,
                    fontWeight: 600,
                  }}
                  title="Fallback regex search found additional occurrences"
                >
                  +{cell?.search_only_count} search
                </span>
              )}
            </div>
          )}

          {types.length > 0 && (
            <div className="row" style={{ flexWrap: "wrap", gap: 3, marginBottom: 6 }}>
              {types.slice(0, 8).map(([t, n]) => (
                <span
                  key={t}
                  style={{
                    fontSize: 10,
                    padding: "1px 6px",
                    background: "#eef",
                    border: "1px solid #ccd",
                    borderRadius: 999,
                  }}
                >
                  {t.replace(/^UK_/, "")} ×{n}
                </span>
              ))}
              {types.length > 8 && (
                <span style={{ fontSize: 10, color: "var(--muted)" }}>+{types.length - 8} more</span>
              )}
            </div>
          )}

          <div className="row" style={{ gap: 10, flexWrap: "wrap", fontSize: 11, marginTop: 6 }}>
            <button onClick={() => onOpenPanel("image")} style={btnLinkStyle}>🖼 image</button>
            <button onClick={() => onOpenPanel("spans")} style={btnLinkStyle}>spans</button>
            <button onClick={() => onOpenPanel("occurrences")} style={btnLinkStyle}>occurrences</button>
            <button onClick={() => onOpenPanel("audit")} style={btnLinkStyle}>audit</button>
            <span style={{ flex: 1 }} />
            <button onClick={() => onOpenPanel("capabilities")} style={btnLinkStyle}>🛈 caps</button>
          </div>
        </>
      )}
    </div>
  );
}

const btnLinkStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  padding: 0,
  cursor: "pointer",
  color: "#0969da",
  fontSize: 11,
};

