"use client";

import { useEffect, useState } from "react";
import { artifactUrl, getSolutionPii } from "@/lib/api";
import type { PiiBundle } from "@/lib/types";
import { ZoomableImage } from "./ZoomableImage";

export function PiiPanel({ runId, solution, pageIndex }: { runId: string; solution: string; pageIndex: number }) {
  const [bundle, setBundle] = useState<PiiBundle | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [zoom, setZoom] = useState<{ src: string; caption: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSolutionPii(runId, solution)
      .then((b) => { if (!cancelled) setBundle(b); })
      .catch((e) => { if (!cancelled) setErr(String(e)); });
    return () => { cancelled = true; };
  }, [runId, solution]);

  if (err) return <p style={{ color: "#cf222e" }}>{err}</p>;
  if (!bundle) return <p className="muted">loading PII…</p>;
  if (bundle.tokens.length === 0) return <p className="muted">No PII detected.</p>;

  const tokensForPage = bundle.tokens.filter((t) => t.pages.includes(pageIndex));
  const maskedForPage = bundle.masked_pages.find((m) => m.page_index === pageIndex);
  const mockForPage = (bundle.mock_redacted_pages ?? []).find((m) => m.page_index === pageIndex);
  const isParaLevel = solution === "docling" || solution.startsWith("docling_");

  return (
    <div>
      {isParaLevel && (
        <p className="muted" style={{ fontSize: 11, marginBottom: 6 }}>
          Note: {solution} emits paragraph-level regions; PII bounding boxes are interpolated across the full paragraph width and may appear wider than individual words in the masked image.
        </p>
      )}
      {maskedForPage && (
        <div className="row" style={{ marginBottom: 8, gap: 8 }}>
          <button
            className="btn primary"
            onClick={() => setZoom({ src: artifactUrl(runId, maskedForPage.ref), caption: `Masked page ${pageIndex + 1}` })}
          >
            View masked image
          </button>
          <a
            className="btn"
            href={artifactUrl(runId, maskedForPage.ref)}
            download={`masked-page-${pageIndex + 1}.png`}
          >
            Download masked PNG
          </a>
        </div>
      )}

      {mockForPage && (mockForPage.clean_ref || mockForPage.annotated_ref) && (
        <details
          open
          style={{
            marginBottom: 10,
            padding: 10,
            border: "1px solid #8250df55",
            background: "#8250df0a",
            borderRadius: 6,
          }}
        >
          <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 12, color: "#8250df" }}>
            🛡 Same-length mock redaction (safe for LLM)
            <span className="muted" style={{ fontWeight: 400, marginLeft: 6, fontSize: 11 }}>
              · PII swapped with realistic same-shape mocks · mapping kept encrypted for later restore
            </span>
          </summary>
          <div style={{ marginTop: 8 }}>
            <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>
              Left: original masked PNG (red boxes + masked text — what you see today).
              Right: <strong>annotated</strong> mock-redacted PNG — PII text replaced with a same-length mock so the image fits the original layout AND can be passed to an LLM without leaking PII.
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {maskedForPage ? (
                <SideImage
                  title="Original masked (legacy)"
                  src={artifactUrl(runId, maskedForPage.ref)}
                  onZoom={() => setZoom({ src: artifactUrl(runId, maskedForPage.ref), caption: `Masked page ${pageIndex + 1}` })}
                />
              ) : (
                <div className="muted" style={{ fontSize: 11 }}>(no masked image)</div>
              )}
              {mockForPage.annotated_ref ? (
                <SideImage
                  title="Mock-redacted (annotated)"
                  src={artifactUrl(runId, mockForPage.annotated_ref)}
                  onZoom={() => setZoom({
                    src: artifactUrl(runId, mockForPage.annotated_ref!),
                    caption: `Mock-redacted page ${pageIndex + 1} (annotated)`,
                  })}
                />
              ) : (
                <div className="muted" style={{ fontSize: 11 }}>(annotated variant unavailable)</div>
              )}
            </div>
            <div className="row" style={{ gap: 8, marginTop: 8, flexWrap: "wrap" }}>
              {mockForPage.clean_ref && (
                <a
                  className="btn"
                  href={artifactUrl(runId, mockForPage.clean_ref)}
                  download={`page-${pageIndex + 1}-mock-redacted.png`}
                  title="Clean mock-redacted PNG — no annotations, ready for LLM input"
                >
                  ⬇ clean PNG (LLM-ready)
                </a>
              )}
              {mockForPage.annotated_ref && (
                <a
                  className="btn"
                  href={artifactUrl(runId, mockForPage.annotated_ref)}
                  download={`page-${pageIndex + 1}-mock-redacted-annotated.png`}
                >
                  ⬇ annotated PNG
                </a>
              )}
              {bundle.mock_mapping_ref && (
                <a
                  className="btn"
                  href={artifactUrl(runId, bundle.mock_mapping_ref)}
                  download="mock-mapping.fernet"
                  title="Encrypted mock→original mapping for the future restore step"
                >
                  ⬇ mapping.fernet
                </a>
              )}
              {bundle.mock_mapping_index && (
                <span className="muted" style={{ fontSize: 11, alignSelf: "center" }}>
                  {bundle.mock_mapping_index.n_mappings} unique mocks ·{" "}
                  {Object.entries(bundle.mock_mapping_index.entity_types)
                    .map(([k, v]) => `${k}×${v}`)
                    .join(", ")}
                </span>
              )}
            </div>
          </div>
        </details>
      )}
      <div className="row" style={{ marginBottom: 8 }}>
        <strong>PII — page {pageIndex + 1}</strong>
        <span className="pill">{tokensForPage.length} unique on this page</span>
        <span className="pill">{bundle.tokens.length} unique total</span>
        <label className="row" style={{ gap: 4, cursor: "pointer" }}>
          <input type="checkbox" checked={revealed} onChange={(e) => setRevealed(e.target.checked)} />
          reveal original
        </label>
      </div>
      <table>
        <thead>
          <tr>
            <th>entity</th>
            <th>masked</th>
            <th>{revealed ? "original" : "original (hidden)"}</th>
            <th>token</th>
            <th>occurrences</th>
            <th>pages</th>
          </tr>
        </thead>
        <tbody>
          {tokensForPage.map((t) => (
            <tr key={t.token}>
              <td><span className="pill" style={{ background: "#ffebe9", color: "#cf222e" }}>{t.entity}</span></td>
              <td><code>{t.masked}</code></td>
              <td>{revealed ? <code>{t.original ?? "<missing>"}</code> : <code className="muted">••••</code>}</td>
              <td><code className="muted" style={{ fontSize: 10 }}>{t.token}</code></td>
              <td>{t.n_occurrences}</td>
              <td>{t.pages.map((p) => p + 1).join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {zoom && <ZoomableImage src={zoom.src} alt={zoom.caption} caption={zoom.caption} onClose={() => setZoom(null)} />}
    </div>
  );
}

function SideImage({ title, src, onZoom }: { title: string; src: string; onZoom: () => void }) {
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 6, background: "#fbfbfd" }}>
      <div
        className="row"
        style={{
          fontSize: 11,
          padding: "4px 8px",
          borderBottom: "1px solid var(--border)",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <span className="muted">{title}</span>
        <button onClick={onZoom} className="btn" style={{ padding: "0 8px", fontSize: 10 }} title="zoom">
          🔍
        </button>
      </div>
      <img src={src} alt={title} style={{ width: "100%", display: "block", cursor: "zoom-in" }} onClick={onZoom} />
    </div>
  );
}
