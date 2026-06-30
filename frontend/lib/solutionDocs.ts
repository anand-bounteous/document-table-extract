// Per-solution long-form documentation: prerequisites, when-to-use, flow + sequence
// diagrams (Mermaid source), interpretation guide. Consumed by the per-solution
// detail page and the /guide route.

export interface SolutionDoc {
  display_name: string;
  long_description: string;
  prerequisites: string[];
  good_at: string[];
  weak_at: string[];
  mermaid_flow: string;
  mermaid_sequence: string;
  interpretation: string;
}

export const SOLUTION_DOCS: Record<string, SolutionDoc> = {
  ocr_tesseract_baseline: {
    display_name: "Tesseract baseline",
    long_description:
      "Raw tesseract OCR over each rasterized page. Word-level bboxes from `image_to_data` are grouped into line-level regions by tesseract's block/par/line ids. No preprocessing, no table reconstruction — this is the floor of the harness, the simplest meaningful pipeline.",
    prerequisites: ["`brew install tesseract` on the system PATH", "no pip extras"],
    good_at: ["clean printed text on light backgrounds", "fast (~1.5 s/page)", "no external services"],
    weak_at: ["ruled tables (every cell becomes its own region)", "low-contrast scans", "rotated text"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[tesseract image_to_data]
  B --> C[group words → lines by block_num/par_num/line_num]
  C --> D[Presidio PII pass]
  D --> E[annotate render]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant T as TesseractOCR
  participant P as PresidioPII
  participant A as AnnotatePage
  R->>T: run(ctx, state)
  T->>T: image_to_data per page
  T-->>R: regions populated
  R->>P: run(ctx, state)
  P-->>R: pii spans + masked images
  R->>A: run(ctx, state)
  A-->>R: annotated PNGs as artifacts`,
    interpretation:
      "Expect dozens of line-level `normal_text` regions per page, **zero** `table` regions, and per-region confidence equal to the length-weighted mean of word confidences. Use this as the floor when comparing other solutions — anything that doesn't beat the baseline on text accuracy isn't worth the extra dependencies.",
  },

  opencv_tesseract: {
    display_name: "OpenCV → Tesseract → ruled tables",
    long_description:
      "Adds an OpenCV preprocessing pass before tesseract: deskew via min-area-rectangle on the inverted page, fast non-local-means denoise, adaptive Gaussian threshold, and horizontal + vertical morphological line detection. The detected line grid is converted to ruled-cell bboxes, then tesseract OCR runs on the cleaned binary image, and a final stage reconstructs `TableModel`s from the grid + text overlap.",
    prerequisites: ["`brew install tesseract`", "`opencv-python` (already in core deps)"],
    good_at: ["ruled bank-statement tables", "skewed scans", "low-contrast pages where adaptive thresholding wins"],
    weak_at: ["borderless / whitespace-separated tables", "multiline cells (each line becomes its own row)"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[OpenCV deskew]
  B --> C[denoise + adaptive threshold]
  C --> D[ruled-line detection]
  D --> E[grid → cell bboxes]
  E --> F[tesseract OCR on preprocessed]
  F --> G[layout_ruled_table: text ∩ cells]
  G --> H[Presidio PII]
  H --> I[annotate render]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant O as OpenCVPreprocess
  participant T as TesseractOCR
  participant L as RuledTableFromOpenCV
  R->>O: deskew, denoise, threshold, line-detect
  O-->>R: state.extras.ruled_cells per page
  R->>T: OCR with use_preprocessed=True
  T-->>R: regions
  R->>L: build TableModel per page
  L-->>R: tables populated`,
    interpretation:
      "Look for **`table` regions with `border_mode=\"ruled\"`** and `n_rows × n_cols` that matches what you see visually. If you see lots of text regions but no tables, the page didn't have detectable lines and the line-grid stage produced nothing.",
  },

  claude_vision: {
    display_name: "Claude Vision (structured)",
    long_description:
      "Tesseract runs first to seed PII detection, Presidio redacts the image (black boxes over every detected span), then Claude Vision is sent the redacted page with a strict JSON-output prompt asking for regions + tables + reading-order text. The response is parsed with `json-repair` to tolerate the usual LLM JSON failure modes.",
    prerequisites: [
      "`ANTHROPIC_API_KEY` set in `.env`",
      "`PII_MASK_KEY` set if you want the token map Fernet-encrypted at rest",
      "outbound HTTPS to `api.anthropic.com`",
    ],
    good_at: ["whitespace-separated tables", "multiline cells with newlines preserved", "logos / signatures / seals / watermarks tagged as their own region type"],
    weak_at: ["high per-page latency (~30–90 s)", "API cost", "tabular data with thousands of rows (max-tokens truncation)"],
    mermaid_flow: `flowchart LR
  A[PDF page raster @200 DPI] --> B[Tesseract OCR seed]
  B --> C[Presidio PII detect]
  C --> D[Redact PII spans on image]
  D --> E[Claude Vision call]
  E --> F[json-repair → regions + tables]
  F --> G[annotate render]`,
    mermaid_sequence: `sequenceDiagram
  participant W as ClaudeVision worker
  participant C as Claude API
  W->>W: load redacted PNG + base64
  W->>C: messages.create(model, image, prompt)
  C-->>W: text block with JSON body
  W->>W: strip fences, json_repair, parse
  W->>W: map → Region + TableModel`,
    interpretation:
      "Expect high recall: logos, signatures, watermarks, seals, and multiline cells all surface as their own regions. **Confidence is Claude's self-reported per-field score**, not a tesseract-style mean. The `vision/page-NNN-raw.txt` artifact captures the raw model output before parsing — inspect it if structure looks wrong.",
  },

  img2table: {
    display_name: "img2table (bordered + borderless)",
    long_description:
      "Tesseract OCR for word-level text, then img2table detects bordered AND borderless tables on the rasterized page using its own line/whitespace heuristics. Cells inherit the bbox from img2table's grid and pull text from the tesseract pass. Subprocess-isolated.",
    prerequisites: ["`pip install -e \".[tables-img]\"`", "`brew install tesseract`"],
    good_at: ["mixed bordered + borderless tables in one document", "fast (~1–6 s/page)", "stable on Apple Silicon"],
    weak_at: ["multi-column document layouts where img2table merges columns", "tables with thin/inconsistent borders"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[Tesseract: text regions]
  B --> C[img2table subprocess]
  C --> D[detect bordered tables]
  C --> E[detect borderless tables]
  D --> F[grid → TableModel]
  E --> F
  F --> G[Presidio PII]
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant S as SubprocessStage
  participant W as img2table worker
  R->>S: build_payload (page paths, dpi)
  S->>W: spawn python -m app.workers.img2table_worker
  W->>W: Image(src=png).extract_tables(ocr=Tesseract)
  W-->>S: JSON {pages, regions, tables}
  S-->>R: merge into RunState`,
    interpretation:
      "Look at `border_mode=\"mixed\"` tables and the per-cell `multiline` flag. img2table doesn't expose a single confidence — we approximate by cell-fill ratio, so a low confidence usually means a sparse table.",
  },

  camelot_vector: {
    display_name: "Camelot (vector tables)",
    long_description:
      "Camelot reads the original PDF (not a raster) and emits tables in both lattice (ruled) and stream (whitespace) flavors. Coordinates are in PDF points, bottom-left origin, so the worker converts to image pixels at the run DPI before emitting. **Vector PDFs only** — gated by `supported_kinds`.",
    prerequisites: [
      "`pip install -e \".[tables-vector]\"`",
      "`brew install ghostscript` (Camelot raster-renders pages internally)",
    ],
    good_at: ["high-fidelity vector PDFs", "structured invoices / statements with clean table grids"],
    weak_at: ["scanned PDFs (skipped automatically)", "pages where ghostscript fails to rasterize"],
    mermaid_flow: `flowchart LR
  A[PDF path] --> B[Camelot lattice]
  A --> C[Camelot stream]
  B --> D[per-table df + bbox in PDF pts]
  C --> D
  D --> E[convert pts → image_px@dpi, flip Y]
  E --> F[TableModel per flavor]
  F --> G[Presidio PII]
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant W as Camelot worker
  participant GS as Ghostscript
  R->>W: pdf_path, pages
  W->>GS: raster preview internally
  W->>W: lattice + stream per page
  W-->>R: pages.tables with both flavors`,
    interpretation:
      "You'll see TWO tables per real table — once with `border_mode=\"ruled\"` (lattice) and once with `\"whitespace\"` (stream). The `accuracy` attribute in `attributes` is camelot's own quality estimate; trust the higher-accuracy flavor.",
  },

  tabula_vector: {
    display_name: "Tabula (vector tables)",
    long_description:
      "Tabula (Java-backed via tabula-py) extracts vector-PDF tables in lattice and stream modes. Returns Pandas DataFrames; cells inherit row/col indices from the DataFrame shape. **Vector PDFs only**.",
    prerequisites: ["`pip install -e \".[tables-vector]\"`", "`brew install openjdk` and `JAVA_HOME` exported"],
    good_at: ["clean vector tables where Camelot misses (different parser heuristics)", "JVM is already on most data-eng machines"],
    weak_at: ["per-call JVM startup latency", "no bbox info on cells (we only emit row/col)"],
    mermaid_flow: `flowchart LR
  A[PDF path] --> B[tabula-py read_pdf lattice]
  A --> C[tabula-py read_pdf stream]
  B --> D[DataFrame per table]
  C --> D
  D --> E[map to TableModel rows/cols]
  E --> F[Presidio PII]
  F --> G[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant W as Tabula worker
  participant J as JVM
  R->>W: pdf_path, pages
  W->>J: spawn java reading PDF
  J-->>W: DataFrames per table
  W-->>R: TableModel rows/cols (no bbox)`,
    interpretation:
      "Cells have no `bbox` (only `row`/`col`), so you won't see per-cell highlights in the annotated image. Compare row/col counts and text content against Camelot for the same page.",
  },

  paddle_structure: {
    display_name: "PaddleOCR PP-Structure",
    long_description:
      "PaddleOCR's PP-StructureV3 pipeline: layout detection + table recognition + per-region OCR in one pass. The stage pins every native thread library to 1 to avoid SIGTRAP / SIGABRT on Apple Silicon and disables formula/seal/chart/region detection by default to keep the model footprint under ~1 GB.",
    prerequisites: [
      "`pip install -e \".[ocr-paddle]\"`",
      "Outbound HTTPS to `paddlepaddle.org.cn` + `huggingface.co` for first-run model downloads (~500 MB)",
      "8 GB+ free RAM during the run",
    ],
    good_at: ["whitespace tables with multiline cells", "mixed-language documents"],
    weak_at: ["first-run model download fails on restricted networks", "high memory pressure on small Macs"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[PP-StructureV3 pipeline]
  B --> C[layout detect: blocks + types]
  B --> D[table recognition: rows + cells]
  B --> E[per-block OCR]
  C --> F[regions]
  D --> F
  E --> F
  F --> G[Presidio PII]
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant W as Paddle worker
  participant P as PPStructureV3
  W->>P: predict(image_path)
  P-->>W: parsing results
  W->>W: walk JSON for labeled bboxes
  W-->>W: emit Region + TableModel per block`,
    interpretation:
      "Look at the distribution of `RegionType` values — paddle classifies into `kv_pair`, `normal_text`, `table`, `image`, `seal`, etc. The block-level `pp_type` is preserved in `attributes` for debugging.",
  },

  docling: {
    display_name: "docling · EasyOCR (default)",
    long_description:
      "IBM's docling converter: layout, tables, and reading order in one pipeline. Output is a `DoclingDocument` with bboxes in PDF points; the worker converts to image pixels. Forced to `AcceleratorDevice.CPU` because docling's models touch float64 ops that Apple's MPS backend doesn't implement. **OCR backend: EasyOCR** (docling's default) — used to recognise text in pixel regions that aren't extractable as native PDF text. Each region carries `attributes.ocr_backend` so you can confirm which engine fed the text.",
    prerequisites: [
      "`pip install -e \".[docling]\"`",
      "Outbound HTTPS to Hugging Face + `modelscope.cn` for first-run downloads (~1.5 GB)",
      "`SSL_CERT_FILE` pointing at brew's OpenSSL bundle (auto-set by the stage)",
    ],
    good_at: ["preserving reading order across multi-column layouts", "structured tables with row/col spans"],
    weak_at: ["~15–30 s/page on CPU", "first-run latency (downloads + model warm-up)"],
    mermaid_flow: `flowchart LR
  A[PDF path] --> B[docling DocumentConverter]
  B --> C[layout + reading order]
  B --> D[table recognition]
  B -. needs OCR? .-> O[EasyOCR backend]
  O --> C
  C --> E[regions w/ docling labels + ocr_backend]
  D --> F[TableModel w/ row/col spans]
  E --> G[Presidio PII]
  F --> G
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant W as Docling worker
  participant D as DocumentConverter
  participant O as EasyOCR backend
  W->>D: convert(pdf_path, ocr_options=EasyOcrOptions)
  D->>O: OCR pixel regions
  O-->>D: text + confidence
  D-->>W: DoclingDocument
  W->>W: iterate_items() → regions
  W->>W: ddoc.tables → TableModel grid
  W-->>W: stamp ocr_backend on attributes`,
    interpretation:
      "Each region carries `attributes.docling_label` (`section_header`, `paragraph`, `picture`, etc.) AND `attributes.ocr_backend` so the card can show which OCR engine produced the text. Reading order is preserved in `full_text` — useful when comparing against Claude's reading order. To compare OCR engines under docling's layout pipeline, pair this card with `docling_tesseract` / `docling_rapidocr` on the same document.",
  },

  docling_tesseract: {
    display_name: "docling · Tesseract",
    long_description:
      "Same docling layout/tables/reading-order pipeline as the default `docling` solution, but configured with `TesseractCliOcrOptions` so the OCR backend is classical Tesseract instead of deep-learning EasyOCR. Useful when EasyOCR's torch deps aren't installed or to compare Tesseract's recognition against EasyOCR's under an identical layout pipeline.",
    prerequisites: [
      "`pip install -e \".[docling]\"`",
      "`tesseract` binary on PATH (`brew install tesseract` / `apt install tesseract-ocr`)",
      "Outbound HTTPS for docling's first-run layout/table model downloads",
    ],
    good_at: ["printed text without GPU deps", "machine-comparable to standalone `ocr_tesseract_baseline`"],
    weak_at: ["handwritten / low-quality scans (vs. EasyOCR / TrOCR)", "rotated text", "non-Latin scripts (without extra lang packs)"],
    mermaid_flow: `flowchart LR
  A[PDF path] --> B[docling DocumentConverter]
  B --> C[layout + reading order]
  B --> D[table recognition]
  B -. needs OCR? .-> O[Tesseract CLI]
  O --> C
  C --> E[regions w/ ocr_backend=tesseract_cli]
  D --> F[TableModel w/ row/col spans]
  E --> G[Presidio PII]
  F --> G
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant W as Docling worker
  participant D as DocumentConverter
  participant T as Tesseract CLI
  W->>D: convert(pdf_path, ocr_options=TesseractCliOcrOptions)
  D->>T: shell out per pixel region
  T-->>D: text + confidence
  D-->>W: DoclingDocument
  W-->>W: stamp ocr_backend on attributes`,
    interpretation:
      "Compare side-by-side against `docling` (EasyOCR) to isolate the OCR-engine variable from docling's layout/table-structure variables. Differences between the two cards on the same document are purely OCR-engine differences.",
  },

  docling_rapidocr: {
    display_name: "docling · RapidOCR",
    long_description:
      "Same docling layout/tables/reading-order pipeline, swapped to `RapidOcrOptions` for OCR. RapidOCR is a lightweight ONNX-based PaddleOCR derivative — no torch dependency, smaller models, CPU-friendly. Good middle ground between EasyOCR (heavy, accurate) and Tesseract (classical, fast).",
    prerequisites: [
      "`pip install -e \".[docling]\"`",
      "`pip install rapidocr_onnxruntime`",
      "Outbound HTTPS for docling's first-run layout/table model downloads",
    ],
    good_at: ["CPU-friendly OCR without torch", "fast cold start vs. EasyOCR", "printed Latin + CJK text"],
    weak_at: ["handwriting (vs. TrOCR-hw)", "very dense tables (recognition recall lower than PaddleOCR proper)"],
    mermaid_flow: `flowchart LR
  A[PDF path] --> B[docling DocumentConverter]
  B --> C[layout + reading order]
  B --> D[table recognition]
  B -. needs OCR? .-> O[RapidOCR ONNX]
  O --> C
  C --> E[regions w/ ocr_backend=rapidocr]
  D --> F[TableModel w/ row/col spans]
  E --> G[Presidio PII]
  F --> G
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant W as Docling worker
  participant D as DocumentConverter
  participant R as RapidOCR
  W->>D: convert(pdf_path, ocr_options=RapidOcrOptions)
  D->>R: ONNX inference per pixel region
  R-->>D: text + confidence
  D-->>W: DoclingDocument
  W-->>W: stamp ocr_backend on attributes`,
    interpretation:
      "Compare with `docling` (EasyOCR) and `docling_tesseract` to see how OCR-engine choice shifts both extraction recall and downstream PII detection — same layout, different recognition.",
  },

  docling_doctr: {
    display_name: "docling · DocTR (custom post-OCR)",
    long_description:
      "DocTR isn't shipped as a docling-native OCR backend, so we get it under docling by running docling with `do_ocr=False` and then **post-OCRing each text region's bbox crop** with `doctr.ocr_predictor`. The card shows what docling's layout pipeline plus DocTR text recognition would produce together. Region text is replaced entirely by DocTR's output; tables stay on docling's native cell extraction.",
    prerequisites: [
      "`pip install -e \".[docling]\"` (docling layout/table models)",
      "`pip install -e \".[ocr-doctr]\"` (DocTR + PyTorch)",
      "Outbound HTTPS for first-run model downloads of both pipelines (~1 GB combined)",
    ],
    good_at: [
      "documents where DocTR's CRNN/MASTER recogniser beats EasyOCR (mixed-density text, low-contrast scans)",
      "fair head-to-head with standalone `doctr_baseline` — same recogniser, different layout",
    ],
    weak_at: [
      "two cold-start model loads (docling layout + DocTR pipeline)",
      "~25–60 s/page on CPU because every region is re-OCRed after docling's pass",
    ],
    mermaid_flow: `flowchart LR
  A[PDF path] --> B[docling DocumentConverter\\n(do_ocr=False)]
  B --> C[layout + reading order]
  B --> D[table recognition]
  C --> E[regions w/ empty text]
  E --> P[post-OCR: crop bbox →\\ndoctr.ocr_predictor]
  P --> F[regions w/ DocTR text + ocr_backend=doctr]
  D --> G[TableModel (docling cells)]
  F --> H[Presidio PII]
  G --> H
  H --> I[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant W as Docling worker
  participant D as DocumentConverter
  participant P as DocTR pipeline
  W->>D: convert(pdf, do_ocr=False)
  D-->>W: DoclingDocument (layout only)
  loop every region
    W->>W: crop page raster to bbox
    W->>P: ocr_predictor([crop])
    P-->>W: words → lines → text
    W->>W: region.text = new_text
  end
  W-->>W: stamp ocr_backend=doctr`,
    interpretation:
      "Compare with `doctr_baseline` (DocTR's own layout + DocTR OCR) and `docling` (docling's layout + EasyOCR) to isolate which component drives observed differences — layout source or recogniser. `attributes.ocr_backend` is `doctr` on every region.",
  },

  docling_trocr_handwritten: {
    display_name: "docling · TrOCR (handwritten, custom post-OCR)",
    long_description:
      "Same custom post-OCR pattern as `docling_doctr` but using `microsoft/trocr-base-handwritten`. TrOCR is line-only, so the worker uses EasyOCR's text detector inside each region crop to find line bboxes first, then runs TrOCR per line. Targeted at documents where docling's layout is good but the text is handwritten — TrOCR-hw will recognise content that classical OCR engines drop.",
    prerequisites: [
      "`pip install -e \".[docling]\"`",
      "`pip install -e \".[ocr-easy]\"` (EasyOCR detector for line splitting)",
      "TrOCR runs under the existing `transformers` + `torch` stack already in the project",
    ],
    good_at: [
      "handwritten content inside printed-form layouts",
      "machine-comparable to standalone `trocr_handwritten` — same recogniser, different region source",
    ],
    weak_at: [
      "loads three pipelines (docling layout, EasyOCR detector, TrOCR recogniser) — heaviest cold start",
      "very slow on dense pages: TrOCR generates token-by-token per detected line",
    ],
    mermaid_flow: `flowchart LR
  A[PDF path] --> B[docling DocumentConverter\\n(do_ocr=False)]
  B --> C[layout + reading order]
  C --> E[regions w/ empty text]
  E --> P1[per region: EasyOCR detector\\non bbox crop → line boxes]
  P1 --> P2[per line: TrOCR recognise]
  P2 --> F[regions w/ TrOCR text +\\nocr_backend=trocr_handwritten]
  F --> H[Presidio PII] --> I[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant W as Docling worker
  participant D as DocumentConverter
  participant E as EasyOCR detector
  participant T as TrOCR (handwritten)
  W->>D: convert(pdf, do_ocr=False)
  D-->>W: DoclingDocument (layout only)
  loop every region
    W->>W: crop page raster to bbox
    W->>E: detect(crop) → line boxes
    loop every line
      W->>T: generate(line_crop)
      T-->>W: text
    end
    W->>W: region.text = join(lines)
  end
  W-->>W: stamp ocr_backend=trocr_handwritten`,
    interpretation:
      "Best paired with `docling` (EasyOCR baseline) and `trocr_handwritten` (standalone) for a 3-way comparison. Cells inside tables stay on docling's native extraction — TrOCR only rewrites region text. If a region has no detected lines (EasyOCR finds nothing), TrOCR is given the whole region crop as a single line.",
  },

  openai_vision: {
    display_name: "OpenAI Vision (structured)",
    long_description:
      "Same pipeline as claude_vision but uses the OpenAI API (gpt-4o or gpt-4o-mini). Tesseract seeds PII detection, Presidio redacts the image, then the redacted PNG is sent to OpenAI's vision endpoint with a structured-JSON extraction prompt. Response parsed with json-repair.",
    prerequisites: [
      "`OPENAI_API_KEY` set in `.env`",
      "outbound HTTPS to `api.openai.com`",
    ],
    good_at: ["whitespace-separated tables", "multiline cells", "comparison baseline against Claude"],
    weak_at: ["API cost", "~30–90 s/page latency", "max-tokens truncation on dense tables"],
    mermaid_flow: `flowchart LR
  A[PDF page raster @200 DPI] --> B[Tesseract OCR seed]
  B --> C[Presidio PII detect]
  C --> D[Redact PII spans on image]
  D --> E[OpenAI Vision call]
  E --> F[json-repair → regions + tables]
  F --> G[annotate render]`,
    mermaid_sequence: `sequenceDiagram
  participant W as OpenAIVision worker
  participant O as OpenAI API
  W->>W: load redacted PNG + base64
  W->>O: chat.completions.create(model, image, prompt)
  O-->>W: text block with JSON body
  W->>W: strip fences, json_repair, parse
  W->>W: map → Region + TableModel`,
    interpretation:
      "Same as claude_vision. Raw output in `vision/page-NNN-raw.txt`. Compare token costs and JSON quality against claude_vision using the LLM cost badge on each card.",
  },

  gemini_vision: {
    display_name: "Gemini Vision (structured)",
    long_description:
      "Same redact-then-vision pipeline but targets Google Gemini (gemini-2.5-pro or gemini-2.0-flash). The stage uses google-generativeai. Parsed with json-repair.",
    prerequisites: [
      "`GOOGLE_API_KEY` set in `.env`",
      "outbound HTTPS to `generativelanguage.googleapis.com`",
    ],
    good_at: ["same as claude/openai vision", "gemini-flash is notably cheaper"],
    weak_at: ["same latency/cost tradeoffs", "Gemini's JSON strictness varies by model version"],
    mermaid_flow: `flowchart LR
  A[PDF page raster @200 DPI] --> B[Tesseract OCR seed]
  B --> C[Presidio PII detect]
  C --> D[Redact PII spans on image]
  D --> E[Gemini Vision call]
  E --> F[json-repair → regions + tables]
  F --> G[annotate render]`,
    mermaid_sequence: `sequenceDiagram
  participant W as GeminiVision worker
  participant G as Google Gemini API
  W->>W: load redacted PNG + base64
  W->>G: generate_content(model, image, prompt)
  G-->>W: text block with JSON body
  W->>W: strip fences, json_repair, parse
  W->>W: map → Region + TableModel`,
    interpretation:
      "Same as claude_vision. Compare cost-per-page across all three LLM vision solutions using the cost badge.",
  },

  easyocr_baseline: {
    display_name: "EasyOCR baseline",
    long_description:
      "EasyOCR (deep-learning OCR) as a standalone solution. Reader runs on CPU with `gpu=False` (Apple Silicon compatible). Returns 4-point quad bounding boxes which are converted to axis-aligned x/y/w/h rectangles. Text and confidence come from EasyOCR's recognition network.",
    prerequisites: [
      "`pip install -e \".[ocr-easy]\"` — pulls PyTorch (~1 GB first time)",
    ],
    good_at: ["multilingual text", "printed text on complex backgrounds", "handles slight rotation"],
    weak_at: ["slower than tesseract (~5–15 s/page on CPU)", "no table detection"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[EasyOCR reader.readtext]
  B --> C[quad bbox → axis-aligned rect]
  C --> D[Region normal_text]
  D --> E[Presidio PII]
  E --> F[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant E as EasyOCR reader
  participant P as PresidioPII
  participant A as AnnotatePage
  R->>E: reader.readtext(image)
  E-->>R: [(quad_bbox, text, confidence)]
  R->>R: quad → x/y/w/h Region
  R->>P: run(ctx, state)
  P-->>R: pii spans + masked images
  R->>A: run(ctx, state)
  A-->>R: annotated PNGs`,
    interpretation:
      "Regions are all `normal_text`. Confidence is EasyOCR's recognition score (0–1). Compare text accuracy on noisy scans against the Tesseract baseline.",
  },

  paddleocr_baseline: {
    display_name: "PaddleOCR baseline",
    long_description:
      "Standalone PaddleOCR text detection + recognition (PP-OCRv4) as an independent baseline — no layout model, no table reconstruction. Quad polygon bboxes from the detector are converted to axis-aligned rectangles. Subprocess-isolated with the standard paddle thread-pin env so a native crash can't take down the API.",
    prerequisites: [
      "`pip install -e \".[ocr-paddle]\"` — pulls paddlepaddle + paddleocr (~600 MB)",
      "First-run model download from `paddlepaddle.org.cn` (~150 MB for PP-OCRv4)",
    ],
    good_at: ["multilingual text", "mixed-script documents", "comparable accuracy to easyocr/doctr"],
    weak_at: ["heavier than easyocr/doctr (paddle runtime overhead)", "no table structure detection", "first-run model download on restricted networks"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[PaddleOCR PP-OCRv4]
  B --> C[text detection: quad polygons]
  C --> D[text recognition per crop]
  D --> E[quad → axis-aligned rect]
  E --> F[Region normal_text]
  F --> G[Presidio PII]
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant S as SubprocessStage
  participant W as PaddleOCR worker
  R->>S: build_payload (page paths, dpi)
  S->>W: spawn python -m app.workers.paddleocr_worker
  W->>W: PaddleOCR().predict(image_path)
  W-->>S: JSON {pages, regions}
  S-->>R: merge into RunState`,
    interpretation:
      "Regions are all `normal_text`; confidence is paddle's recognition score (0–1). Compare against easyocr_baseline / doctr_baseline on the same page — paddle tends to win on Asian-script text but is slower to warm up.",
  },

  trocr_handwritten: {
    display_name: "TrOCR (handwritten)",
    long_description:
      "Microsoft TrOCR's `microsoft/trocr-base-handwritten` transformer for handwriting + signature recognition. TrOCR is recognition-only, so the stage reuses EasyOCR's line detector to find regions, then transcribes each crop. Output regions are tagged `handwriting_signature` so they surface under the Signatures panel in `FeatureRegionsPanel`. Subprocess-isolated; first-run downloads ~600 MB of HuggingFace weights.",
    prerequisites: [
      "`pip install -e \".[ocr-trocr]\"` — pulls transformers + easyocr + torch",
      "Outbound HTTPS to `huggingface.co` for first-run model download",
    ],
    good_at: ["handwritten text on forms / cheques / signatures", "complementary to printed-text OCR baselines"],
    weak_at: ["slow — TrOCR runs per line on CPU; ~5–10 s/page on Apple Silicon", "first-run model download (~600 MB)", "no table reconstruction (recognition only)"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[EasyOCR.detect: line boxes]
  B --> C[crop per line]
  C --> D[TrOCR handwritten]
  D --> E[Region handwriting_signature]
  E --> F[Presidio PII]
  F --> G[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant S as SubprocessStage
  participant W as TrOCR worker
  R->>S: build_payload (page paths, dpi, model_id)
  S->>W: spawn python -m app.workers.trocr_worker
  W->>W: easyocr.Reader.detect → boxes
  loop per line
    W->>W: crop + TrOCRProcessor + VisionEncoderDecoderModel.generate
  end
  W-->>S: JSON {pages, regions}
  S-->>R: merge into RunState`,
    interpretation:
      "Confidence is the mean argmax-token softmax over TrOCR's output. Regions show up under the Signatures bucket of the per-feature panel. Compare side-by-side with `trocr_printed` and any classical OCR baseline to spot handwritten content the others miss entirely.",
  },

  trocr_printed: {
    display_name: "TrOCR (printed)",
    long_description:
      "Same pipeline as `trocr_handwritten` but uses `microsoft/trocr-base-printed` and tags output as `normal_text` so results are directly comparable against Tesseract / EasyOCR / DocTR / PaddleOCR. Useful when you want a single transformer-recognized baseline that's not tied to a CRNN-style head.",
    prerequisites: [
      "`pip install -e \".[ocr-trocr]\"` — pulls transformers + easyocr + torch",
      "Outbound HTTPS to `huggingface.co` for first-run model download",
    ],
    good_at: ["transformer-quality printed-text recognition", "comparison baseline for handwritten card"],
    weak_at: ["slower than tesseract / easyocr", "first-run model download (~600 MB)", "no table reconstruction"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[EasyOCR.detect: line boxes]
  B --> C[crop per line]
  C --> D[TrOCR printed]
  D --> E[Region normal_text]
  E --> F[Presidio PII]
  F --> G[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant S as SubprocessStage
  participant W as TrOCR worker
  R->>S: build_payload (page paths, dpi, model_id)
  S->>W: spawn python -m app.workers.trocr_worker
  W->>W: easyocr.Reader.detect → boxes
  loop per line
    W->>W: crop + TrOCR printed model
  end
  W-->>S: JSON {pages, regions}
  S-->>R: merge into RunState`,
    interpretation:
      "Same shape as other OCR baselines (regions = `normal_text`). The transformer head reads cleaner cursive / italic / decorative fonts than tesseract but is meaningfully slower per page.",
  },

  layout_parser: {
    display_name: "Layout-Parser (PubLayNet)",
    long_description:
      "Layout-Parser with the Detectron2 PubLayNet backbone. Emits five layout classes — Text, Title, List, Table, Figure — and authoritatively sets the page-level `doc_format` label (tabular-heavy / form-like / narrative / image-heavy / mixed) from the area-weighted distribution. The Format pill appears in the card header for this card and for every other layout-emitting solution that runs the shared `DocFormatStage`. Subprocess-isolated.",
    prerequisites: [
      "`pip install -e \".[layout-parser]\"`",
      "Detectron2 install — Apple Silicon needs a per-platform wheel; see SETUP.md",
      "First-run model download from layoutparser's Dropbox mirror (~250 MB)",
    ],
    good_at: ["modern English business docs (statements, invoices, reports)", "clean structural decomposition with score thresholding", "authoritative doc-format labeling"],
    weak_at: ["Detectron2 install on Apple Silicon is finicky — common failure point", "no per-cell table reconstruction (table region only)", "doesn't fine-tune well to historical / non-English layouts"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[Detectron2 PubLayNet model]
  B --> C{block.type}
  C -- Text --> T1[Region normal_text]
  C -- Title --> T2[Region kv_pair · layout_label=title]
  C -- List --> T3[Region normal_text · layout_label=list]
  C -- Table --> T4[Region table + empty TableModel]
  C -- Figure --> T5[Region image]
  T1 --> F[derive doc_format]
  T2 --> F
  T3 --> F
  T4 --> F
  T5 --> F
  F --> G[Presidio PII]
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant S as SubprocessStage
  participant W as Layout-Parser worker
  R->>S: build_payload (page paths, dpi, score_threshold)
  S->>W: spawn python -m app.workers.layout_parser_worker
  W->>W: lp.Detectron2LayoutModel(...).detect(image)
  W->>W: classify doc_format from area weights
  W-->>S: JSON {pages, regions, tables, doc_format}
  S-->>R: merge into RunState + copy doc_format`,
    interpretation:
      "Look at the `Format: <label>` pill in the card header — that's the page-level summary derived from the area distribution. The detailed `doc_format_scores` (per-bucket fractions) appear as the pill's tooltip. Title / List regions land under the Key-Value pairs and Regions panels respectively; Figure regions land under Images. The empty TableModel for each detected table is a placeholder — pair this card with a real table extractor (camelot / pdfplumber / paddle_structure) for cell content.",
  },

  layout_parser_pdf: {
    display_name: "Layout-Parser (PDF-native)",
    long_description:
      "Vector-PDF variant of layout_parser. Reads the PDF text layer directly via `lp.load_pdf` (pdfplumber under the hood) for exact-position text tokens — no rasterization needed for those — then runs the PaddleDetection PubLayNet model on the rasterized page only to catch non-text structural elements (Figure / Table / Title) that aren't representable in the text stream. Text regions carry `attributes.source = \"pdf_text\"` (confidence 1.0); visual-model regions carry `attributes.source = \"visual\"` with the model's score. **Vector PDFs only** — auto-skipped on scanned documents.",
    prerequisites: [
      "`pip install -e \".[layout-parser]\"`",
      "`pip install -e \".[native-pdfplumber]\"` (lp.load_pdf uses pdfplumber)",
      "Vector PDF (auto-skipped on scanned docs)",
    ],
    good_at: ["exact text positions from PDF stream (no OCR drift)", "still gets visual classes (figures, tables, titles) from the model", "directly comparable to layout_parser for the same page — same model, different input"],
    weak_at: ["scanned / image-only PDFs (auto-skipped)", "PDFs whose text layer is corrupted or password-protected", "model load + first-run download still required for the visual half"],
    mermaid_flow: `flowchart LR
  A[PDF path] --> B{pdf_kind == vector?}
  B -- no --> S[skipped: not native]
  B -- yes --> C[lp.load_pdf]
  C --> D[text-layer tokens · pt → image_px]
  D --> R1[Region normal_text · source=pdf_text · conf 1.0]
  A2[PDF page raster] --> V[PaddleDetection visual model]
  V --> R2[Region Figure / Table / Title · source=visual]
  R1 --> M[merge regions]
  R2 --> M
  M --> F[derive doc_format]
  F --> G[Presidio PII]
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant S as SubprocessStage
  participant W as Layout-Parser PDF worker
  R->>S: build_payload (pdf_path + page paths)
  S->>W: spawn python -m app.workers.layout_parser_pdf_worker
  W->>W: lp.load_pdf → text-layer Layouts
  W->>W: lp.PaddleDetectionLayoutModel.detect(image) per page
  W->>W: filter visual hits to Title/List/Table/Figure
  W->>W: classify doc_format from area weights
  W-->>S: JSON {pages, regions, tables, doc_format}
  S-->>R: merge into RunState + copy doc_format`,
    interpretation:
      "Compare side-by-side with `layout_parser` on the same vector PDF. Text positions should look identical to native_pdfplumber's output (because that's the same library underneath), while figure / table / title detections come from the same PaddleDetection model as `layout_parser`. If you only see `normal_text` regions and no Figure / Table / Title, set `params.use_visual_model = false` was probably triggered — or the visual model load failed (check the stderr log).",
  },

  deepdoc_baseline: {
    display_name: "RAGFlow deepdoc (default ONNX OCR)",
    long_description:
      "RAGFlow's `deepdoc/vision` pipeline running in our harness via a vendored copy at `backend/vendor/deepdoc/`. Stack: ONNX layout detector (YOLOv10 PubLayNet-style) → ONNX text detection + recognition → ONNX table-structure recognizer. Layout regions flow through `LayoutRecognizer4YOLOv10`, OCR text comes from deepdoc's bundled `OCR` class. Subprocess-isolated; first-run downloads ~250 MB of ONNX weights from Hugging Face `InfiniFlow/deepdoc` into `~/.cache/ragflow/rag/res/deepdoc/`.",
    prerequisites: [
      "`pip install -e \".[ocr-deepdoc]\"`",
      "Outbound HTTPS to `huggingface.co` for first-run model download",
    ],
    good_at: ["coherent layout + OCR pipeline (no impedance mismatch between layout and text models)", "ONNX runtime is fast and low-RAM on CPU", "5-class layout taxonomy (text/title/table/figure/header-footer)"],
    weak_at: ["only English-tuned in the bundled weights; CJK accuracy degrades", "no per-cell table contents (table region + row/col counts only)", "first-run model download is ~250 MB"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[deepdoc OCR: text detection]
  B --> C[deepdoc OCR: text recognition]
  C --> D[OCR results per page]
  D --> E[LayoutRecognizer4YOLOv10]
  A --> E
  E --> F[regions tagged with layout_type]
  E --> T[table-typed regions]
  T --> U[TableStructureRecognizer]
  U --> V[row/col bands]
  F --> G[Presidio PII]
  V --> G
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant S as SubprocessStage
  participant W as deepdoc worker
  R->>S: build_payload (page paths, params)
  S->>W: spawn python -m app.workers.deepdoc_worker
  W->>W: prepend vendor/ + _ragflow_stubs to sys.path
  W->>W: deepdoc OCR detect + recognize_batch per page
  W->>W: LayoutRecognizer4YOLOv10(images, ocr_res)
  W->>W: TableStructureRecognizer on each table crop
  W-->>S: JSON {pages, regions, tables}
  S-->>R: merge into RunState`,
    interpretation:
      "Compare against `paddle_structure` and `docling` — same kind of pipeline, different model weights. Text regions get `source_tool=deepdoc/default`; tables carry row/col band counts in `n_rows`/`n_cols` but no per-cell text (TSR exposes bands, not the full grid). Pair with `camelot_*` or `pdfplumber` if you need cell content.",
  },

  deepdoc_tesseract: {
    display_name: "RAGFlow deepdoc · Tesseract",
    long_description:
      "Same layout + TSR pipeline as `deepdoc_baseline` but text comes from Tesseract via `pytesseract.image_to_data`. Words are grouped into lines by tesseract's block/par/line ids and fed to deepdoc's LayoutRecognizer as the OCR result. Lets you see whether a classical CRNN backend beats the bundled ONNX recognizer on your documents.",
    prerequisites: [
      "`pip install -e \".[ocr-deepdoc]\"`",
      "`brew install tesseract` (already a core system dep)",
    ],
    good_at: ["fast, no GPU needed", "directly comparable to `ocr_tesseract_baseline` — same text engine, but driven by deepdoc's layout/table model"],
    weak_at: ["tesseract struggles on low-contrast scans where the ONNX recognizer wins", "word-line grouping is heuristic — long multi-column lines may merge"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[Tesseract: image_to_data]
  B --> C[group words → lines]
  C --> D[OCR results per page]
  D --> E[deepdoc LayoutRecognizer]
  A --> E
  E --> F[regions tagged]
  E --> T[tables → TSR]
  F --> G[Presidio PII]
  T --> G
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant W as deepdoc worker
  R->>W: params={"ocr_backend": "tesseract"}
  W->>W: TesseractDeepdocOCR.recognize_page(image)
  W->>W: LayoutRecognizer4YOLOv10(images, ocr_res)
  W-->>R: regions + tables`,
    interpretation:
      "Same comparison axis as the img2table_* family — same layout/table detector, different OCR. Look at text accuracy on the same pages between `deepdoc_baseline` and this card to see whether tesseract or deepdoc's ONNX recognizer reads your documents better.",
  },

  deepdoc_easyocr: {
    display_name: "RAGFlow deepdoc · EasyOCR",
    long_description:
      "Same layout + TSR pipeline as `deepdoc_baseline`, but text comes from EasyOCR's deep-learning detector + CRNN recognizer. EasyOCR's quad bboxes are converted to axis-aligned rectangles before being fed to deepdoc's LayoutRecognizer.",
    prerequisites: [
      "`pip install -e \".[ocr-deepdoc,ocr-easy]\"`",
    ],
    good_at: ["multilingual recognition (EasyOCR supports 80+ languages out of the box)", "robust on low-contrast / curved text"],
    weak_at: ["slower than deepdoc's bundled OCR (~5–15 s/page on CPU)", "first-run model download ~100 MB for EasyOCR + ~250 MB for deepdoc"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[EasyOCR.readtext]
  B --> C[quad → axis-aligned rect]
  C --> D[OCR results per page]
  D --> E[deepdoc LayoutRecognizer]
  A --> E
  E --> F[regions tagged]
  F --> G[Presidio PII]
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant W as deepdoc worker
  R->>W: params={"ocr_backend": "easyocr"}
  W->>W: EasyOCRDeepdocOCR.recognize_page(image)
  W->>W: LayoutRecognizer4YOLOv10(images, ocr_res)
  W-->>R: regions + tables`,
    interpretation:
      "EasyOCR's CRNN typically outperforms tesseract on noisy scans but is slower. Compare against `deepdoc_tesseract` on the same page to spot text the cheap engine missed.",
  },

  deepdoc_doctr: {
    display_name: "RAGFlow deepdoc · DocTR",
    long_description:
      "Same layout + TSR pipeline as `deepdoc_baseline`, but text comes from python-doctr's two-stage detection + recognition transformer. The doctr predictor runs first; line geometry + word text are converted to deepdoc's expected OCR shape.",
    prerequisites: [
      "`pip install -e \".[ocr-deepdoc,ocr-doctr]\"`",
    ],
    good_at: ["clean printed documents (DocTR is trained on PubLayNet-adjacent data)", "good word-level confidence calibration"],
    weak_at: ["~5–20 s/page on CPU", "first-run model download ~150 MB doctr + ~250 MB deepdoc"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[doctr ocr_predictor]
  B --> C[per-word geometry + text]
  C --> D[OCR results per page]
  D --> E[deepdoc LayoutRecognizer]
  A --> E
  E --> F[regions tagged]
  F --> G[Presidio PII]
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant W as deepdoc worker
  R->>W: params={"ocr_backend": "doctr"}
  W->>W: DoctrDeepdocOCR.recognize_page(image)
  W->>W: LayoutRecognizer4YOLOv10(images, ocr_res)
  W-->>R: regions + tables`,
    interpretation:
      "Compare against `doctr_baseline` to see whether deepdoc's layout/TSR model improves outcomes vs. running doctr standalone. Worth pairing with `deepdoc_baseline` to A/B doctr vs. deepdoc's ONNX recognizer on the same layout.",
  },

  deepdoc_paddle: {
    display_name: "RAGFlow deepdoc · PaddleOCR",
    long_description:
      "Same layout + TSR pipeline as `deepdoc_baseline`, but text comes from PaddleOCR (PP-OCRv4 mobile by default — same pin as `paddleocr_baseline` to avoid the OOM that PP-OCRv5 triggers on 8 GB Macs). Lets you compare deepdoc's bundled OCR vs. PaddleOCR with the same layout/table heuristics applied to both.",
    prerequisites: [
      "`pip install -e \".[ocr-deepdoc,ocr-paddle]\"`",
    ],
    good_at: ["multilingual (PaddleOCR supports Asian-script text out of the box)", "directly comparable to `paddleocr_baseline` and `paddle_structure`"],
    weak_at: ["paddle's recognizer can be heavy — already pinned to PP-OCRv4 mobile", "first-run pulls models for both paddle (~150 MB) and deepdoc (~250 MB)"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[PaddleOCR PP-OCRv4]
  B --> C[poly + text + score]
  C --> D[OCR results per page]
  D --> E[deepdoc LayoutRecognizer]
  A --> E
  E --> F[regions tagged]
  F --> G[Presidio PII]
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant W as deepdoc worker
  R->>W: params={"ocr_backend": "paddle"}
  W->>W: PaddleDeepdocOCR.recognize_page(image)
  W->>W: LayoutRecognizer4YOLOv10(images, ocr_res)
  W-->>R: regions + tables`,
    interpretation:
      "The most useful three-way comparison: this card vs. `paddleocr_baseline` (paddle without deepdoc's layout) vs. `paddle_structure` (paddle's own end-to-end pipeline). Reveals whether deepdoc's layout helps, hurts, or is a wash on documents you care about.",
  },

  doctr_baseline: {
    display_name: "DocTR baseline",
    long_description:
      "python-doctr (Document Text Recognition) as a standalone solution. Uses `ocr_predictor(pretrained=True)` which downloads a detection + recognition model (~150 MB) on first use. Bounding boxes are relative (0–1) and converted to pixels. Runs on CPU.",
    prerequisites: [
      "`pip install -e \".[ocr-doctr]\"` — pulls PyTorch",
    ],
    good_at: ["clean scanned documents", "good word-level bbox accuracy", "no external service"],
    weak_at: ["~5–20 s/page on CPU", "no table detection"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[doctr ocr_predictor]
  B --> C[relative bboxes 0-1]
  C --> D[convert to image_px]
  D --> E[Region normal_text]
  E --> F[Presidio PII]
  F --> G[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant D as DocTR predictor
  participant P as PresidioPII
  participant A as AnnotatePage
  R->>D: model(image_tensor)
  D-->>R: Document with pages/blocks/words
  R->>R: relative bbox → pixel coords
  R->>P: run(ctx, state)
  P-->>R: pii spans + masked images
  R->>A: run(ctx, state)
  A-->>R: annotated PNGs`,
    interpretation:
      "Regions are all `normal_text`. Coordinates relative in the model but converted to image_px. Compare word-level accuracy against tesseract and easyocr baselines.",
  },

  img2table_tesseract: {
    display_name: "img2table · Tesseract",
    long_description:
      "img2table table detection backed by Tesseract OCR. img2table detects both bordered and borderless tables using its own line/whitespace heuristics; cells are filled with text from the Tesseract pass. Renamed from `img2table` to make the OCR backend explicit.",
    prerequisites: [
      "`pip install -e \".[tables-img]\"`",
      "`brew install tesseract`",
    ],
    good_at: ["mixed bordered + borderless tables", "fast (~1–6 s/page)", "no heavy ML"],
    weak_at: ["multi-column document layouts (merges columns)", "thin/inconsistent borders"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[Tesseract: text regions]
  B --> C[img2table subprocess]
  C --> D[detect bordered tables]
  C --> E[detect borderless tables]
  D --> F[grid → TableModel]
  E --> F
  F --> G[Presidio PII]
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant S as SubprocessStage
  participant W as img2table worker
  R->>S: build_payload (page paths, dpi)
  S->>W: spawn python -m app.workers.img2table_worker
  W->>W: Image(src=png).extract_tables(ocr=Tesseract)
  W-->>S: JSON {pages, regions, tables}
  S-->>R: merge into RunState`,
    interpretation:
      "Same as old `img2table` entry. border_mode=\"mixed\". Compare against img2table_easyocr for accuracy on low-contrast scans.",
  },

  img2table_easyocr: {
    display_name: "img2table · EasyOCR",
    long_description:
      "img2table table detection with EasyOCR as the OCR backend. Same table detection heuristics as img2table_tesseract but EasyOCR's deep-learning recognizer fills the cells. Requires both `[tables-img]` and `[ocr-easy]` extras.",
    prerequisites: [
      "`pip install -e \".[tables-img]\"` and `pip install -e \".[ocr-easy]\"`",
    ],
    good_at: ["better cell-text quality on low-contrast or noisy scans vs Tesseract backend"],
    weak_at: ["slower (EasyOCR model load ~5–15 s overhead)", "more RAM"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[EasyOCR: text regions]
  B --> C[img2table subprocess]
  C --> D[detect bordered tables]
  C --> E[detect borderless tables]
  D --> F[grid → TableModel]
  E --> F
  F --> G[Presidio PII]
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant S as SubprocessStage
  participant W as img2table worker
  R->>S: build_payload (page paths, dpi)
  S->>W: spawn python -m app.workers.img2table_worker
  W->>W: Image(src=png).extract_tables(ocr=EasyOCR)
  W-->>S: JSON {pages, regions, tables}
  S-->>R: merge into RunState`,
    interpretation:
      "Compare cell text against img2table_tesseract — EasyOCR should win on difficult scans.",
  },

  img2table_doctr: {
    display_name: "img2table · DocTR",
    long_description:
      "img2table table detection backed by DocTR. Combines img2table's structural detection with DocTR's transformer-based text recognizer. Requires `[tables-img]` and `[ocr-doctr]`.",
    prerequisites: [
      "`pip install -e \".[tables-img]\"` and `pip install -e \".[ocr-doctr]\"`",
    ],
    good_at: ["accurate word recognition", "good on clean printed docs"],
    weak_at: ["slowest of the img2table variants on CPU"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[DocTR: text regions]
  B --> C[img2table subprocess]
  C --> D[detect bordered tables]
  C --> E[detect borderless tables]
  D --> F[grid → TableModel]
  E --> F
  F --> G[Presidio PII]
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant S as SubprocessStage
  participant W as img2table worker
  R->>S: build_payload (page paths, dpi)
  S->>W: spawn python -m app.workers.img2table_worker
  W->>W: Image(src=png).extract_tables(ocr=DocTR)
  W-->>S: JSON {pages, regions, tables}
  S-->>R: merge into RunState`,
    interpretation:
      "Compare against img2table_tesseract and img2table_easyocr for cell-text quality.",
  },

  img2table_paddle: {
    display_name: "img2table · PaddleOCR",
    long_description:
      "img2table table detection backed by PaddleOCR. Uses PP-OCRv4 (mobile tier) to stay within RAM limits. Requires `[tables-img]` and `[ocr-paddle]` plus the paddlex[ocr] extra install step.",
    prerequisites: [
      "`pip install -e \".[tables-img]\"` and `pip install -e \".[ocr-paddle]\"`",
      "`pip install \"paddlex[ocr]==<version>\"`",
    ],
    good_at: ["multilingual documents", "paddle's mobile models are reasonably fast on CPU"],
    weak_at: ["OOM on 8 GB Macs if other heavy processes are running", "first-run model download"],
    mermaid_flow: `flowchart LR
  A[PDF page raster] --> B[PaddleOCR PP-OCRv4: text regions]
  B --> C[img2table subprocess]
  C --> D[detect bordered tables]
  C --> E[detect borderless tables]
  D --> F[grid → TableModel]
  E --> F
  F --> G[Presidio PII]
  G --> H[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant S as SubprocessStage
  participant W as img2table worker
  R->>S: build_payload (page paths, dpi)
  S->>W: spawn python -m app.workers.img2table_worker
  W->>W: Image(src=png).extract_tables(ocr=PaddleOCR)
  W-->>S: JSON {pages, regions, tables}
  S-->>R: merge into RunState`,
    interpretation:
      "Compare table structure against other img2table variants; paddle's recognizer handles mixed-script text better than tesseract.",
  },

  camelot_lattice: {
    display_name: "Camelot · Lattice (ruled)",
    long_description:
      "Camelot in lattice-only mode, tuned for ruled-line tables. Params: `line_scale=40`, `copy_text=[\"v\"]`, `shift_text=[\"l\",\"t\"]`. These settings improve accuracy on tables with thick borders and vertically-spanning cells. Vector PDFs only.",
    prerequisites: [
      "`pip install -e \".[tables-vector]\"`",
      "`brew install ghostscript` (Camelot raster-renders pages internally)",
    ],
    good_at: ["ruled tables with consistent line widths", "vertically-spanning cells", "bank-statement grids"],
    weak_at: ["whitespace-only tables (use stream instead)", "pages with very thin lines (lower line_scale)"],
    mermaid_flow: `flowchart LR
  A[PDF path] --> B[Camelot lattice line_scale=40]
  B --> C[per-table df + bbox in PDF pts]
  C --> D[convert pts → image_px@dpi flip Y]
  D --> E[TableModel]
  E --> F[Presidio PII]
  F --> G[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant W as Camelot worker
  participant GS as Ghostscript
  R->>W: pdf_path, pages, flavor=lattice
  W->>GS: raster preview internally
  W->>W: camelot.read_pdf(lattice, line_scale=40)
  W-->>R: pages.tables with lattice flavor`,
    interpretation:
      "If lattice finds more tables than camelot_vector, the default line_scale was too low. accuracy attribute shows per-table quality; prefer lattice for tables with visible borders.",
  },

  camelot_stream: {
    display_name: "Camelot · Stream (whitespace)",
    long_description:
      "Camelot in stream-only mode, tuned for whitespace-separated tables. Params: `edge_tol=50`, `row_tol=2`. Stream uses text position gaps to infer columns and rows — suited for statements that align numbers in columns without visible lines.",
    prerequisites: [
      "`pip install -e \".[tables-vector]\"`",
      "`brew install ghostscript`",
    ],
    good_at: ["whitespace-aligned tables", "financial reports with no visible grid lines"],
    weak_at: ["ruled tables (use lattice)", "pages with multi-column prose (false positives)"],
    mermaid_flow: `flowchart LR
  A[PDF path] --> B[Camelot stream edge_tol=50 row_tol=2]
  B --> C[per-table df + bbox in PDF pts]
  C --> D[convert pts → image_px@dpi flip Y]
  D --> E[TableModel]
  E --> F[Presidio PII]
  F --> G[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant W as Camelot worker
  participant GS as Ghostscript
  R->>W: pdf_path, pages, flavor=stream
  W->>GS: raster preview internally
  W->>W: camelot.read_pdf(stream, edge_tol=50, row_tol=2)
  W-->>R: pages.tables with stream flavor`,
    interpretation:
      "Compare against camelot_lattice on the same page — stream will find different table boundaries. Use both and pick the flavor whose row/col counts match the visual.",
  },

  tabula_lattice: {
    display_name: "Tabula · Lattice",
    long_description:
      "Tabula in lattice-only mode (`lattice=True, stream=False`). Uses the PDF's line drawing commands to detect table boundaries. Cleaner output than combined mode on ruled tables.",
    prerequisites: [
      "`pip install -e \".[tables-vector]\"`",
      "`brew install openjdk` and `JAVA_HOME` exported",
    ],
    good_at: ["ruled vector-PDF tables", "less noise than combined mode"],
    weak_at: ["no cell bbox info (row/col indices only)"],
    mermaid_flow: `flowchart LR
  A[PDF path] --> B[tabula-py read_pdf lattice=True]
  B --> C[DataFrame per table]
  C --> D[map to TableModel rows/cols]
  D --> E[Presidio PII]
  E --> F[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant W as Tabula worker
  participant J as JVM
  R->>W: pdf_path, pages, lattice=True
  W->>J: spawn java reading PDF lattice mode
  J-->>W: DataFrames per table
  W-->>R: TableModel rows/cols (no bbox)`,
    interpretation:
      "Compare row/col counts against camelot_lattice for the same page.",
  },

  native_pdfplumber: {
    display_name: "pdfplumber (native text + tables + extras)",
    long_description:
      "Native-PDF extraction via pdfplumber (built on pdfminer.six). Words come from `page.extract_words()` and are grouped into lines by their `top` coordinate. Tables come from `page.find_tables()` tried with three strategies in order — ruled `lines`, then `text`-position inference, then a `mixed` (vertical-lines + horizontal-text) fallback — so whitespace-aligned statements aren't silently missed. Beyond text + tables, the stage also emits embedded `images`, `hyperlinks` (with URIs), and PDF `annotations` as Regions. Coordinates are PDF points scaled by `dpi/72` so everything aligns with the rest of the harness. **Vector PDFs only** — the runner auto-skips this solution on scanned documents.",
    prerequisites: ["`pip install -e \".[native-pdfplumber]\"`"],
    good_at: ["vector PDFs with a real text layer", "exact text fidelity — characters come straight from the PDF, no recognition error", "whitespace-aligned financial tables (text strategy catches what `lines` misses)", "embedded images, hyperlinks, and PDF annotations as first-class regions", "pure-Python, no native dependencies"],
    weak_at: ["scanned / image-only PDFs (auto-skipped)", "slower than PyMuPDF on large docs", "table heuristics misfire on complex multi-column layouts"],
    mermaid_flow: `flowchart LR
  A[PDF path] --> B{pdf_kind == vector?}
  B -- no --> S[skipped: not native]
  B -- yes --> C[pdfplumber.open]
  C --> D[page.extract_words]
  C --> E[find_tables: lines → text → mixed]
  C --> X[page.images + hyperlinks + annots]
  D --> F[group words → lines]
  E --> G[cells → TableModel]
  X --> Y[Region image / kv_pair]
  F --> H[Region normal_text]
  H --> I[Presidio PII]
  G --> I
  Y --> I
  I --> J[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant N as NativePdfPlumberStage
  participant P as pdfplumber
  R->>R: solution.supports(pdf_kind)?
  alt scanned / mixed
    R-->>R: SolutionResult skipped (not native)
  else vector
    R->>N: run(ctx, state)
    N->>P: pdfplumber.open(pdf_path)
    P-->>N: pages with words + tables
    N->>N: pt → image_px @ dpi
    N-->>R: regions + tables
  end`,
    interpretation:
      "Confidence is always 1.0 — text comes directly from the PDF stream, not from OCR. If you see this card with status `skipped`, the document was classified as `scanned` and the solution was not run. Compare against `native_pymupdf` for the same page: pdfplumber's table-detection heuristics tend to win on whitespace-aligned columns while PyMuPDF wins on dense ruled grids.",
  },

  native_pymupdf: {
    display_name: "PyMuPDF (native text + tables)",
    long_description:
      "Native-PDF extraction: opens the original PDF with PyMuPDF (fitz) and pulls text directly from the PDF stream — no rasterization, no OCR. Lines come from `page.get_text(\"dict\")`; tables come from `page.find_tables()`. Coordinates are scaled from PDF points to image pixels at the run DPI so they align with every other solution. **Vector PDFs only** — the runner auto-skips this solution on scanned documents with a clear `not applicable: document is not native` message.",
    prerequisites: ["`pymupdf>=1.24` (already in core deps)"],
    good_at: ["vector / native PDFs with a real text layer", "fastest of all solutions (no OCR, no model)", "exact text fidelity — characters come straight from the PDF, no recognition error", "ruled and whitespace tables via find_tables()"],
    weak_at: ["scanned / image-only PDFs (auto-skipped)", "PDFs with embedded images of text (no text layer to read)", "complex table layouts where find_tables heuristics misfire"],
    mermaid_flow: `flowchart LR
  A[PDF path] --> B{pdf_kind == vector?}
  B -- no --> S[skipped: not native]
  B -- yes --> C[fitz.open]
  C --> D[page.get_text dict]
  C --> E[page.find_tables]
  D --> F[lines → Region normal_text]
  E --> G[cells → TableModel]
  F --> H[Presidio PII]
  G --> H
  H --> I[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant N as NativePyMuPDFStage
  participant F as PyMuPDF
  R->>R: solution.supports(pdf_kind)?
  alt scanned / mixed
    R-->>R: SolutionResult skipped (not native)
  else vector
    R->>N: run(ctx, state)
    N->>F: fitz.open(pdf_path)
    F-->>N: pages with text + tables
    N->>N: pt → image_px @ dpi
    N-->>R: regions + tables
  end`,
    interpretation:
      "Confidence is always 1.0 — text comes directly from the PDF stream, not from OCR. If you see this card with status `skipped`, the document was classified as `scanned` (no extractable text layer) and the solution was not run. Compare against camelot/tabula for the same page: those use vector PDF too but with different table-detection heuristics.",
  },

  tabula_stream: {
    display_name: "Tabula · Stream (whitespace)",
    long_description:
      "Tabula in stream mode (`stream=True, guess=True`). Column boundaries are inferred from whitespace gaps with column guessing enabled. Good for financial statements with no visible lines.",
    prerequisites: [
      "`pip install -e \".[tables-vector]\"`",
      "`brew install openjdk` and `JAVA_HOME` exported",
    ],
    good_at: ["whitespace tables", "column alignment in financial statements"],
    weak_at: ["no cell bbox", "guess heuristic can split or merge columns incorrectly"],
    mermaid_flow: `flowchart LR
  A[PDF path] --> B[tabula-py read_pdf stream=True guess=True]
  B --> C[DataFrame per table]
  C --> D[map to TableModel rows/cols]
  D --> E[Presidio PII]
  E --> F[annotate]`,
    mermaid_sequence: `sequenceDiagram
  participant R as Runner
  participant W as Tabula worker
  participant J as JVM
  R->>W: pdf_path, pages, stream=True, guess=True
  W->>J: spawn java reading PDF stream mode
  J-->>W: DataFrames per table
  W-->>R: TableModel rows/cols (no bbox)`,
    interpretation:
      "Compare against camelot_stream — different parsers, different heuristics. If both find the same column count you can trust that structure.",
  },
};

export const CATEGORY_LABEL: Record<"tables" | "text" | "pii" | "layout", string> = {
  tables: "Tables",
  text: "Text / Regions",
  pii: "PII detection",
  layout: "Layout",
};

// What's in the flow for each scenario. Used to badge the selection cards so a
// reviewer can tell at a glance whether a scenario shells out to an LLM, runs a
// vision model, or stays classical-OCR.
export type TechTag = "OCR" | "Vision" | "LLM" | "Vector PDF" | "Subprocess";

export const TECH_TAGS: Record<string, TechTag[]> = {
  ocr_tesseract_baseline: ["OCR"],
  opencv_tesseract: ["OCR"],
  claude_vision: ["OCR", "Vision", "LLM"],
  openai_vision: ["OCR", "Vision", "LLM"],
  gemini_vision: ["OCR", "Vision", "LLM"],
  img2table: ["OCR", "Subprocess"],
  img2table_tesseract: ["OCR", "Subprocess"],
  img2table_easyocr: ["OCR", "Vision", "Subprocess"],
  img2table_doctr: ["OCR", "Vision", "Subprocess"],
  img2table_paddle: ["OCR", "Vision", "Subprocess"],
  easyocr_baseline: ["OCR", "Vision", "Subprocess"],
  doctr_baseline: ["OCR", "Vision", "Subprocess"],
  paddleocr_baseline: ["OCR", "Vision", "Subprocess"],
  native_pymupdf: ["Vector PDF"],
  native_pdfplumber: ["Vector PDF"],
  layout_parser: ["Vision", "Subprocess"],
  layout_parser_pdf: ["Vector PDF", "Vision", "Subprocess"],
  deepdoc_baseline: ["OCR", "Vision", "Subprocess"],
  deepdoc_tesseract: ["OCR", "Vision", "Subprocess"],
  deepdoc_easyocr: ["OCR", "Vision", "Subprocess"],
  deepdoc_doctr: ["OCR", "Vision", "Subprocess"],
  deepdoc_paddle: ["OCR", "Vision", "Subprocess"],
  trocr_handwritten: ["OCR", "Vision", "Subprocess"],
  trocr_printed: ["OCR", "Vision", "Subprocess"],
  camelot_vector: ["Vector PDF", "Subprocess"],
  camelot_lattice: ["Vector PDF", "Subprocess"],
  camelot_stream: ["Vector PDF", "Subprocess"],
  tabula_vector: ["Vector PDF", "Subprocess"],
  tabula_lattice: ["Vector PDF", "Subprocess"],
  tabula_stream: ["Vector PDF", "Subprocess"],
  paddle_structure: ["OCR", "Vision", "Subprocess"],
  docling: ["OCR", "Vision", "Subprocess"],
  docling_tesseract: ["OCR", "Vision", "Subprocess"],
  docling_rapidocr: ["OCR", "Vision", "Subprocess"],
  docling_doctr: ["OCR", "Vision", "Subprocess"],
  docling_trocr_handwritten: ["OCR", "Vision", "Subprocess"],
};

export const TECH_TAG_COLOR: Record<TechTag, string> = {
  OCR: "#0969da",
  Vision: "#8250df",
  LLM: "#bf3989",
  "Vector PDF": "#0a7c7c",
  Subprocess: "#57606a",
};

export const TECH_TAG_DESCRIPTION: Record<TechTag, string> = {
  OCR: "Classical character recognition (tesseract / paddleocr / rapidocr).",
  Vision: "Deep-learning vision model for layout / structure detection.",
  LLM: "Calls a large language model (Anthropic Claude).",
  "Vector PDF": "Reads the PDF's text layer directly; vector PDFs only.",
  Subprocess: "Runs in an isolated subprocess so a native crash can't take down the API.",
};

export interface SolutionGroup {
  key: string;
  label: string;
  description: string;
  solutions: string[];
}

export const SOLUTION_GROUPS: SolutionGroup[] = [
  {
    key: "native_pdf",
    label: "Native PDF",
    description: "Reads the PDF's text + tables directly via PyMuPDF / pdfplumber — no OCR, no rasterization. Vector PDFs only; auto-skipped on scanned documents.",
    solutions: ["native_pymupdf", "native_pdfplumber"],
  },
  {
    key: "ocr_baseline",
    label: "OCR Baselines",
    description: "Classical text extraction — Tesseract, OpenCV preprocessing, EasyOCR, DocTR, PaddleOCR, TrOCR (handwritten + printed).",
    solutions: ["ocr_tesseract_baseline", "opencv_tesseract", "easyocr_baseline", "doctr_baseline", "paddleocr_baseline", "trocr_handwritten", "trocr_printed"],
  },
  {
    key: "img2table",
    label: "img2table (image-based table detection)",
    description: "img2table detects bordered and borderless tables on rasterized pages. Available with multiple OCR backends.",
    solutions: ["img2table_tesseract", "img2table_easyocr", "img2table_doctr", "img2table_paddle"],
  },
  {
    key: "vector_camelot",
    label: "Camelot (vector PDF tables)",
    description: "Camelot reads the PDF text/line layer directly — no rasterization needed. Lattice uses visible rules; stream uses whitespace gaps.",
    solutions: ["camelot_vector", "camelot_lattice", "camelot_stream"],
  },
  {
    key: "vector_tabula",
    label: "Tabula (vector PDF tables)",
    description: "Tabula is a JVM-backed PDF table extractor. Lattice uses ruled lines; stream uses whitespace with optional column guessing.",
    solutions: ["tabula_vector", "tabula_lattice", "tabula_stream"],
  },
  {
    key: "vision_ml",
    label: "Vision / ML",
    description: "Deep-learning models for layout analysis and full-document understanding. Layout-Parser additionally sets a page-level `doc_format` label (tabular-heavy / form-like / narrative / image-heavy / mixed) that surfaces as a pill on this and other layout-emitting cards.",
    solutions: ["paddle_structure", "docling", "docling_tesseract", "docling_rapidocr", "docling_doctr", "docling_trocr_handwritten", "layout_parser", "layout_parser_pdf"],
  },
  {
    key: "ragflow_deepdoc",
    label: "RAGFlow deepdoc",
    description: "RAGFlow's `deepdoc/vision` pipeline — ONNX layout detector + table-structure recognizer — vendored from upstream (Apache 2.0). Five cards share the same layout + table models but swap the OCR backend: default ONNX bundle, Tesseract, EasyOCR, DocTR, or PaddleOCR. Pick the comparison that matters for your benchmark.",
    solutions: ["deepdoc_baseline", "deepdoc_tesseract", "deepdoc_easyocr", "deepdoc_doctr", "deepdoc_paddle"],
  },
  {
    key: "llm_vision",
    label: "LLM Vision",
    description: "Large language models with vision capability — send redacted page images for structured extraction. Requires API keys in .env.",
    solutions: ["claude_vision", "openai_vision", "gemini_vision"],
  },
];

// Cost per million tokens by model name prefix (input, output in USD).
export const LLM_COST_PER_M: Record<string, { input: number; output: number }> = {
  "claude-opus-4": { input: 15, output: 75 },
  "claude-sonnet-4": { input: 3, output: 15 },
  "claude-haiku-4": { input: 0.25, output: 1.25 },
  "claude-opus": { input: 15, output: 75 },
  "claude-sonnet": { input: 3, output: 15 },
  "claude-haiku": { input: 0.25, output: 1.25 },
  "gpt-4o-mini": { input: 0.15, output: 0.60 },
  "gpt-4o": { input: 2.50, output: 10 },
  "gpt-4-turbo": { input: 10, output: 30 },
  "gemini-2.5-pro": { input: 1.25, output: 10 },
  "gemini-2.0-flash": { input: 0.10, output: 0.40 },
  "gemini-1.5-pro": { input: 1.25, output: 5 },
  "gemini-1.5-flash": { input: 0.075, output: 0.30 },
};

export function estimateLlmCost(usage: { input_tokens?: number; output_tokens?: number; model?: string }): number | null {
  if (!usage.model) return null;
  const entry = Object.entries(LLM_COST_PER_M).find(([prefix]) => usage.model!.startsWith(prefix));
  if (!entry) return null;
  const [, rates] = entry;
  return ((usage.input_tokens ?? 0) / 1_000_000) * rates.input
    + ((usage.output_tokens ?? 0) / 1_000_000) * rates.output;
}
