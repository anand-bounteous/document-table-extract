"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export function ZoomableImage({
  src, alt, onClose, caption,
}: {
  src: string; alt: string; onClose: () => void; caption?: string;
}) {
  const [scale, setScale] = useState(1);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const dragRef = useRef<{ x: number; y: number; px: number; py: number } | null>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "+" || e.key === "=") setScale((s) => Math.min(s * 1.25, 8));
      if (e.key === "-") setScale((s) => Math.max(s / 1.25, 0.25));
      if (e.key === "0") { setScale(1); setPos({ x: 0, y: 0 }); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    setScale((s) => Math.max(0.25, Math.min(8, s * factor)));
  }, []);

  function onMouseDown(e: React.MouseEvent) {
    dragRef.current = { x: e.clientX, y: e.clientY, px: pos.x, py: pos.y };
  }
  function onMouseMove(e: React.MouseEvent) {
    const d = dragRef.current;
    if (!d) return;
    setPos({ x: d.px + (e.clientX - d.x), y: d.py + (e.clientY - d.y) });
  }
  function onMouseUp() { dragRef.current = null; }

  return (
    <div
      role="dialog"
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)", zIndex: 1000,
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      }}
    >
      <div className="row" style={{ position: "absolute", top: 12, right: 12, gap: 8, zIndex: 1001 }} onClick={(e) => e.stopPropagation()}>
        <button className="btn" onClick={() => setScale((s) => Math.max(s / 1.25, 0.25))}>−</button>
        <span style={{ color: "white", minWidth: 64, textAlign: "center" }}>{(scale * 100).toFixed(0)}%</span>
        <button className="btn" onClick={() => setScale((s) => Math.min(s * 1.25, 8))}>+</button>
        <button className="btn" onClick={() => { setScale(1); setPos({ x: 0, y: 0 }); }}>fit</button>
        <button className="btn" onClick={onClose}>close</button>
      </div>
      {caption && (
        <div style={{ position: "absolute", top: 12, left: 12, color: "white", fontSize: 13, opacity: 0.85 }} onClick={(e) => e.stopPropagation()}>
          {caption}
        </div>
      )}
      <div
        onClick={(e) => e.stopPropagation()}
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
        style={{
          overflow: "hidden", width: "100%", height: "100%",
          display: "flex", alignItems: "center", justifyContent: "center",
          cursor: dragRef.current ? "grabbing" : "grab",
        }}
      >
        <img
          src={src}
          alt={alt}
          draggable={false}
          style={{
            transform: `translate(${pos.x}px, ${pos.y}px) scale(${scale})`,
            transformOrigin: "center center",
            transition: dragRef.current ? "none" : "transform 0.1s ease-out",
            maxWidth: "none", maxHeight: "none",
            userSelect: "none",
          }}
        />
      </div>
      <div style={{ position: "absolute", bottom: 8, color: "rgba(255,255,255,0.5)", fontSize: 11 }}>
        scroll to zoom · drag to pan · keys: +/- 0 · esc to close
      </div>
    </div>
  );
}
