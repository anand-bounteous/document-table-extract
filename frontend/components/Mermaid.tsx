"use client";

import { useEffect, useId, useRef, useState } from "react";

let mermaidInitPromise: Promise<typeof import("mermaid").default> | null = null;
function loadMermaid() {
  if (!mermaidInitPromise) {
    mermaidInitPromise = import("mermaid").then((mod) => {
      const m = mod.default;
      m.initialize({ startOnLoad: false, securityLevel: "loose", theme: "neutral", fontFamily: "inherit" });
      return m;
    });
  }
  return mermaidInitPromise;
}

export function Mermaid({ source, caption }: { source: string; caption?: string }) {
  const id = useId().replace(/:/g, "_");
  const [svg, setSvg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    setErr(null);
    setSvg(null);
    loadMermaid()
      .then((m) => m.render(`mermaid-${id}`, source))
      .then(({ svg }) => { if (!cancelled) setSvg(svg); })
      .catch((e) => { if (!cancelled) setErr(String(e)); });
    return () => { cancelled = true; };
  }, [id, source]);

  return (
    <figure style={{ margin: 0 }}>
      <div ref={containerRef} className="card" style={{ overflowX: "auto", background: "#fff" }}>
        {err && <pre style={{ color: "#cf222e", fontSize: 12 }}>{err}</pre>}
        {!err && !svg && <p className="muted" style={{ fontSize: 12 }}>rendering diagram…</p>}
        {svg && <div dangerouslySetInnerHTML={{ __html: svg }} />}
      </div>
      {caption && <figcaption className="muted" style={{ fontSize: 11, marginTop: 4, textAlign: "center" }}>{caption}</figcaption>}
    </figure>
  );
}
