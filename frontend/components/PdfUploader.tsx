"use client";

import { useRef, useState } from "react";
import { uploadDocument } from "@/lib/api";
import type { DocumentMeta } from "@/lib/types";

export function PdfUploader({
  onUploaded,
  multiple = true,
}: {
  onUploaded: (doc: DocumentMeta) => void;
  multiple?: boolean;
}) {
  const ref = useRef<HTMLInputElement | null>(null);
  const [queue, setQueue] = useState<{ name: string; status: "queued" | "uploading" | "done" | "error"; error?: string }[]>([]);
  const [busy, setBusy] = useState(false);

  async function pick() {
    const files = Array.from(ref.current?.files ?? []);
    if (files.length === 0) return;
    setBusy(true);
    setQueue(files.map((f) => ({ name: f.name, status: "queued" })));
    for (let i = 0; i < files.length; i++) {
      setQueue((q) => q.map((item, idx) => (idx === i ? { ...item, status: "uploading" } : item)));
      try {
        const doc = await uploadDocument(files[i]);
        onUploaded(doc);
        setQueue((q) => q.map((item, idx) => (idx === i ? { ...item, status: "done" } : item)));
      } catch (e) {
        setQueue((q) =>
          q.map((item, idx) =>
            idx === i ? { ...item, status: "error", error: String(e) } : item,
          ),
        );
      }
    }
    setBusy(false);
    if (ref.current) ref.current.value = "";
  }

  return (
    <div>
      <div className="row">
        <input
          ref={ref}
          type="file"
          accept="application/pdf"
          multiple={multiple}
          onChange={pick}
          disabled={busy}
        />
        {busy && <span className="muted">uploading {queue.filter((q) => q.status === "uploading" || q.status === "queued").length} left…</span>}
      </div>
      {queue.length > 0 && (
        <ul style={{ marginTop: 6, paddingLeft: 18, fontSize: 11 }}>
          {queue.map((item, i) => (
            <li key={i} style={{ color: item.status === "error" ? "#cf222e" : item.status === "done" ? "#1a7f37" : undefined }}>
              {item.name} · <strong>{item.status}</strong>
              {item.error ? ` · ${item.error}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
