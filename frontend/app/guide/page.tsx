"use client";

import Link from "next/link";
import { SOLUTION_DOCS } from "@/lib/solutionDocs";
import { Mermaid } from "@/components/Mermaid";

export default function GuidePage() {
  return (
    <main className="container">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1 style={{ marginBottom: 4 }}>User guide</h1>
        <Link href="/" className="muted">← back to home</Link>
      </div>
      <p className="muted">
        How the harness works, when to pick which scenario, what to expect, and how to read the comparison.
      </p>

      <nav className="card" style={{ marginTop: 12 }}>
        <strong>Contents</strong>
        <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
          <li><a href="#setup">Setup &amp; prerequisites</a></li>
          <li><a href="#walkthrough">How to run a comparison</a></li>
          <li><a href="#scenarios">The scenarios</a> (
            {Object.keys(SOLUTION_DOCS).map((k, i, all) => (
              <span key={k}><a href={`#sol-${k}`}><code>{k}</code></a>{i < all.length - 1 ? ", " : ""}</span>
            ))}
            )
          </li>
          <li><a href="#bpmn">BPMN execution flow</a></li>
          <li><a href="#interpret">Interpreting results</a></li>
          <li><a href="#review">Acceptance &amp; review</a></li>
          <li><a href="#risk">Risk register</a></li>
        </ul>
      </nav>

      <section id="setup" style={{ marginTop: 18 }}>
        <h2>Setup &amp; prerequisites</h2>
        <p>
          Two processes: <code>backend</code> (FastAPI + uvicorn) and <code>frontend</code> (Next.js).
          Most setup costs land on the backend — system tools, optional pip groups, and first-run
          ML model downloads. The full setup runbook lives at <code>SETUP.md</code> in the repo root.
        </p>
        <ol>
          <li><strong>System tools</strong>: <code>brew install tesseract poppler ghostscript openjdk pango cairo libffi</code></li>
          <li><strong>Backend venv</strong>: <code>cd backend &amp;&amp; python3.12 -m venv .venv &amp;&amp; .venv/bin/pip install -e .</code></li>
          <li><strong>spaCy model</strong>: <code>.venv/bin/python -m spacy download en_core_web_lg</code></li>
          <li><strong>Phase-2 extras</strong>: <code>pip install -e ".[phase2-light]"</code> for img2table + tables-vector; add <code>".[ocr-easy]"</code> (EasyOCR + PyTorch), <code>".[ocr-doctr]"</code> (DocTR + PyTorch), <code>".[ocr-paddle]"</code> (PaddleOCR), <code>".[docling]"</code> as needed. For PaddleOCR also run <code>pip install "paddlex[ocr]==&lt;version&gt;"</code> (see SETUP.md §2b).</li>
          <li><strong>.env</strong>: copy <code>backend/.env.example</code> → <code>.env</code>, set <code>ANTHROPIC_API_KEY</code> (Claude Vision), <code>OPENAI_API_KEY</code> (OpenAI Vision), <code>GOOGLE_API_KEY</code> (Gemini Vision), and <code>PII_MASK_KEY</code> (Fernet-encrypted token map)</li>
          <li><strong>Run</strong>: <code>uvicorn app.main:app --port 8002</code> + <code>cd frontend &amp;&amp; npm run dev</code></li>
        </ol>
      </section>

      <section id="walkthrough" style={{ marginTop: 18 }}>
        <h2>How to run a comparison</h2>
        <ol>
          <li>Pick a PDF from the homepage table (or upload one).</li>
          <li>Toggle the solutions you want to run — use the chip row above the cards for fast multi-select.</li>
          <li>Click <strong>Run</strong>. You're taken to the run page; cards appear immediately with status pills (<em>Pending → Processing → Completed</em>).</li>
          <li>While solutions are running, click <em>Details</em> on any card to read its long description, flow diagram, and what to expect from it.</li>
          <li>When a solution finishes, hover regions on the annotated image to see text + confidence + tool. Click the image for a zoom modal.</li>
          <li>For each page, accept the best solution per <em>category</em> (Tables / Text / PII / Layout) on each card. The benchmark page composes the accepted parts into a final per-document output.</li>
        </ol>
      </section>

      <section id="scenarios" style={{ marginTop: 18 }}>
        <h2>The scenarios</h2>
        <p className="muted">Nineteen solutions are wired in. Each is independent and opt-in.</p>
        {Object.entries(SOLUTION_DOCS).map(([key, doc]) => (
          <article key={key} id={`sol-${key}`} className="card" style={{ marginTop: 12 }}>
            <h3 style={{ marginTop: 0 }}>
              <code>{key}</code> — {doc.display_name}
            </h3>
            <p>{doc.long_description}</p>
            <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10 }}>
              <div>
                <strong>Prerequisites</strong>
                <ul style={{ margin: "4px 0 0 18px", padding: 0 }}>
                  {doc.prerequisites.map((p, i) => <li key={i} style={{ fontSize: 12 }} dangerouslySetInnerHTML={{ __html: renderInlineCode(p) }} />)}
                </ul>
              </div>
              <div>
                <strong>Good at</strong>
                <ul style={{ margin: "4px 0 0 18px", padding: 0 }}>
                  {doc.good_at.map((p, i) => <li key={i} style={{ fontSize: 12 }}>{p}</li>)}
                </ul>
              </div>
              <div>
                <strong>Weak at</strong>
                <ul style={{ margin: "4px 0 0 18px", padding: 0 }}>
                  {doc.weak_at.map((p, i) => <li key={i} style={{ fontSize: 12 }}>{p}</li>)}
                </ul>
              </div>
            </div>
            <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
              <Mermaid source={doc.mermaid_flow} caption="Stage flow" />
              <Mermaid source={doc.mermaid_sequence} caption="Sequence" />
            </div>
            <div style={{ marginTop: 8 }}>
              <strong>How to read its results</strong>
              <p style={{ fontSize: 13, marginTop: 4 }} dangerouslySetInnerHTML={{ __html: renderInlineCode(doc.interpretation) }} />
            </div>
          </article>
        ))}
      </section>

      <section id="bpmn" style={{ marginTop: 18 }}>
        <h2>BPMN execution flow</h2>
        <p style={{ fontSize: 13 }}>
          Each solution's pipeline is defined as a BPMN 2.0 process diagram (editable in Camunda Modeler)
          stored at <code>backend/app/bpmn/&lt;solution&gt;.bpmn</code>.
        </p>
        <p style={{ fontSize: 13 }}>
          On the run page, expand <strong>"Execution flow (BPMN)"</strong> on any solution card to see its
          pipeline diagram with stages coloured by status: green = done, red = error, blue = running, amber = pending.
        </p>
        <p style={{ fontSize: 13 }}>
          The <strong>Pipeline overview</strong> tab on the run page shows all solutions on the master diagram.
          Completed paths are highlighted green; gateway nodes show which solutions took which branch.
          Click any task or gateway to open the inspector panel on the right.
        </p>
        <p style={{ fontSize: 13 }}>
          The master diagram uses <strong>inclusive gateways</strong> at each pipeline fork (OCR, table-detection,
          vision). An inclusive gateway fires all outgoing paths that have active tokens — meaning multiple
          solutions can traverse different branches simultaneously.
        </p>
        <p style={{ fontSize: 13 }}>
          SpiffWorkflow (BPMN engine) drives actual execution: each stage maps to a <code>bpmn:task</code> element
          whose <code>id</code> matches the stage name. After each stage the run is checkpointed to{" "}
          <code>storage/workflows.db</code> (SQLite). To inspect:{" "}
          <code>sqlite3 storage/workflows.db "SELECT solution, status FROM workflow_runs ORDER BY started_at DESC LIMIT 20;"</code>
        </p>
        <p style={{ fontSize: 13 }}>
          To regenerate BPMN files after adding a new solution:{" "}
          <code>cd backend &amp;&amp; .venv/bin/python -m app.bpmn.generator</code>
        </p>
      </section>

      <section id="interpret" style={{ marginTop: 18 }}>
        <h2>Interpreting results</h2>
        <h3>Region types</h3>
        <p>The harness normalizes every solution's output into a common set of <code>RegionType</code>s:</p>
        <ul style={{ margin: "4px 0 0 18px", padding: 0, fontSize: 13 }}>
          <li><code>normal_text</code> — line-level text region</li>
          <li><code>table</code>, <code>table_header</code>, <code>table_row</code>, <code>table_cell</code> — table structure</li>
          <li><code>logo</code>, <code>seal</code>, <code>watermark</code>, <code>handwriting_signature</code>, <code>image</code> — non-text content</li>
          <li><code>kv_pair</code> — labelled key/value snippet (account number, balance, dates)</li>
          <li><code>unknown</code> — falls through when the source tool's label doesn't map</li>
        </ul>
        <h3 style={{ marginTop: 12 }}>Confidence</h3>
        <p style={{ fontSize: 13 }}>
          A <em>within-solution</em> quality signal — never a cross-solution ranker. tesseract uses
          length-weighted word confidence; paddle/easyocr use native 0–1 scores; Claude uses its own
          self-reported per-field confidence; img2table uses structural cell-fill ratio as a proxy.
          Compare confidences across solutions using the benchmark harness (per-metric ground truth),
          not the raw number.
        </p>
        <h3 style={{ marginTop: 12 }}>PII annotation</h3>
        <p style={{ fontSize: 13 }}>
          The Presidio stage runs after OCR/Vision so detection is fair across solutions. Spans are
          masked (e.g. <code>****1234</code>, <code>[PERSON]</code>), and the original values are
          Fernet-encrypted at rest. Universal masking: once a value is detected anywhere, all other
          occurrences across pages are masked too. A red-tinted <code>page-NNN-masked.png</code>
          artifact is always written.
        </p>
        <h3 style={{ marginTop: 12 }}>Solution lifecycle</h3>
        <ul style={{ margin: "4px 0 0 18px", padding: 0, fontSize: 13 }}>
          <li><strong>Pending</strong> — queued, hasn't started</li>
          <li><strong>Processing</strong> — running (animated pulse dot)</li>
          <li><strong>Completed</strong> — done; results populated</li>
          <li><strong>Error</strong> — crashed; check the <em>log</em> link on the card</li>
          <li><strong>Skipped</strong> — solution doesn't support this PDF kind (e.g. Camelot on a scanned PDF)</li>
        </ul>
      </section>

      <section id="review" style={{ marginTop: 18 }}>
        <h2>Acceptance &amp; review</h2>
        <p style={{ fontSize: 13 }}>
          Each page can have a different solution accepted per category:
          <strong> Tables</strong>, <strong>Text</strong>, <strong>PII</strong>, <strong>Layout</strong>.
          The benchmark page composes the accepted parts into a final result per page —
          tables from the tables-winner, text regions from the text-winner, PII from the PII-winner,
          layout from the layout-winner.
        </p>
        <p style={{ fontSize: 13 }}>
          Use the per-category pills on each solution card on the run page. Empty pill = no accept
          for that category. Click again to revoke.
        </p>
      </section>

      <section id="risk" style={{ marginTop: 18 }}>
        <h2>Risk register</h2>
        <table>
          <thead><tr><th>Symptom</th><th>Cause</th><th>Fix</th></tr></thead>
          <tbody>
            <tr>
              <td><code>ModuleNotFoundError: camelot/tabula/docling</code></td>
              <td>optional extra not installed</td>
              <td><code>pip install -e ".[tables-vector]"</code> etc.</td>
            </tr>
            <tr>
              <td><code>gs: command not found</code> from Camelot</td>
              <td>Ghostscript missing</td>
              <td><code>brew install ghostscript</code></td>
            </tr>
            <tr>
              <td><code>worker ... exited -9 (SIGKILL)</code></td>
              <td>OOM killer — solution loaded too much RAM</td>
              <td>Close other apps, or disable optional heavy submodels on the stage</td>
            </tr>
            <tr>
              <td><code>worker ... exited -5 (SIGTRAP)</code></td>
              <td>Native thread-pool contention on Apple Silicon</td>
              <td>The paddle stage already pins OMP/MKL/OpenBLAS to 1 thread</td>
            </tr>
            <tr>
              <td><code>CERTIFICATE_VERIFY_FAILED</code> during model download</td>
              <td>certifi bundle missing a root brew's OpenSSL trusts</td>
              <td>The heavy-ML stages already export <code>SSL_CERT_FILE</code> at the brew bundle</td>
            </tr>
            <tr>
              <td><code>Cannot convert MPS Tensor to float64</code></td>
              <td>docling hits a float64 op MPS doesn't implement</td>
              <td>The docling stage already forces <code>AcceleratorDevice.CPU</code></td>
            </tr>
            <tr>
              <td><code>JSONDecodeError</code> from <code>vision_claude</code></td>
              <td>Claude emitted unescaped quotes or got truncated</td>
              <td>Parser auto-heals via <code>json-repair</code>; if it still fails, raise <code>ANTHROPIC_MAX_TOKENS</code></td>
            </tr>
            <tr>
              <td><code>ModuleNotFoundError: img2table</code></td>
              <td><code>[tables-img]</code> not installed</td>
              <td><code>pip install -e ".[tables-img]"</code></td>
            </tr>
            <tr>
              <td><code>ModuleNotFoundError: easyocr</code></td>
              <td><code>[ocr-easy]</code> not installed</td>
              <td><code>pip install -e ".[ocr-easy]"</code></td>
            </tr>
            <tr>
              <td><code>ModuleNotFoundError: doctr</code></td>
              <td><code>[ocr-doctr]</code> not installed</td>
              <td><code>pip install -e ".[ocr-doctr]"</code></td>
            </tr>
            <tr>
              <td><code>A dependency error occurred during pipeline creation</code> (Paddle)</td>
              <td><code>paddlex[ocr]</code> extras missing</td>
              <td><code>pip install "paddlex[ocr]==&lt;version&gt;"</code> (see SETUP.md §2b)</td>
            </tr>
            <tr>
              <td><code>paddle_structure</code> stuck in "processing" for &gt;10 min</td>
              <td>server-tier models running on CPU at ~1 fps</td>
              <td>Expected; timeout is 10 min. GPU dramatically speeds it up.</td>
            </tr>
            <tr>
              <td><code>worker exited -9 (SIGKILL — OOM killer)</code> on img2table_paddle</td>
              <td>paddle mobile models + img2table exhaust RAM</td>
              <td>Close other apps and retry</td>
            </tr>
          </tbody>
        </table>
      </section>
    </main>
  );
}

function renderInlineCode(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}
