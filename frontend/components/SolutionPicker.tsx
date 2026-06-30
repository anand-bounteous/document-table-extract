"use client";

import { useState } from "react";
import type { SolutionDescriptor } from "@/lib/types";
import {
  SOLUTION_GROUPS,
  TECH_TAGS,
  TECH_TAG_COLOR,
  TECH_TAG_DESCRIPTION,
  type TechTag,
} from "@/lib/solutionDocs";

const ALL_TAGS: TechTag[] = ["OCR", "Vision", "LLM", "Vector PDF", "Subprocess"];

export function SolutionPicker({
  solutions,
  selected,
  onChange,
  showDisabled = true,
}: {
  solutions: SolutionDescriptor[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  showDisabled?: boolean;
}) {
  const [tagFilter, setTagFilter] = useState<Set<TechTag>>(new Set());

  const byName = Object.fromEntries(solutions.map((s) => [s.name, s]));
  const isEnabled = (name: string) => byName[name]?.enabled !== false;

  function toggle(name: string) {
    const next = new Set(selected);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    onChange(next);
  }

  function toggleTag(tag: TechTag) {
    const next = new Set(tagFilter);
    if (next.has(tag)) next.delete(tag);
    else next.add(tag);
    setTagFilter(next);
  }

  function matchesFilter(name: string): boolean {
    if (tagFilter.size === 0) return true;
    const tags = TECH_TAGS[name] ?? [];
    return [...tagFilter].every((t) => tags.includes(t));
  }

  function selectAll() { onChange(new Set(solutions.filter((s) => s.enabled !== false).map((s) => s.name))); }
  function clear() { onChange(new Set()); }
  function selectVectorOnly() {
    onChange(new Set(solutions.filter((s) => !s.supported_kinds.includes("scanned")).map((s) => s.name)));
  }
  function selectFiltered() {
    onChange(new Set(solutions.filter((s) => matchesFilter(s.name)).map((s) => s.name)));
  }

  // Groups with at least one solution in the registry, order by group definition
  const groups = SOLUTION_GROUPS.map((g) => ({
    ...g,
    members: g.solutions.map((n) => byName[n]).filter(Boolean) as SolutionDescriptor[],
  })).filter((g) => g.members.length > 0);

  // Solutions not assigned to any group
  const groupedNames = new Set(SOLUTION_GROUPS.flatMap((g) => g.solutions));
  const ungrouped = solutions.filter((s) => !groupedNames.has(s.name));

  return (
    <div>
      {/* Tag filter bar */}
      <div
        className="row"
        style={{
          flexWrap: "wrap",
          gap: 6,
          padding: "8px 10px",
          border: "1px solid var(--border)",
          borderRadius: 8,
          background: "#f6f8fa",
          marginBottom: 8,
          alignItems: "center",
        }}
      >
        <span className="muted" style={{ fontSize: 11, marginRight: 4 }}>filter by tag:</span>
        {ALL_TAGS.map((tag) => {
          const active = tagFilter.has(tag);
          const c = TECH_TAG_COLOR[tag];
          return (
            <button
              key={tag}
              onClick={() => toggleTag(tag)}
              title={TECH_TAG_DESCRIPTION[tag]}
              style={{
                padding: "2px 10px",
                borderRadius: 999,
                border: `1px solid ${active ? c : c + "55"}`,
                background: active ? c + "22" : "white",
                color: active ? c : c + "99",
                fontSize: 11,
                fontWeight: active ? 700 : 400,
                cursor: "pointer",
              }}
            >
              {tag}
            </button>
          );
        })}
        <span style={{ flex: 1 }} />
        <button onClick={selectAll} className="btn" style={{ padding: "3px 10px", fontSize: 11 }}>all</button>
        <button onClick={clear} className="btn" style={{ padding: "3px 10px", fontSize: 11 }}>none</button>
        <button onClick={selectVectorOnly} className="btn" style={{ padding: "3px 10px", fontSize: 11 }}>vector-only</button>
        {tagFilter.size > 0 && (
          <button onClick={selectFiltered} className="btn" style={{ padding: "3px 10px", fontSize: 11 }}>select filtered</button>
        )}
      </div>

      {/* Grouped cards */}
      {groups.map((g) => {
        const visible = g.members.filter((s) => matchesFilter(s.name));
        if (visible.length === 0) return null;
        const groupSelected = g.members.filter((s) => selected.has(s.name)).length;
        const groupTotal = g.members.length;
        return (
          <div key={g.key} style={{ marginBottom: 16 }}>
            <div className="row" style={{ alignItems: "baseline", marginBottom: 6, gap: 8 }}>
              <h4 style={{ margin: 0, fontSize: 13 }}>{g.label}</h4>
              <span className="muted" style={{ fontSize: 11 }}>{g.description}</span>
              <span style={{ flex: 1 }} />
              <button
                className="btn"
                style={{ padding: "2px 8px", fontSize: 10 }}
                onClick={() => {
                  const next = new Set(selected);
                  g.members.forEach((s) => next.add(s.name));
                  onChange(next);
                }}
              >
                all
              </button>
              <button
                className="btn"
                style={{ padding: "2px 8px", fontSize: 10 }}
                onClick={() => {
                  const next = new Set(selected);
                  g.members.forEach((s) => next.delete(s.name));
                  onChange(next);
                }}
              >
                none
              </button>
              <span className="muted" style={{ fontSize: 10 }}>{groupSelected}/{groupTotal}</span>
            </div>
            <div className="grid cols-3">
              {visible.map((s) => {
                const on = selected.has(s.name);
                const tags = TECH_TAGS[s.name] ?? [];
                const enabled = s.enabled !== false;
                return (
                  <label
                    key={s.name}
                    className="card"
                    style={{
                      cursor: enabled ? "pointer" : "not-allowed",
                      borderColor: on ? "#1a7f37" : (!enabled ? "#e0e0e0" : undefined),
                      opacity: !matchesFilter(s.name) ? 0.45 : (!enabled ? 0.55 : 1),
                      background: !enabled ? "#fafafa" : undefined,
                    }}
                  >
                    <div className="row" style={{ marginBottom: 4, gap: 6 }}>
                      <input type="checkbox" checked={on} disabled={!enabled} onChange={() => enabled && toggle(s.name)} />
                      <strong style={{ fontSize: 12 }}>{s.display_name}</strong>
                      {s.model && (
                        <span style={{ fontSize: 10, color: "#8250df", background: "#8250df18", border: "1px solid #8250df44", padding: "0 6px", borderRadius: 999 }}>
                          {s.model}
                        </span>
                      )}
                    </div>
                    {tags.length > 0 && (
                      <div className="row" style={{ gap: 4, flexWrap: "wrap", margin: "3px 0 5px" }}>
                        {tags.map((t) => <TechTagBadge key={t} tag={t} />)}
                      </div>
                    )}
                    {!enabled && (
                      <div style={{ fontSize: 10, color: "#cf222e", marginBottom: 4 }}>
                        ⚠ API key not configured in .env
                      </div>
                    )}
                    <div className="muted" style={{ fontSize: 11 }}>{s.description}</div>
                    <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>
                      kinds: {s.supported_kinds.join(", ")}
                    </div>
                  </label>
                );
              })}
            </div>
          </div>
        );
      })}

      {/* Ungrouped fallback */}
      {ungrouped.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <h4 style={{ margin: "0 0 6px", fontSize: 13 }}>Other</h4>
          <div className="grid cols-3">
            {ungrouped.filter((s) => matchesFilter(s.name)).map((s) => {
              const on = selected.has(s.name);
              const tags = TECH_TAGS[s.name] ?? [];
              return (
                <label key={s.name} className="card" style={{ cursor: "pointer", borderColor: on ? "#1a7f37" : undefined }}>
                  <div className="row" style={{ marginBottom: 4 }}>
                    <input type="checkbox" checked={on} onChange={() => toggle(s.name)} />
                    <strong style={{ fontSize: 12 }}>{s.display_name}</strong>
                  </div>
                  {tags.length > 0 && (
                    <div className="row" style={{ gap: 4, flexWrap: "wrap", margin: "3px 0 5px" }}>
                      {tags.map((t) => <TechTagBadge key={t} tag={t} />)}
                    </div>
                  )}
                  <div className="muted" style={{ fontSize: 11 }}>{s.description}</div>
                  <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>kinds: {s.supported_kinds.join(", ")}</div>
                </label>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export function TechTagBadge({ tag }: { tag: TechTag }) {
  const color = TECH_TAG_COLOR[tag];
  return (
    <span
      title={TECH_TAG_DESCRIPTION[tag]}
      style={{
        background: color + "1a",
        color,
        border: `1px solid ${color}55`,
        padding: "0 7px",
        borderRadius: 999,
        fontSize: 10,
        fontWeight: 600,
        letterSpacing: 0.3,
        textTransform: "uppercase" as const,
      }}
    >
      {tag}
    </span>
  );
}
