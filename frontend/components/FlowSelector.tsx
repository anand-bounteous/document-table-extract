"use client";

export interface FlowSelection {
  current: boolean;
  pii_v2: boolean;
}

export function FlowSelector({
  value,
  onChange,
}: {
  value: FlowSelection;
  onChange: (next: FlowSelection) => void;
}) {
  const noneSelected = !value.current && !value.pii_v2;
  return (
    <div
      style={{
        marginTop: 16,
        padding: "12px 14px",
        border: "1px solid var(--border)",
        borderRadius: 8,
        background: "#fbfbfd",
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 13 }}>
        Pick at least one flow
      </div>
      <label className="row" style={{ gap: 8, alignItems: "flex-start", marginBottom: 6 }}>
        <input
          type="checkbox"
          checked={value.current}
          onChange={(e) => onChange({ ...value, current: e.target.checked })}
        />
        <div>
          <div style={{ fontSize: 13 }}><strong>OCR + Table + current PII</strong></div>
          <div className="muted" style={{ fontSize: 11 }}>
            The existing pipeline. Runs the solutions you pick in §2 below. Embedded
            PresidioPII stage masks PII on each page.
          </div>
        </div>
      </label>
      <label className="row" style={{ gap: 8, alignItems: "flex-start" }}>
        <input
          type="checkbox"
          checked={value.pii_v2}
          onChange={(e) => onChange({ ...value, pii_v2: e.target.checked })}
        />
        <div>
          <div style={{ fontSize: 13 }}><strong>New PII Benchmark</strong></div>
          <div className="muted" style={{ fontSize: 11 }}>
            Independent UK-banking PII detection POC. Runs every baseline text
            producer (PyMuPDF, pdfplumber, Tesseract, EasyOCR, DocTR, TrOCR,
            PaddleOCR) and feeds each output through the configured detectors
            (Presidio regex, spaCy NER, …). Results render in <code>/pii-benchmarks/&lt;id&gt;</code>.
          </div>
        </div>
      </label>
      {noneSelected && (
        <div style={{ color: "#cf222e", fontSize: 11, marginTop: 6 }}>
          Select at least one flow to enable Run.
        </div>
      )}
    </div>
  );
}
