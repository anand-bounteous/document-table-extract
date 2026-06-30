"use client";

import { useEffect } from "react";

export type SidePanelTab =
  | "image"
  | "redaction"
  | "spans"
  | "occurrences"
  | "audit"
  | "capabilities"
  | "compare";

export interface SidePanelTabSpec {
  key: SidePanelTab;
  label: string;
  badge?: number | string;
  disabled?: boolean;
}

/**
 * Right-sliding drawer used as the unified drill-down surface for PII cards.
 *
 * Replaces the older centered modal. Width is responsive (60vw clamped to
 * 380-960px). The backdrop is dimmed and click-to-close. Esc also closes.
 */
export function PiiSidePanel({
  open,
  title,
  tabs,
  activeTab,
  onTabChange,
  onClose,
  children,
  openInNewTabHref,
  mode = "drawer",
}: {
  open: boolean;
  title: string;
  tabs: SidePanelTabSpec[];
  activeTab: SidePanelTab;
  onTabChange: (t: SidePanelTab) => void;
  onClose: () => void;
  children: React.ReactNode;
  /** When set, render a ↗ button in the header that pops the same content
   * into a new browser tab at this href. */
  openInNewTabHref?: string;
  /** ``"drawer"`` (default) slides in from the right with a dim backdrop.
   * ``"fullscreen"`` renders inline, full width, no backdrop — used by the
   * dedicated /pii-benchmarks/.../cell/... route. */
  mode?: "drawer" | "fullscreen";
}) {
  useEffect(() => {
    if (!open) return;
    function onKey(ev: KeyboardEvent) {
      if (ev.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const isFullscreen = mode === "fullscreen";
  const asideStyle: React.CSSProperties = isFullscreen
    ? {
        position: "relative",
        width: "100%",
        minHeight: "calc(100vh - 80px)",
        background: "white",
        border: "1px solid var(--border)",
        borderRadius: 8,
        display: "flex",
        flexDirection: "column",
      }
    : {
        position: "fixed",
        top: 0,
        right: 0,
        height: "100vh",
        width: "clamp(380px, 60vw, 960px)",
        background: "white",
        boxShadow: "-8px 0 24px rgba(0,0,0,0.18)",
        transform: open ? "translateX(0)" : "translateX(100%)",
        transition: "transform 0.22s ease",
        zIndex: 100,
        display: "flex",
        flexDirection: "column",
      };

  return (
    <>
      {!isFullscreen && (
        <div
          onClick={onClose}
          style={{
            position: "fixed",
            inset: 0,
            background: open ? "rgba(0,0,0,0.4)" : "transparent",
            pointerEvents: open ? "auto" : "none",
            opacity: open ? 1 : 0,
            transition: "opacity 0.18s ease, background 0.18s ease",
            zIndex: 90,
          }}
        />
      )}
      <aside
        role="dialog"
        aria-modal={!isFullscreen}
        style={asideStyle}
      >
        <header
          style={{
            padding: "12px 16px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 8,
            flexShrink: 0,
          }}
        >
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {title}
          </h2>
          <div className="row" style={{ gap: 6 }}>
            {!isFullscreen && openInNewTabHref && (
              <a
                href={openInNewTabHref}
                target="_blank"
                rel="noreferrer"
                className="btn"
                style={{ padding: "2px 12px" }}
                title="Open this cell's details in a new browser tab (full width, full height)"
              >
                open in new tab ↗
              </a>
            )}
            {!isFullscreen && (
              <button onClick={onClose} className="btn" style={{ padding: "2px 12px" }}>close ✕</button>
            )}
          </div>
        </header>

        <nav
          style={{
            display: "flex",
            gap: 2,
            padding: "8px 12px 0",
            borderBottom: "1px solid var(--border)",
            background: "#fbfbfd",
            flexShrink: 0,
            overflowX: "auto",
          }}
        >
          {tabs.map((t) => {
            const active = activeTab === t.key;
            return (
              <button
                key={t.key}
                onClick={() => onTabChange(t.key)}
                disabled={t.disabled}
                style={{
                  padding: "6px 12px",
                  background: active ? "white" : "transparent",
                  border: "1px solid var(--border)",
                  borderBottom: active ? "1px solid white" : "1px solid var(--border)",
                  borderTopLeftRadius: 6,
                  borderTopRightRadius: 6,
                  marginBottom: -1,
                  cursor: t.disabled ? "not-allowed" : "pointer",
                  fontSize: 12,
                  fontWeight: active ? 600 : 400,
                  color: t.disabled ? "var(--muted)" : active ? "#0969da" : "#57606a",
                  opacity: t.disabled ? 0.55 : 1,
                  whiteSpace: "nowrap",
                }}
              >
                {t.label}
                {t.badge !== undefined && t.badge !== 0 && (
                  <span
                    style={{
                      marginLeft: 6,
                      padding: "0 6px",
                      borderRadius: 999,
                      background: active ? "#0969da22" : "#0969da11",
                      color: "#0969da",
                      fontSize: 10,
                      fontWeight: 600,
                    }}
                  >
                    {t.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        <div style={{ flex: 1, overflow: "auto", padding: 16 }}>
          {children}
        </div>
      </aside>
    </>
  );
}
