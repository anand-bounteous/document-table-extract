# Setup — macOS (Apple Silicon)

End-to-end install for `sof-table-extract` on macOS (Apple Silicon — M1/M2/M3/M4).
Tested on macOS 15, Python 3.12, Node 22+.

For Linux, see **[SETUP-LINUX.md](./SETUP-LINUX.md)** — the optional extras
overlap but the system prerequisites and a few ARM-specific workarounds differ.

Everything except the system prerequisites lives inside per-folder
`backend/.venv` and `frontend/node_modules` — nothing is installed globally.

---

## 0. Quick start (local dev)

Use this path to get the UI and API running locally. Two terminals are required.

### 0a. Check toolchain

```bash
python3.12 --version   # 3.12.x
node --version         # 22.x or newer
npm --version
tesseract --version    # 5.x — install via §1 if missing
```

### 0b. One-time backend setup

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate

pip install -U pip setuptools wheel
pip install -e .
python -m spacy download en_core_web_lg   # ~500 MB; required by Presidio PII stage

# PII benchmark (independent track — §6b)
python -m scripts.prefetch_pii_models     # ~700 MB total; downloads spaCy sm + GLiNER + Piiranha

cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY if you want claude_vision
```

**Minimal local profile** (fastest install; OCR + Claude Vision + PII benchmark Tracks A/B):

```bash
pip install -e .
python -m spacy download en_core_web_lg
python -m spacy download en_core_web_sm   # Track B contextual NER
```

Unlocks: `ocr_tesseract_baseline`, `opencv_tesseract`, `claude_vision` (with `ANTHROPIC_API_KEY`),
PII benchmark Track A (`presidio_regex`) and Track B (`presidio_spacy`).

**Recommended local profile** (most solutions + all 5 PII tracks A–E):

```bash
pip install -e ".[phase2-light,llm-openai,llm-gemini]"
python -m spacy download en_core_web_lg
python -m scripts.prefetch_pii_models     # downloads all PII model assets (~700 MB)
```

Also unlocks: Camelot, Tabula, img2table, EasyOCR, DocTR, the OpenAI/Gemini vision providers (when API keys are set), and PII benchmark Tracks C (`gliner`), D (`piiranha`), E (`hybrid`). See §2b for the full optional-group list and §6b for PII details.

### 0c. One-time frontend setup

```bash
cd frontend          # from repo root
npm install
```

### 0d. Run (every session)

**Terminal 1 — backend** (port `8002`):

```bash
cd backend
source .venv/bin/activate
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

**Terminal 2 — frontend** (port `3000`):

```bash
cd frontend
npm run dev
```

Open <http://localhost:3000>. The Next.js dev server proxies `/api/*` to
`http://localhost:8002` (override with `BACKEND_URL=...`).

### 0e. Smoke-test

With the backend running:

```bash
curl -s http://127.0.0.1:8002/solutions | python3 -m json.tool
curl -s http://127.0.0.1:8002/documents | python3 -m json.tool
```

Upload a PDF in the UI or pick one from `data/`, select solutions, and hit **Run**.

---

## 1. System prerequisites (Homebrew)

These are **not** pip-installable. Install them before `pip install`.

| Tool | Why it's needed | Required by |
|---|---|---|
| `tesseract` | OCR engine binary that `pytesseract` shells out to | every OCR solution |
| `poppler` | optional PDF rasterizer (`pdftoppm`) — PyMuPDF is preferred but img2table may fall back | `img2table_*` solutions |
| `ghostscript` | rasterizes vector PDFs for Camelot | `[tables-vector]` (Camelot) |
| `openjdk` | JVM that `tabula-py` invokes | `[tables-vector]` (Tabula) |
| `pango`, `cairo`, `libffi` | text shaping + PDF backends for WeasyPrint | report PDF export |

**Minimal local dev** needs only `tesseract`. Install the rest when you add the
matching optional solution groups.

```bash
brew install tesseract poppler ghostscript openjdk pango cairo libffi
```

After installing `openjdk`, add the JVM to the discoverable path:

```bash
sudo ln -sfn $(brew --prefix)/opt/openjdk/libexec/openjdk.jdk \
    /Library/Java/JavaVirtualMachines/openjdk.jdk
```

Verify:

```bash
tesseract --version   # 5.x
gs --version          # 10.x
java -version         # 17+
```

---

## 2. Backend

### 2a. Create the venv and install core deps

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate

pip install -U pip setuptools wheel
pip install -e .
python -m spacy download en_core_web_lg   # ~500 MB; required by Presidio PII stage
```

This gives you the core solutions that need no optional extras:

| Solution | What it does |
|---|---|
| `ocr_tesseract_baseline` | Raw Tesseract OCR |
| `opencv_tesseract` | OpenCV pre-processing + Tesseract |
| `claude_vision` | Structured JSON extraction via Claude (needs `ANTHROPIC_API_KEY`) |

### 2b. Install optional solution groups

Each group is independent — install only what you'll use. Model weights are
downloaded on first run (not at install time); see §4 for sizes.

#### LLM vision providers (OpenAI + Gemini)

Anthropic is included in core deps. OpenAI and Gemini need their own extras:

```bash
pip install -e ".[llm-openai]"   # unlocks openai_vision (needs OPENAI_API_KEY)
pip install -e ".[llm-gemini]"   # unlocks gemini_vision (needs GEMINI_API_KEY)
```

| Solution | API key env var |
|---|---|
| `openai_vision` | `OPENAI_API_KEY` |
| `gemini_vision` | `GEMINI_API_KEY` |

#### img2table — rasterized-page table detection

```bash
pip install -e ".[tables-img]"
```

Unlocks: `img2table_tesseract`, `img2table_easyocr`, `img2table_doctr`, `img2table_paddle`

> `img2table_easyocr` also needs `[ocr-easy]`; `img2table_doctr` also needs `[ocr-doctr]`;
> `img2table_paddle` also needs `[ocr-paddle]`.

#### Camelot + Tabula — vector-PDF table extraction

Requires `ghostscript` and `openjdk` from §1.

```bash
pip install -e ".[tables-vector]"
```

Unlocks: `camelot_vector`, `camelot_lattice`, `camelot_stream`, `tabula_vector`, `tabula_lattice`, `tabula_stream`

#### EasyOCR — alternative OCR baseline

```bash
pip install -e ".[ocr-easy]"
```

Unlocks: `easyocr_baseline`

#### DocTR — alternative OCR baseline

```bash
pip install -e ".[ocr-doctr]"
```

Unlocks: `doctr_baseline`

#### PaddleOCR PP-StructureV3 — layout + table + OCR

`paddlex[ocr]` must be installed alongside `paddleocr` (the base package does
not include the OCR pipeline extras). Models (~500 MB) are downloaded from
`paddlepaddle.org.cn` on first use.

```bash
pip install -e ".[ocr-paddle]"
# The meta-group installs paddleocr + paddlepaddle + paddlex, but paddlex
# needs its [ocr] extras explicitly:
PADDLEX_VER=$(pip show paddlex | awk '/^Version/{print $2}')
pip install "paddlex[ocr]==${PADDLEX_VER}"
```

Unlocks: `paddle_structure`, `img2table_paddle`

> **Performance note:** PP-StructureV3 uses server-tier models (PP-OCRv5_server_*,
> PP-DocLayout_plus-L) which run at roughly 0.5–2 fps on CPU. On an 8 GB Mac
> expect 2–5 min/page. A GPU is not required but dramatically speeds things up.

#### Docling — IBM document layout + table

Pulls PyTorch + Transformers and downloads a ~2 GB layout model from Hugging
Face on first use.

```bash
pip install -e ".[docling]"
```

Unlocks: `docling`

#### PaddleOCR baseline — standalone PP-OCRv4 text detection + recognition

A lighter alternative to PP-StructureV3. No layout / table model — emits
line-level text regions only. The worker pins `ocr_version="PP-OCRv4"` by
default because the paddleocr 3.x default (`PP-OCRv5`) peaks above 8 GB during
recognition and gets SIGKILL'd by the macOS OOM killer.

```bash
pip install -e ".[ocr-paddle]"   # same extras group as PP-Structure
```

Unlocks: `paddleocr_baseline`

#### Native PDF — PyMuPDF + pdfplumber

Reads the PDF text + tables directly from the PDF stream — no rasterization,
no OCR. Vector PDFs only; runner auto-skips scanned documents with a
`not applicable: document is not native` message.

```bash
# PyMuPDF (fitz) — already in core deps, nothing to install
pip install -e ".[native-pdfplumber]"
```

Unlocks: `native_pymupdf` (no extras needed), `native_pdfplumber`

> The pdfplumber stage tries three table strategies in order — ruled
> `lines` → `text`-position inference → mixed `lines+text` — so whitespace
> tables that the default config silently misses are still picked up.

#### Layout-Parser — layout detection + doc-format label

Detects Text / Title / List / Table / Figure regions and authoritatively sets
the page-level `doc_format` label (`tabular-heavy | form-like | narrative |
image-heavy | mixed`) that also lights up on every other layout-emitting
card via the shared `DocFormatStage`.

```bash
pip install -e ".[layout-parser]"
```

Unlocks: `layout_parser`

**Backend choice on Apple Silicon.** The canonical Layout-Parser backbone is
**Detectron2** (Facebook), but Detectron2 has **no maintained wheel for
macOS arm64** — building from source requires Xcode, a compatible PyTorch
build, and often fails on M-series chips. The worker therefore **defaults to
the `PaddleDetectionLayoutModel` backend** (PubLayNet PP-YOLOv2), which uses
the `paddlepaddle` install that `[ocr-paddle]` already pulls in.

Switch backends per-run by overriding stage params:

| `params.backend` | Backend | Apple Silicon status |
|---|---|---|
| `"paddle"` *(default)* | `PaddleDetectionLayoutModel` (PubLayNet PP-YOLOv2) | Works out-of-the-box on M-series |
| `"detectron2"` | `Detectron2LayoutModel` (PubLayNet Mask R-CNN) | Requires manual Detectron2 install — see below |

If you really need Detectron2 on macOS arm64 (uncommon — the Paddle backend
detects the same five classes and is materially faster on CPU):

```bash
# Best-effort — not officially supported on macOS arm64
pip install 'git+https://github.com/facebookresearch/detectron2.git'
# Requires Xcode CLT, may take 5–10 min, often fails on PyTorch 2.x
```

Then in a Python session or test, override the param to opt in:

```python
from app.stages.layout.layout_parser_stage import LayoutParserStage
LayoutParserStage(params={"backend": "detectron2", "score_threshold": 0.5})
```

**Doc-format pill — works on every layout-emitting card.** Even if you don't
install `layout-parser`, the shared `DocFormatStage` (added to
`paddle_structure`, `docling`, `claude_vision`, `openai_vision`,
`gemini_vision`) will derive the `format: …` pill from those solutions' own
region distributions.

#### RAGFlow deepdoc — vendored ONNX layout + TSR + swappable OCR

Pure-ONNX pipeline vendored from
[infiniflow/ragflow](https://github.com/infiniflow/ragflow) (Apache 2.0) at
`backend/vendor/deepdoc/`. Five cards share the same layout + table-structure
recognizer; only the OCR backend differs.

```bash
pip install -e ".[ocr-deepdoc]"
```

Unlocks: `deepdoc_baseline`, `deepdoc_tesseract`, `deepdoc_easyocr`, `deepdoc_doctr`, `deepdoc_paddle`

> The OCR-variant cards additionally require their backend's own extras
> (`ocr-easy` / `ocr-doctr` / `ocr-paddle`). The Tesseract variant uses the
> Tesseract binary from §1 — no extra pip extra.

**Why vendored, not pip-installed.** RAGFlow's `pyproject.toml` requires
Python 3.13+ and its packaging is broken on a fresh clone (declares a
`graphrag` package that doesn't exist at the repo root, so `pip install
git+…` fails before pip can even check the Python-version constraint). We
vendor only `deepdoc/vision/*` plus ~80 lines of stubs for the
`common.*` / `rag.*` symbols deepdoc's vision modules import. See
`backend/vendor/VENDORED_FROM.md` for the pinned commit and patch notes.

**Swappable OCR — same pattern as `img2table_*`.** Each card pins a backend
via stage params:

| Card | `params.ocr_backend` | Backend |
|---|---|---|
| `deepdoc_baseline` | `"default"` | Deepdoc's bundled ONNX det + rec |
| `deepdoc_tesseract` | `"tesseract"` | Tesseract via `pytesseract.image_to_data` |
| `deepdoc_easyocr` | `"easyocr"` | EasyOCR (needs `[ocr-easy]`) |
| `deepdoc_doctr` | `"doctr"` | python-doctr (needs `[ocr-doctr]`) |
| `deepdoc_paddle` | `"paddle"` | PaddleOCR PP-OCRv4 (needs `[ocr-paddle]`) |

The OCR adapter lives at `backend/app/stages/ocr/deepdoc_adapters.py` —
adding a sixth backend is ~80 lines.

**Apple Silicon notes.** `onnxruntime>=1.18` has functional arm64 wheels
(CPU-only). The vendored deepdoc code path does not use GPU acceleration on
macOS. First-run pulls ~250 MB of ONNX weights from Hugging Face's
`InfiniFlow/deepdoc` repo into `~/.cache/ragflow/rag/res/deepdoc/`; the
stage's `_deepdoc_env()` injects the macOS SSL bundle so the download
succeeds without manual cert config.

#### TrOCR — handwriting + printed-text transformer recognition

Microsoft TrOCR (HuggingFace transformers). Two cards share the same worker:

| Solution | Model | Output regions |
|---|---|---|
| `trocr_handwritten` | `microsoft/trocr-base-handwritten` | `HANDWRITING_SIGNATURE` (surfaces under Signatures panel) |
| `trocr_printed` | `microsoft/trocr-base-printed` | `NORMAL_TEXT` (comparable to other OCR baselines) |

```bash
pip install -e ".[ocr-trocr]"
```

Unlocks: `trocr_handwritten`, `trocr_printed`

**Version pin rationale — don't loosen.** The extras explicitly pin
`transformers>=4.40,<5` and `huggingface_hub<1`. The `transformers 5.x` line
forces `huggingface_hub>=1.0`, which switched its downloader to **httpx**
and ships a regression where the global httpx client closes itself before
the first request — every TrOCR call fails with:

```
RuntimeError: Cannot send a request, as the client has been closed.
… OSError: Can't load processor for 'microsoft/trocr-base-handwritten'.
```

The 4.x line + `huggingface_hub<1` uses the proven **requests**-based
downloader and works on every macOS / Linux combo we've tested.

**SSL trust — handled by the stage.** The TrOCR stage (and the
Layout-Parser stage) call `ssl_env_overrides()` which points `SSL_CERT_FILE`
/ `REQUESTS_CA_BUNDLE` at Homebrew's OpenSSL bundle. Without that,
HuggingFace's CDN serves a cert chain that `certifi`'s default bundle
doesn't trust on macOS, and the model download fails with:

```
SSLCertVerificationError: unable to get local issuer certificate
```

If you run a TrOCR worker manually outside the harness, export those vars
yourself (see §4 SSL trust).

**Detector reuse.** TrOCR is recognition-only — the worker reuses
`easyocr.Reader.detect()` to find line boxes, so `[ocr-trocr]` includes
`easyocr` as a transitive dependency.

#### Convenience meta-groups

```bash
pip install -e ".[phase2-light]"                        # tables-img + tables-vector + easyocr + doctr
pip install -e ".[phase2,llm-openai,llm-gemini]"        # everything including paddle + docling + all LLM providers
```

### 2c. Configure `.env`

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env` (paths are relative to the `backend/` directory):

```dotenv
# Claude Vision (included in core install)
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
ANTHROPIC_MAX_TOKENS=8192

# OpenAI Vision (requires pip install -e ".[llm-openai]")
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Gemini Vision (requires pip install -e ".[llm-gemini]")
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.0-flash

# Fernet-encrypted PII token maps at rest (recommended for local dev too).
# Generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
PII_MASK_KEY=

# Paths and tuning (defaults work for local dev)
CORS_ORIGINS=http://localhost:3000
DATA_DIR=../data
RUNS_DIR=./storage/runs
DEFAULT_DPI=300       # OCR rasterization DPI
VISION_DPI=200        # Vision-model rasterization DPI

# ---- PII benchmark (independent track, see §6b) -------------------------
PII_V2_ENABLED=true
PII_V2_DEFAULT_DETECTORS=presidio_regex,presidio_spacy,gliner,piiranha,hybrid
PII_V2_TEXT_PRODUCERS=native_pymupdf,native_pdfplumber,paddleocr_baseline,ocr_tesseract_baseline,easyocr_baseline,doctr_baseline,trocr_printed
PII_V2_DEFAULT_JURISDICTIONS=GLOBAL_COMMON,UK
PII_V2_RUNS_DIR=./storage/pii_runs
# Allow ML detector subprocesses to download models from HuggingFace on
# first call. Set to 1 only if you skipped `scripts/prefetch_pii_models`;
# the default (offline) is recommended once models are cached.
PII_V2_HF_ONLINE=0
# Override the default models if you'd like a different size/family.
# PII_V2_GLINER_MODEL=urchade/gliner_small-v2.1
# PII_V2_PIIRANHA_MODEL=iiiorg/piiranha-v1-detect-personal-information
```

`DATA_DIR=../data` points at the sample PDFs in the repo root. `RUNS_DIR` and
`backend/storage/workflows.db` are created automatically on first backend start.

### 2d. Run

```bash
cd backend
source .venv/bin/activate
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

Alternative (same port, built-in reload via `main.py`):

```bash
cd backend
source .venv/bin/activate
python -m app.main
```

The boot log lists every registered solution. With only core deps installed you
will see a shorter list (e.g. `ocr_tesseract_baseline`, `opencv_tesseract`,
`claude_vision`). A full `[phase2]` install registers all solutions:

```
solutions  : ['camelot_lattice', 'camelot_stream', 'camelot_vector',
              'claude_vision',
              'deepdoc_baseline', 'deepdoc_doctr', 'deepdoc_easyocr',
              'deepdoc_paddle', 'deepdoc_tesseract',
              'docling', 'doctr_baseline',
              'easyocr_baseline', 'gemini_vision',
              'img2table_doctr', 'img2table_easyocr',
              'img2table_paddle', 'img2table_tesseract',
              'layout_parser', 'layout_parser_pdf',
              'native_pdfplumber', 'native_pymupdf',
              'ocr_tesseract_baseline', 'openai_vision', 'opencv_tesseract',
              'paddle_structure', 'paddleocr_baseline',
              'tabula_lattice', 'tabula_stream', 'tabula_vector',
              'trocr_handwritten', 'trocr_printed']
```

Smoke-test:

```bash
curl -s http://127.0.0.1:8002/solutions | python3 -m json.tool
curl -s http://127.0.0.1:8002/documents | python3 -m json.tool
```

---

## 3. Frontend

```bash
cd frontend          # from repo root
npm install
npm run dev
```

Opens at <http://localhost:3000>. `/api/*` requests are proxied to
`http://localhost:8002` (override with `BACKEND_URL=...` in the env).

Production build (optional):

```bash
cd frontend
npm run build
npm run start        # also serves on port 3000
```

Upload a PDF or pick one from `data/`, select solutions, and hit **Run**. The
run page polls and fills in cards as each solution finishes. Each card has an
**Execution flow (BPMN)** section that shows the per-solution pipeline diagram
with stage status colours. The master **Pipeline overview** tab shows all
solutions on a single diagram with gateway routing highlighted.

---

## 4. First-run model downloads

These happen on first solution invocation and require outbound network access.

| Solution | Cache location | Source | Approx size |
|---|---|---|---|
| `paddle_structure`, `img2table_paddle` | `~/.paddlex/official_models/` | `paddlepaddle.org.cn` + GitHub | ~500 MB |
| `paddleocr_baseline` | `~/.paddlex/official_models/` | `paddlepaddle.org.cn` | ~150 MB (PP-OCRv4 mobile) |
| `docling` | `~/.cache/docling/`, `~/.cache/huggingface/`, `~/.cache/rapidocr/` | Hugging Face | ~1.5–2 GB |
| `easyocr_baseline` | `~/.EasyOCR/` | GitHub releases | ~100 MB |
| `doctr_baseline`, `img2table_doctr` | `~/.cache/doctr_cache/` | Hugging Face / GitHub | ~150 MB |
| `layout_parser` (paddle backend) | `~/.paddledet/`, `~/.cache/layoutparser/` | layoutparser Dropbox + paddledet | ~250 MB |
| `trocr_handwritten` | `~/.cache/huggingface/` | Hugging Face (`microsoft/trocr-base-handwritten`) | ~600 MB |
| `trocr_printed` | `~/.cache/huggingface/` | Hugging Face (`microsoft/trocr-base-printed`) | ~600 MB |
| `deepdoc_*` (all 5) | `~/.cache/ragflow/rag/res/deepdoc/` | Hugging Face (`InfiniFlow/deepdoc`) | ~250 MB |
| `native_pymupdf`, `native_pdfplumber` | — | — | 0 (no model download) |
| spaCy `en_core_web_lg` | inside the venv (it's a pip package) | PyPI | ~500 MB |

Pre-download on a network-connected machine and copy the cache directories over
if your run environment has no outbound HTTPS.

### SSL trust on macOS (handled automatically)

`certifi`'s root bundle does not include every CA that `paddlepaddle.org.cn`,
`modelscope.cn`, and the **Hugging Face CDN** chain through, while Homebrew's
OpenSSL bundle does. The following subprocess stages automatically set the
overrides via `backend/app/pipeline/ssl_env.py`:

- `paddle_structure`, `img2table_paddle`, `paddleocr_baseline`
- `docling`
- `layout_parser`, `layout_parser_pdf`
- `trocr_handwritten`, `trocr_printed`
- `deepdoc_baseline`, `deepdoc_tesseract`, `deepdoc_easyocr`, `deepdoc_doctr`, `deepdoc_paddle`

They each export:

```
SSL_CERT_FILE=/opt/homebrew/etc/openssl@3/cert.pem
REQUESTS_CA_BUNDLE=/opt/homebrew/etc/openssl@3/cert.pem
CURL_CA_BUNDLE=/opt/homebrew/etc/openssl@3/cert.pem
```

If you run a worker manually outside the harness — or hit
`SSLCertVerificationError` from any other tool that fetches model weights —
export those variables yourself before running.

### Apple Silicon GPU (handled automatically)

Docling's PyTorch models touch float64 tensors which Apple's MPS backend does
not implement. The `vision_docling` stage forces `AcceleratorDevice.CPU` and
sets `PYTORCH_ENABLE_MPS_FALLBACK=1` — no manual action needed on M-series Macs.

---

## 5. Workflow persistence

Every solution run is orchestrated by SpiffWorkflow (BPMN engine) and persisted
to SQLite at `backend/storage/workflows.db`. Tables:

- `workflow_runs` — one row per (run_id, solution), status `running`/`done`/`error`
- `stage_events` — one row per stage execution with timing and any error message

The DB is created automatically on first backend start. To inspect:

```bash
sqlite3 backend/storage/workflows.db \
  "SELECT solution, status, round((updated_at-started_at)*1000) ms FROM workflow_runs ORDER BY started_at DESC LIMIT 20;"
```

BPMN files (editable in Camunda Modeler) live in `backend/app/bpmn/*.bpmn`.
To regenerate them after adding or renaming solutions:

```bash
cd backend
.venv/bin/python -m app.bpmn.generator
```

---

## 6a. Memory & concurrency tuning

When many ML-heavy cards are selected (`paddle_structure`, `docling`,
`deepdoc_*`, `trocr_*`, `layout_parser*`), each one spawns a subprocess that
loads its own 0.4–2 GB model. Running all 30+ in parallel on a small Mac
exhausts RAM. The harness now auto-tunes the number of solution-subprocesses
that can be alive at once.

**Default behaviour** — `MAX_CONCURRENT_SOLUTIONS=0`:

```
n_concurrent = max(1, min(n_solutions, 16, free_RAM_GB // RAM_PER_SOLUTION_GB))
```

Read at run start via `psutil.virtual_memory().available`. The chosen value
is logged on the backend (search the uvicorn log for `"N at a time"`).

**Override per run** — env vars in `backend/.env`:

```dotenv
# 0 = auto from free RAM. Set explicitly to override.
MAX_CONCURRENT_SOLUTIONS=0
# Budget (in GB) the auto-tune assumes for one solution-subprocess.
# Lower this if you trust your selection (only light cards selected) to allow
# more parallelism; raise it if you're hitting OOMs.
RAM_PER_SOLUTION_GB=3.0
```

**Profile examples:**

| Machine | free RAM | default tune | wall-clock for 30 cards × 1 page |
|---|---|---|---|
| 8 GB Mac | ~3 GB | 1 concurrent | ~10–15 min (sequential) |
| 16 GB Mac | ~10 GB | 3 concurrent | ~4–6 min |
| 32 GB Linux | ~24 GB | 8 concurrent | ~2–3 min |

**Multi-document batches** — documents are always run **sequentially** (one
at a time). Within each document, the auto-tuned solution-level cap applies.
The batch dashboard at `/batches/<batch_id>` shows live counts (queued /
running / done) plus per-solution per-page progress for the currently
running document.

**Per-stage page chunking** (opt-in) — heavy workers that hold large
intermediates across many pages can opt in to per-N-page subprocess
invocations:

```python
DeepdocStage(pages_per_chunk=2)   # reload the model every 2 pages
```

`pages_per_chunk=0` (default) keeps the existing behaviour — one subprocess
call covers all pages. Use this knob only if you hit OOM on a single
solution mid-doc (rare with the concurrency cap above).

**Per-page live progress** — every page-loop worker writes a tiny
`progress.json` to its artifacts dir on each page. The `/runs/<id>` poll
attaches this to the solution status entry; the UI's status pill renders
`"Processing… · page 3 / 10"` as it advances.

---

## 6b. PII benchmark (independent UK-banking PII track)

A second PII pipeline runs alongside the existing `PresidioPII` stage. It is
benchmark-oriented: every detector candidate produces the same `PIIEntity`
schema (`backend/app/pii_v2/schema.py`) so they can be compared head-to-head
in a dashboard at `/pii-benchmarks/<id>`. The existing in-pipeline
`PresidioPII` stage is untouched.

### 6b.1 Architecture (one paragraph)

For every uploaded PDF the runner extracts text via each baseline OCR
producer (`native_pymupdf`, `native_pdfplumber`, `paddleocr_baseline`,
`ocr_tesseract_baseline`, `easyocr_baseline`, `doctr_baseline`,
`trocr_printed` by default), then feeds each page's text through every
selected detector. When the **OCR + Table + current PII** flow runs in
parallel (both checkboxes on the home page), the PII track reads OCR text
from `/runs/<paired_run_id>/<solution>/result.json` instead of re-running
OCR. A second mode operates on annotated JSONL datasets and produces a
production-recommendation matrix per `.prompt/009 §13–14`.

### 6b.2 Detectors shipped

All 5 tracks from `.prompt/009 §3` are implemented and benchmark-comparable.

| Track | Detector | Module | Optional dep | When useful |
|---|---|---|---|---|
| A | `presidio_regex` | `pii_v2/detectors/presidio_regex_detector.py` | none — always works | UK postcode, phone, NINO, sort code + account, IBAN (MOD-97), Luhn cards, NHS, UTR |
| B | `presidio_spacy` | `pii_v2/detectors/presidio_spacy_detector.py` | `spacy` + `en_core_web_sm` | Adds PERSON / ORGANISATION / LOCATION / DATE on top of regex |
| C | `gliner` | `pii_v2/detectors/gliner_detector.py` (subprocess) | `gliner` + HF model | Flexible label-driven NER for free-form names, addresses, customer-service notes |
| D | `piiranha` | `pii_v2/detectors/piiranha_detector.py` (subprocess) | `transformers` + cached HF model | Dedicated PII token classifier |
| E | `hybrid` | `pii_v2/detectors/hybrid_detector.py` | uses best available above | Regex + best contextual detector (GLiNER → Piiranha → spaCy → regex-only fallback) |

**Reference baseline** — running all 5 detectors over a 50-record synthetic
UK-banking dataset (`scripts/generate_pii_dataset --count 50`) on an M-series
Mac:

| Detector | P | R | F1 | FP | FN | p50 ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| `presidio_regex` | **0.827** | 0.663 | 0.736 | **0** | 33 | **0.1** | **0.1** |
| `presidio_spacy` | 0.705 | 0.735 | 0.720 | 27 | 20 | 3.7 | 4.4 |
| `gliner` | 0.771 | **0.771** | **0.771** | 1 | 1 | 5688.3 | 5784.0 |
| `piiranha` | 0.383 | 0.446 | 0.412 | 33 | 6 | 3339.5 | 3606.4 |
| `hybrid` | 0.771 | **0.771** | **0.771** | 1 | 1 | 5775.4 | 7323.1 |

- `presidio_regex` wins precision and latency (no model load).
- `gliner` / `hybrid` win recall and F1 — GLiNER picks up PERSON / UK_ADDRESS
  that regex can't see, and hybrid prefers GLiNER as its contextual layer.
- `piiranha` has lower precision in this slice because its label taxonomy
  doesn't 1:1 map to the synthetic dataset's gold labels (the mapping in
  `workers/pii_piiranha_worker.py` is a best-effort attempt; tune it for
  your dataset).
- ML detector latency is dominated by per-record subprocess + model reload
  (~5 s each). For batch use this is the right cost-vs-isolation trade-off;
  for interactive use, swap to an in-process detector or a long-lived
  worker pool.

All five auto-register at import time (`backend/app/pii_v2/detectors/__init__.py`).
If an optional dep is missing, the affected detector returns regex-only output
or — for the subprocess detectors — caches "unavailable" after the first failed
spawn so a 50-record benchmark doesn't pay the cost 50 times.

### 6b.3 Installing dependencies + prefetching models

**Python deps**: `spacy` and `gliner` are already in core `dependencies`
(see `backend/pyproject.toml`); `gliner` transitively brings `transformers`
and `torch` so Piiranha works too. A fresh `uv sync` covers all five tracks.

**Models** are not pip-installable. Three assets must be downloaded once:

| Track | Asset | Size | Source |
|---|---|---|---|
| B | `en_core_web_sm` spaCy model | ~15 MB | PyPI |
| C | `urchade/gliner_small-v2.1` | ~200 MB | huggingface.co |
| D | `iiiorg/piiranha-v1-detect-personal-information` | ~500 MB | huggingface.co |

A **one-shot prefetch script** downloads all three and writes the spaCy
model + HF cache directories so the subprocess workers can stay in offline
mode at run time:

```bash
cd backend
uv run python -m scripts.prefetch_pii_models
```

Expected output:

```
>> Track B  · spaCy en_core_web_sm
   ✓ already installed (or freshly downloaded)
>> Track C  · GLiNER (urchade/gliner_small-v2.1)
   ✓ cached
>> Track D  · Piiranha (iiiorg/piiranha-v1-detect-personal-information)
   ✓ cached

Summary:
  spacy      ✓
  gliner     ✓
  piiranha   ✓
```

The script auto-discovers Homebrew's OpenSSL bundle (`/opt/homebrew/etc/openssl@3/cert.pem`
or `/usr/local/etc/openssl@3/cert.pem`) on macOS so the HF download
isn't blocked by certifi staleness — the same trick the TrOCR /
Layout-Parser stages use.

**Manual equivalents** if you'd rather run each step:

```bash
# Track B
uv run python -m spacy download en_core_web_sm

# Track C
HF_HUB_OFFLINE=0 uv run python -c "from gliner import GLiNER; GLiNER.from_pretrained('urchade/gliner_small-v2.1')"

# Track D
HF_HUB_OFFLINE=0 uv run python -c "from transformers import pipeline; pipeline('token-classification', model='iiiorg/piiranha-v1-detect-personal-information', aggregation_strategy='simple')"
```

**Online/offline mode at run time:** the subprocess workers default to
`HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` so a *missing* model fails
fast instead of hanging. To allow first-time HF downloads from inside the
backend (e.g. you skipped the prefetch step), set
`PII_V2_HF_ONLINE=1` in `backend/.env`. When online, the worker also auto-
discovers Homebrew's OpenSSL cert bundle if available.

**Air-gapped environments:** run `prefetch_pii_models` on a connected
machine, then copy these directories across:

```
~/.cache/huggingface/hub/                # GLiNER + Piiranha
<backend-venv>/lib/python3.12/site-packages/en_core_web_sm/   # spaCy
```

### 6b.4 Configuration (`backend/.env`)

```dotenv
# Master switch — set to false to disable the /pii-benchmarks routes entirely.
PII_V2_ENABLED=true

# Comma-separated. Order matters only for human readability — every detector
# runs in parallel against every OCR producer per page.
PII_V2_DEFAULT_DETECTORS=presidio_regex,presidio_spacy,gliner,piiranha,hybrid

# Default text producers (existing solution names from app/solutions/).
# Producers that aren't registered are surfaced as 'skipped' cells in the UI.
PII_V2_TEXT_PRODUCERS=native_pymupdf,native_pdfplumber,paddleocr_baseline,ocr_tesseract_baseline,easyocr_baseline,doctr_baseline,trocr_printed

# Jurisdiction packages. UK is shipped; GLOBAL_COMMON covers email/IBAN/Luhn.
# Add EU/INDIA later by adding plugins under app/pii_v2/jurisdictions/.
PII_V2_DEFAULT_JURISDICTIONS=GLOBAL_COMMON,UK

# Where /pii-benchmarks state lives. Defaults to backend/storage/pii_runs.
PII_V2_RUNS_DIR=backend/storage/pii_runs

# Model overrides (optional)
PII_V2_GLINER_MODEL=urchade/gliner_small-v2.1
PII_V2_PIIRANHA_MODEL=iiiorg/piiranha-v1-detect-personal-information
```

### 6b.5 Running it

Three entry points:

1. **Paired with the existing flow** — on the home page, tick **both**
   *OCR + Table + current PII* and *New PII Benchmark*, then Run. The
   existing /runs page renders the OCR/table cards; an inline **PII
   benchmark · paired run** section drops in once detectors start
   completing. Each OCR card carries a 🔗 *pii benchmark* chip to the
   full dashboard at `/pii-benchmarks/<id>`. **OCR is executed exactly
   once** — the PII track reuses results from the paired /runs.

2. **PII benchmark alone** — tick only *New PII Benchmark*. Lands directly
   on `/pii-benchmarks/<id>`. Producers run inside the PII track only
   (stored under `storage/pii_runs/<id>/<doc_id>/_producers/`).

3. **JSONL dataset benchmark** — for offline evaluation against an
   annotated dataset. Navigate to `/pii-benchmarks/dataset`. Upload a
   JSONL file (one record per line: `id`, `text`, `entities[]`) and pick
   detectors. Generate a synthetic 500-record UK-banking sample with:

   ```bash
   cd backend
   uv run python -m scripts.generate_pii_dataset --count 500 --out ../data/pii_v2/synthetic_500.jsonl
   ```

   Reports land in `storage/pii_runs/_dataset_runs/<id>/`:
   `report.json`, `report.md`, `false_positives.csv`,
   `false_negatives.csv` per detector, and a production-recommendation
   matrix (winner per F1 / recall / precision / p95 latency).

### 6b.6 Dashboard UX

`/pii-benchmarks/<id>` renders one card per (OCR × detector) pair per page,
with a filter bar above the grid:

- **Group by**: OCR producer (default), Detector, or flat.
- **Status filter**: all / ok / skipped / error (with live counts).
- **OCR filter** and **Detector filter** popovers — multi-select.

Each card shows: status pill, entity-type counts, latency, and expands to
a span table (`type`, `value`, `score`, `risk_level`). Cards that didn't
produce text (producer unregistered, doesn't support the doc kind, errored,
or returned an empty result) render as **skipped** with the reason
inline — that's why every selected producer always shows a row even when
its detection didn't run.

### 6b.7 Operational notes

- **Memory**: detectors run in-process for `presidio_regex` and
  `presidio_spacy` (cheap). `gliner` and `piiranha` run in fresh
  subprocesses per detection — each spawn loads + drops the model so peak
  RAM is bounded by `RAM_PER_SOLUTION_GB` (§6a). For long batches consider
  pre-loading the models into a single long-lived subprocess in a future
  iteration.
- **Subprocess timeout**: each ML worker is capped at 30 s
  (`pii_v2/subprocess_detector.py:call_worker(timeout_sec=30.0)`). Raise it
  in code for slow CPUs.
- **Subprocess unavailability cache**: once a worker fails with
  `ModuleNotFoundError`, `ImportError`, or a SSL/network error during model
  download, it's cached as unavailable for the rest of the process — the
  hybrid detector then falls back to the next contextual candidate without
  re-spawning. Cache resets on backend restart.
- **No raw PII in logs**: detectors and the runner log entity *counts* and
  jurisdictions only. The encrypted token map (existing PresidioPII path)
  still uses `PII_MASK_KEY`; the new track does not write a token map by
  default — masking is opt-in via `pii_v2/masking.py` when consumed
  downstream.

### 6b.8 Adding a new jurisdiction

Drop a new module under `backend/app/pii_v2/jurisdictions/<code>/`
mirroring the `uk/` layout: `__init__.py` (plugin), `recognizers.py`
(regex specs), `validators.py` (checksums). Register it in
`backend/app/pii_v2/jurisdictions/__init__.py::PLUGINS`. Set
`PII_V2_DEFAULT_JURISDICTIONS` in `.env` to include the new code, or pass
`jurisdictions=[...]` in `POST /pii-benchmarks/runs`.

### 6b.9 Adding a new detector

```python
# backend/app/pii_v2/detectors/my_detector.py
from app.pii_v2.base import BaseDetector
from app.pii_v2.registry import register_detector
from app.pii_v2.schema import PIIEntity

@register_detector
class MyDetector(BaseDetector):
    name = "my_detector"
    display_name = "My new detector"
    description = "Short blurb"

    def detect(self, text: str) -> list[PIIEntity]:
        ...
        return [PIIEntity(...)]
```

Import the module from `backend/app/pii_v2/detectors/__init__.py` so it
registers at startup. The detector immediately becomes available in the
home-page run flow, the dashboard's filter popover, and the JSONL
benchmark runner — no other wiring needed.

### 6b.10 Testing each track end-to-end

Verify every track returns entities on a known sample. Run from `backend/`
with the venv active:

**Track A — Presidio + UK/banking regex**:

```bash
uv run python -c "
from app.pii_v2.detectors.presidio_regex_detector import PresidioRegexDetector
det = PresidioRegexDetector(jurisdictions=['GLOBAL_COMMON','UK'])
text = 'Account 12345678 sort code 12-34-56. NI: AB 12 34 56 C. john@example.com.'
for e in det.detect(text):
    print(f'  {e.entity_type:30} {e.score:.2f} \"{e.text}\"')
"
```

Expected: UK_BANK_ACCOUNT_NUMBER, UK_SORT_CODE, UK_NATIONAL_INSURANCE_NUMBER, EMAIL_ADDRESS.

**Track B — Presidio + spaCy NER**:

```bash
uv run python -c "
from app.pii_v2.detectors.presidio_spacy_detector import PresidioSpacyDetector
det = PresidioSpacyDetector(jurisdictions=['GLOBAL_COMMON','UK'])
for e in det.detect('Customer John Smith called from London.'):
    print(f'  {e.entity_type:30} {e.score:.2f} \"{e.text}\"')
"
```

Expected: PERSON ("John Smith"), LOCATION ("London"). If they're missing,
the spaCy model isn't installed — run `python -m spacy download en_core_web_sm`.

**Track C — GLiNER**:

```bash
uv run python -c "
from app.pii_v2.detectors.gliner_detector import GLiNERDetector
det = GLiNERDetector(jurisdictions=['GLOBAL_COMMON','UK'])
for e in det.detect('John Smith lives at 10 Downing Street, London SW1A 2AA.'):
    print(f'  {e.entity_type:30} {e.score:.2f} \"{e.text}\"')
"
```

Expected: PERSON, UK_ADDRESS, UK_POSTCODE. If the worker errors with
ModuleNotFoundError, `uv pip install gliner`. If it errors with
"unable to load … offline mode", run `python -m scripts.prefetch_pii_models`.

**Track D — Piiranha**:

```bash
uv run python -c "
from app.pii_v2.detectors.piiranha_detector import PiiranhaDetector
det = PiiranhaDetector(jurisdictions=['GLOBAL_COMMON','UK'])
for e in det.detect('Customer John Smith, +44 7700 900123, NI: AB 12 34 56 C.'):
    print(f'  {e.entity_type:30} {e.score:.2f} \"{e.text}\"')
"
```

Expected: UK_PHONE_NUMBER, UK_NATIONAL_INSURANCE_NUMBER (Piiranha labels
mapped to UK taxonomy via `pii_v2/workers/pii_piiranha_worker.py`).

**Track E — Hybrid**:

```bash
uv run python -c "
from app.pii_v2.detectors.hybrid_detector import HybridDetector
det = HybridDetector(jurisdictions=['GLOBAL_COMMON','UK'])
text = 'John Smith, 10 Downing Street, London SW1A 2AA. +44 7700 900123. NI: AB 12 34 56 C. Account 12345678 sort 12-34-56.'
for e in det.detect(text):
    print(f'  {e.entity_type:30} {e.score:.2f} risk={e.risk_level} \"{e.text}\"')
"
```

Expected: 7–8 entities combining structured (account/sort code/NINO) and
contextual (PERSON, UK_ADDRESS). When all of GLiNER/Piiranha/spaCy fail to
load, hybrid degrades to regex-only — that's the fallback path, not a bug.

**Full 5-detector benchmark** (CLI):

```bash
# Generate a 50-record synthetic dataset
uv run python -m scripts.generate_pii_dataset --count 50 --out ../data/pii_v2/synthetic_50.jsonl

# Run all 5 detectors and print metrics
uv run python -m scripts.run_pii_benchmark --dataset ../data/pii_v2/synthetic_50.jsonl \
  --detectors presidio_regex,presidio_spacy,gliner,piiranha,hybrid
```

The CLI returns precision/recall/F1/p50/p95 per detector and the
production-recommendation matrix. The same data is rendered at
`/pii-benchmarks/dataset/<id>` when the benchmark is launched from the UI.

### 6b.11 Card-level enhancements (capability, image, audit, feedback)

Each `(OCR × detector)` card on `/pii-benchmarks/<id>` exposes four drill-downs
and a manual-annotation workflow:

| Button / chip | What it shows |
|---|---|
| `▸ spans` | Per-entity table with type, value, score, risk_level |
| `▸ occurrences` | Per (text, entity_type) rollup with page/doc counts split by discovery (`lib` / `search_only` / `manual_only` / `both`) |
| `▸ audit` | Per-detector audit timeline: `normalize → regex_detect → merge → risk → substring_search → fallback_search → manual_overlay → occurrence_count`, each with ms + input/output counts |
| `🛈 caps` | Detector capability modal: full entity-type taxonomy, supported jurisdictions, validators per type, config-knob list |
| `🖼 image` | Page-image modal with PII bboxes overlaid (resolved from char-offset spans via the per-region text layout). Supports prev/next page navigation, per-category overlay toggles (PII / Network / Location / Visual / Manual), and a 50-overlay cap (env `PII_V2_MAX_OVERLAYS`) |
| `+N manual` chip | The user added N annotations on this page that the detector missed |
| `+N search` chip | The post-process fallback search found N additional occurrences that the detector didn't return |

#### Image modal · manual annotation feedback loop

In the image modal, click **`✎ annotate`** to enter box-draw mode, drag a
rectangle around a missed PII span, choose its entity type, type the
underlying value, and save. By default the annotation is **doc-scoped** —
it persists across runs of the same document AND is promoted into a
global `USER_CUSTOM` jurisdiction dictionary so subsequent
`presidio_regex` runs on any document will detect that exact string.
Tick **"keep just for this run"** to opt out of the dictionary promotion.

Custom dictionary location:

```
backend/storage/pii_runs/_custom_dictionary/USER_CUSTOM.json
```

Each row: `{entity_type, text, added_from, created_at}`. Edit by hand to
adjust scores / remove entries; the regex detector reloads it on every
detection call.

#### New top-level dashboard sections

Per page, the `/pii-benchmarks/<id>` dashboard now renders **four** sections
depending on what was detected:

1. **PII identifiers** — the existing card grid (PERSON, UK_*, etc.)
2. **Network identifiers** — `EMAIL_ADDRESS`, `URL`
3. **Location identifiers** — `LAT_LONG_PAIR`, `MAP_URL_GOOGLE`, `MAP_URL_APPLE`, `MAP_URL_OSM`
4. **Visual identifiers** — QR codes (always) + barcodes (when `[pii-v2-visual]` extras installed)

Sections 2–3 use the same `(OCR × detector)` card grid filtered by category.
Section 4 is image-based (one card per decoded code, with payload + pixel bbox).

#### Visual extras install (QR always; barcodes optional)

QR detection works out of the box (`cv2.QRCodeDetector` is in core deps).
For 1D barcode decoding install the optional extras:

```bash
# macOS
brew install zbar
cd backend && uv pip install -e ".[pii-v2-visual]"

# Linux (Debian/Ubuntu)
sudo apt-get install libzbar0
cd backend && uv pip install -e ".[pii-v2-visual]"
```

When `pyzbar` isn't installed, the Visual identifiers section gracefully
shows `barcode: skipped — pyzbar not installed` without breaking the rest of
the page.

#### New env knobs (add to `backend/.env`)

```dotenv
# Cap on bboxes rendered simultaneously in the image annotation modal.
PII_V2_MAX_OVERLAYS=50

# Confidence assigned to USER_CUSTOM exact-string recognisers built from
# user manual annotations. Lower this if the feedback loop is too aggressive.
PII_V2_USER_CUSTOM_SCORE=0.85

# Enable / disable the QR + barcode extractor pipeline.
PII_V2_VISUAL_ENABLED=true
```

### 6b.12 Post-detection redaction (mock data + side-by-side UI)

After every `(OCR × detector)` cell finishes detection, the runner now
produces a **same-length redaction** of its text + image so the result is
safe to send to an LLM. The original ↔ mock mapping is preserved in an
encrypted file for a later restore step.

#### What gets produced

Per cell, under
`backend/storage/pii_runs/<id>/<doc>/page-NNN/<ocr>/<detector>/redaction/`:

| File | Purpose |
|---|---|
| `redacted_text.txt` | Page text with every PII span replaced by a mock value of identical character length |
| `redacted_page.png` | Page image with every PII bbox white-filled and the mock text drawn in place (only when the page image is available) |
| `diff.json` | List of `{start, end, original, mock, entity_type, bbox_px}` driving the side-by-side UI |
| `mapping.fernet` | Fernet-encrypted JSON of `{mock: original}` — keep this for the restore step |
| `mapping.index.json` | Plaintext-safe metadata (entity-type counts only) |

The redactor is **deterministic within a `pii_run`** — the same value
detected on multiple pages or by multiple `(OCR × detector)` cells gets
the **same mock everywhere**, so the document-level mapping is small and
stable. A fresh `pii_run` (re-run on the home page) regenerates the
mapping with fresh randomness, so leaking one run's mapping doesn't
compromise another.

#### Install the optional Faker dep (recommended)

Faker gives a UK-locale name/organisation/address pool. Without it the
pipeline falls back to a built-in dictionary in
`backend/app/pii_v2/redaction/_fallback_names.py` — every entity still
gets a same-length mock, just from a smaller pool.

```bash
cd backend
uv pip install -e ".[pii-v2-redaction]"
```

#### Same-length invariant per entity type

| Entity type | Strategy |
|---|---|
| `PERSON` | Faker `name()` filtered by length; built-in name pool fallback |
| `ORGANISATION` | Curated UK org name pool, length-bucketed |
| `UK_ADDRESS` | Faker `street_address()` filtered by length; padded `"<n> <street>, <city>"` fallback |
| `EMAIL_ADDRESS` | Random local part + same-length domain (`mail.co.uk` family) |
| `UK_POSTCODE` | Letter→letter, digit→digit replacement preserving the original mask |
| `UK_NATIONAL_INSURANCE_NUMBER` | Valid NINO prefix (no `BG`/`GB`/`KN`/`NK`/`NT`/`TN`/`ZZ`) + 6 digits + `[A-D]` suffix |
| `UK_SORT_CODE` / `UK_BANK_ACCOUNT_NUMBER` | Digits randomised; separators preserved |
| `UK_IBAN` | `GB##...` — preserve country code, randomise rest position-preservingly |
| `UK_PHONE_NUMBER` / `CREDIT_CARD_NUMBER` / `LAT_LONG_PAIR` | Position-preserving digit/letter replacement |
| `URL` / `MAP_URL_*` | Scheme preserved; body randomised position-preservingly |
| Fallback for unknown types | Position-preserving structural replacement |

The runner enforces the same-length invariant — any generator that returns
the wrong length gets length-corrected with a warning log so downstream
image redaction never overflows the original bbox.

#### env knobs (`backend/.env`)

```dotenv
# Master switch. When false the runner skips the redaction step entirely.
PII_V2_REDACTION_ENABLED=true

# Optional override for the TrueType font used to draw mock text on the
# redacted image. Defaults to system fonts (Arial/DejaVuSans/Helvetica)
# auto-discovered on macOS / Linux. Pillow's bitmap fallback also works.
PII_V2_REDACTION_FONT_PATH=
```

#### Reading the redaction in the UI

On `/pii-benchmarks/<id>`, every cell card with detected PII shows a
purple **🛡 redacted: N** chip. Clicking it opens the side panel pre-
selected on the **🛡 redaction** tab, which renders three sections:

1. **Side-by-side text** — original on the left, redacted on the right.
   PII spans on each side are coloured by category; hovering reveals the
   `original → mock` pair.
2. **Side-by-side image** — original page image with PII bboxes drawn in
   red, redacted page image with the same bboxes in green so you can see
   *where* the mock text now lives.
3. **Mapping table** — collapsed by default. Click **👁 reveal originals**
   to expand. Each row shows `entity_type · original · mock · occurrences`.
   The 🔻 button next to the table downloads `mapping.fernet` for the
   restore step.

#### Routes

```
GET  /pii-benchmarks/{id}/redaction/{doc}/{page}/{ocr}/{detector}
       → { redacted_text, diff_spans, mapping_index, has_image }
GET  /pii-benchmarks/{id}/redaction/{doc}/{page}/{ocr}/{detector}/image
       → image/png bytes of the redacted page
GET  /pii-benchmarks/{id}/redaction/{doc}/{page}/{ocr}/{detector}/mapping
       → mapping index (default); ?reveal=true returns the Fernet ciphertext
```

The mapping endpoint never decrypts server-side — the client downloads the
ciphertext and the holder of `PII_MASK_KEY` decrypts locally. This keeps
the key off the wire and makes the restore step (out of scope for this
round) trivially client-side.

#### How this fits the LLM benchmarking loop

The downstream LLM call uses **either** the redacted text **or** the
redacted image (or both) — no original PII ever leaves the box. After
the LLM returns its result, a future restore step uses
`mapping.fernet` to swap each mock token back to its original value
before the next pipeline stage processes the output.

---

**Full 5-track UI walkthrough**:

1. Start backend + frontend (§0d).
2. Upload a PDF on the home page (or pick an existing one).
3. Tick **both** *OCR + Table + current PII* and *New PII Benchmark*.
4. Click Run. The page routes to `/runs/<id>` and the existing solution
   cards stream in. As soon as the OCR producers finish, the **PII
   benchmark · paired run** section below the cards starts populating —
   one card per (OCR × detector) pair, grouped by OCR producer by default.
5. Switch the **group by** filter to *Detector* to see Track A/B/C/D/E
   side-by-side per OCR engine.
6. Click 🔗 *pii benchmark* on any OCR card to deep-link into the full
   `/pii-benchmarks/<id>` dashboard.

---

## 6. Configuration variations

The harness exposes per-stage parameters that you can override either by
editing the matching `app/solutions/<name>.py` file (clean way) or by
constructing the stage with custom params in a Python session (ad-hoc way).
All variations work on Apple Silicon unless otherwise noted.

### PaddleOCR baseline

```python
PaddleOCRStage(params={
    "ocr_version": "PP-OCRv4",  # default. Switch to "PP-OCRv5" for newer weights — needs ≥16 GB RAM on Mac
    "lang": "en",               # any paddleocr lang code
})
```

### Layout-Parser

```python
LayoutParserStage(params={
    "backend": "paddle",        # default. "detectron2" requires manual Detectron2 install
    "score_threshold": 0.5,     # detection confidence threshold (raise for fewer, higher-confidence boxes)
    "model_config": "lp://PubLayNet/ppyolov2_r50vd_dcn_365e/config",
    # Alternative PubLayNet variants:
    #   lp://PubLayNet/mask_rcnn_X_101_32x8d_FPN_3x/config   (Detectron2, larger / slower / more accurate)
    #   lp://HJDataset/faster_rcnn_R_50_FPN_3x/config        (Japanese historical layouts)
    #   lp://PrimaLayout/mask_rcnn_R_50_FPN_3x/config        (scientific paper layouts)
    "label_map": {0: "Text", 1: "Title", 2: "List", 3: "Table", 4: "Figure"},
})
```

### RAGFlow deepdoc

```python
DeepdocStage(params={
    "ocr_backend": "default",            # one of: default | tesseract | easyocr | doctr | paddle
    "layout_score_threshold": 0.4,       # min confidence for LayoutRecognizer detections
})
```

Each solution file (`deepdoc_baseline.py` and the 4 variants) hard-codes
`ocr_backend`. To benchmark another backend ad-hoc, construct
`DeepdocStage(params={"ocr_backend": "<name>"})` directly. Adding a new
backend takes ~80 lines in `backend/app/stages/ocr/deepdoc_adapters.py`.

### TrOCR

```python
TrOCRStage(params={
    "model_id": "microsoft/trocr-base-handwritten",  # or "microsoft/trocr-base-printed"
    "mode": "handwritten",                            # or "printed" — controls output region type tag
    "lang": "en",                                     # passed to EasyOCR detector only
})
```

Other TrOCR weights you can pass to `model_id`:

- `microsoft/trocr-large-handwritten` — higher accuracy, ~1.3 GB instead of 600 MB
- `microsoft/trocr-large-printed` — same trade-off for printed text
- `microsoft/trocr-small-handwritten` / `-small-printed` — ~250 MB, lower quality

### Doc-format heuristic thresholds

The bucket cut-offs live in `backend/app/stages/layout/doc_format.py` —
`classify_page()`. Defaults:

| Threshold | Default | Meaning |
|---|---|---|
| `tables_frac >= 0.35` → `tabular-heavy` | 0.35 | Area-fraction of TABLE-family regions |
| `figures_frac >= 0.35` → `image-heavy` | 0.35 | Area-fraction of IMAGE regions |
| `n_headings >= 5 AND tables < 0.20` → `form-like` | 5 / 0.20 | Heading count + low table density |
| `text_frac >= 0.70` → `narrative` | 0.70 | Mostly text |
| else | `mixed` | Catch-all |

Tune these if your corpus has different layout characteristics. The pill +
tooltip on each card show the actual per-bucket fractions for inspection.

### Layout-Parser authoritative vs. shared

Layout-Parser writes `page.doc_format` directly from its own classification.
The shared `DocFormatStage` only sets the field **if it's empty**, so
running both stages in the same pipeline keeps the Layout-Parser label.
When `DocFormatStage` runs on a card that doesn't include Layout-Parser
(e.g. `paddle_structure`), it derives the label from that solution's own
region distribution.

### Run-time DPI / page sampling

In `backend/.env`:

```dotenv
DEFAULT_DPI=300       # raster DPI for OCR-style solutions (raise for higher fidelity, slower)
VISION_DPI=200        # raster DPI for vision-LLM solutions (keep low — token cost scales with image size)
```

### Native PDF auto-skip behavior

`native_pymupdf` and `native_pdfplumber` declare `supported_kinds={"vector"}`.
The runner auto-skips them on scanned / mixed PDFs with status `skipped`
and a `not applicable: document is not native` reason. No override needed —
to force-run on a scanned PDF, edit `supported_kinds` in the solution file.

---

## 7. Risk register / known gotchas

| Symptom | Cause | Fix |
|---|---|---|
| Frontend shows API errors / empty lists | Backend not running on port 8002 | Start backend in a separate terminal (§0d) |
| `ECONNREFUSED` on `/api/*` | Backend down or wrong `BACKEND_URL` | Confirm `curl http://127.0.0.1:8002/solutions` works; default proxy target is `http://localhost:8002` |
| `ModuleNotFoundError: camelot` at runtime | `[tables-vector]` extra not installed | `pip install -e ".[tables-vector]"` |
| `gs: command not found` from Camelot | Ghostscript not on PATH | `brew install ghostscript` |
| `JAVA_HOME` warnings from Tabula | OpenJDK not discoverable | `export JAVA_HOME=$(brew --prefix openjdk)/libexec/openjdk.jdk/Contents/Home` |
| `ModuleNotFoundError: img2table` | `[tables-img]` not installed | `pip install -e ".[tables-img]"` |
| `ModuleNotFoundError: easyocr` | `[ocr-easy]` not installed | `pip install -e ".[ocr-easy]"` |
| `ModuleNotFoundError: doctr` | `[ocr-doctr]` not installed | `pip install -e ".[ocr-doctr]"` |
| `openai package not installed` | `[llm-openai]` extra not installed | `pip install -e ".[llm-openai]"` |
| `google-generativeai not installed` | `[llm-gemini]` extra not installed | `pip install -e ".[llm-gemini]"` |
| `GEMINI_API_KEY is not configured` | Key missing from `.env` | Set `GEMINI_API_KEY` in `backend/.env` |
| `A dependency error occurred during pipeline creation` (Paddle) | `paddlex[ocr]` extras missing | `PADDLEX_VER=$(pip show paddlex \| awk '/^Version/{print $2}'); pip install "paddlex[ocr]==${PADDLEX_VER}"` |
| `No available model hosting platforms detected` (Paddle) | Outbound HTTPS to Paddle CDN blocked | The stage sets `SSL_CERT_FILE` to Homebrew's bundle automatically; if still blocked, download `~/.paddlex/official_models/` on a connected machine and copy over |
| `worker exited -9 (SIGKILL — OOM killer)` | Paddle server models + other apps exhaust RAM | Close other apps; the stage already disables formula/seal/chart/region sub-models. For 8 GB Macs run paddle in isolation |
| `paddle_structure` stuck in "processing" for >10 min | Server-tier models running on CPU at ~1 fps | Expected on CPU-only machines; the timeout is 10 min. Use a GPU-enabled machine for practical throughput |
| `CERTIFICATE_VERIFY_FAILED` from a Python worker | certifi missing a root that Homebrew's OpenSSL trusts | `export SSL_CERT_FILE=/opt/homebrew/etc/openssl@3/cert.pem REQUESTS_CA_BUNDLE=/opt/homebrew/etc/openssl@3/cert.pem` |
| `Cannot convert a MPS Tensor to float64` (docling) | float64 op on MPS backend | The `vision_docling` stage forces CPU; for ad-hoc scripts: set `PYTORCH_ENABLE_MPS_FALLBACK=1` |
| `JSONDecodeError` from `vision_claude/openai/gemini` | LLM output had malformed JSON | The parser self-heals via `json-repair`; if still failing raise `ANTHROPIC_MAX_TOKENS` and inspect `runs/<id>/*/artifacts/vision/page-NNN-raw.txt` |
| `worker app.workers.paddleocr_worker exited -9 (SIGKILL — OOM)` | paddleocr 3.x defaults to PP-OCRv5_mobile which peaks > 8 GB during recognition | The stage already pins `params.ocr_version="PP-OCRv4"` + 1 thread per native pool. To opt into v5 anyway: `PaddleOCRStage(params={"ocr_version": "PP-OCRv5", "lang": "en"})` |
| `AttributeError: module layoutparser has no attribute Detectron2LayoutModel` | Detectron2 isn't installed (no wheel for macOS arm64) | Worker defaults to `params.backend="paddle"` (PaddleDetectionLayoutModel) which works without Detectron2. To force Detectron2: install it manually (see §2b — Layout-Parser) and pass `params={"backend": "detectron2"}` |
| `RuntimeError: Cannot send a request, as the client has been closed` (TrOCR) | `transformers>=5` pulls `huggingface_hub>=1` whose new httpx client closes itself before the first request | The `[ocr-trocr]` extras pin `transformers<5` + `huggingface_hub<1`. If you accidentally upgraded: `pip install -e ".[ocr-trocr]" --force-reinstall` |
| `OSError: Can't load processor for 'microsoft/trocr-base-…'` | Either the transformers/hf_hub regression above, OR SSL cert failure on the HF CDN | Confirm versions (`pip show transformers huggingface_hub`); if version is correct, the stage already exports `SSL_CERT_FILE` to Homebrew's OpenSSL bundle automatically |
| `SSLCertVerificationError` from a TrOCR / Layout-Parser worker | Homebrew OpenSSL bundle not found at expected path | Install Homebrew OpenSSL: `brew install openssl@3` — the stages auto-discover `/opt/homebrew/etc/openssl@3/cert.pem` |
| `format: tabular-heavy` pill missing on a card | Either no regions emitted yet, or the solution doesn't run a layout-emitting stage | `DocFormatStage` is wired into `paddle_structure`, `docling`, `claude_vision`, `openai_vision`, `gemini_vision`, `layout_parser`, `layout_parser_pdf`, all `deepdoc_*`. Other solutions (raw OCR baselines) don't emit layout regions and therefore no format label |
| `ModuleNotFoundError: deepdoc` from a worker | `[ocr-deepdoc]` extras not installed, or the vendor directory was moved | Run `pip install -e ".[ocr-deepdoc]"` and confirm `backend/vendor/deepdoc/vision/` exists. The worker prepends `backend/vendor/` and `backend/vendor/_ragflow_stubs/` to `sys.path`; both must be on disk |
| deepdoc card stuck "Processing…" >5 min on first run | First-time download of ~250 MB ONNX weights from Hugging Face | Wait — subsequent runs use the `~/.cache/ragflow/rag/res/deepdoc/` cache. If outbound HTTPS is blocked, pre-populate the cache directory on a connected machine |
| `module beartype.claw not found` from deepdoc | Stale vendored `__init__.py` still importing upstream's runtime type-checker | The vendored `backend/vendor/deepdoc/__init__.py` is intentionally a no-op; if you regenerated from upstream, re-apply the patch (see `vendor/VENDORED_FROM.md`) |
| `Cannot load library libpangoft2-1.0.0.dylib` (WeasyPrint) | pango/cairo not installed | `brew install pango cairo libffi` |
| `PII_MASK_KEY not set — token map stored unencrypted` | Key not configured | Set `PII_MASK_KEY` in `.env` (see §2c) |
| spaCy model load error | `en_core_web_lg` not downloaded | `python -m spacy download en_core_web_lg` |
| `/pii-benchmarks/<id>` cards stuck on `pending` | OCR producer name in `PII_V2_TEXT_PRODUCERS` doesn't match the registry | Use registered names (`native_pymupdf`, not `pymupdf_native`; `ocr_tesseract_baseline`, not `tesseract_baseline`; `trocr_printed`, not `trocr_baseline`). Check `curl http://127.0.0.1:8002/solutions` for valid names |
| `/pii-benchmarks/<id>` cards show `skipped — no text in regions` | Producer ran but emitted no `Region.text` (typical for `native_pymupdf` on a scanned PDF) | Expected — keep the producer in the list; it'll work on vector PDFs. To suppress the row, remove the producer name from `PII_V2_TEXT_PRODUCERS` |
| `gliner` detector shows `skipped — worker exited 2: ModuleNotFoundError` | `gliner` not installed in the backend venv | `cd backend && uv pip install "gliner>=0.2"` — see §6b.3. After the first failure the worker is cached as unavailable for the rest of the process; restart the backend after installing |
| `piiranha` detector errors `OSError: We couldn't connect to 'https://huggingface.co'` | Subprocess running with `HF_HUB_OFFLINE=1` and the model isn't cached locally | Either pre-download with `HF_HUB_OFFLINE=0 uv run python -c "from transformers import pipeline; pipeline('token-classification', model='iiiorg/piiranha-v1-detect-personal-information')"` on a connected machine, or set `HF_HUB_OFFLINE=0` in `backend/.env` to let the worker fetch on first call |
| `hybrid` detector results identical to `presidio_regex` | All contextual candidates (GLiNER, Piiranha, spaCy) are unavailable in this process | Install at least one — see §6b.3 — and restart the backend so the subprocess-unavailability cache resets |
| OCR running twice when both flows are selected on home page | Paired-run lookup failed; PII track fell back to re-running producers | Confirm `paired_run_ids` is set in `POST /pii-benchmarks/runs` (the home page wires it automatically — only an issue when calling the API directly). The PII runner logs `"falling back to running producers"` at INFO when the paired run had no usable text |

---

## 8. Tearing down

```bash
rm -rf backend/.venv frontend/node_modules   # project-local only
```

Only the Homebrew packages in §1 are system-wide; Homebrew owns those
(`brew uninstall tesseract ghostscript openjdk ...`).

Model weight caches:

```bash
rm -rf ~/.paddlex ~/.paddledet ~/.cache/docling ~/.cache/huggingface \
       ~/.cache/layoutparser ~/.EasyOCR ~/.cache/doctr_cache \
       ~/.cache/ragflow
```

The `~/.cache/huggingface` removal also clears the TrOCR (handwritten + printed)
model weights and the layout-parser HF assets.
