# Setup — Linux (x86_64 / arm64)

End-to-end install for `sof-table-extract` on Linux. Tested on Ubuntu 22.04 /
24.04, Debian 12, and Amazon Linux 2023 (x86_64). Most of this also works on
Linux arm64 (e.g. AWS Graviton, Raspberry Pi 5) with a few notes called out
where wheels differ.

For macOS (Apple Silicon), see **[SETUP.md](./SETUP.md)** — most steps overlap
but the system prerequisites and a few ML wheels differ.

Everything except the system prerequisites lives inside per-folder
`backend/.venv` and `frontend/node_modules` — nothing is installed globally.

---

## 0. Quick start (local dev)

### 0a. Check toolchain

```bash
python3.12 --version   # 3.12.x — install via deadsnakes on Ubuntu if missing
node --version         # 22.x or newer (see §0c for nvm install)
npm --version
tesseract --version    # 5.x — install via §1 if missing
```

If Python 3.12 isn't your default, install it (Ubuntu/Debian):

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
```

### 0b. One-time backend setup

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate

pip install -U pip setuptools wheel
pip install -e .
python -m spacy download en_core_web_lg   # ~500 MB; required by Presidio PII stage

cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY if you want claude_vision
```

**Minimal local profile** (fastest install; OCR + Claude Vision):

```bash
pip install -e .
python -m spacy download en_core_web_lg
```

Unlocks: `ocr_tesseract_baseline`, `opencv_tesseract`, `claude_vision` (with `ANTHROPIC_API_KEY`), plus `native_pymupdf` (no extras needed).

**Recommended local profile** (most solutions without the heaviest ML deps):

```bash
pip install -e ".[phase2-light,llm-openai,llm-gemini,native-pdfplumber]"
python -m spacy download en_core_web_lg
```

Also unlocks: Camelot, Tabula, img2table, EasyOCR, DocTR, the OpenAI/Gemini
vision providers (when API keys are set), and pdfplumber. See §2b for the
full optional-group list.

### 0c. One-time frontend setup

If Node 22+ isn't installed, use `nvm`:

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
exec $SHELL
nvm install 22
nvm use 22
```

Then:

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

Open <http://localhost:3000>.

### 0e. Smoke-test

```bash
curl -s http://127.0.0.1:8002/solutions | python3 -m json.tool
curl -s http://127.0.0.1:8002/documents | python3 -m json.tool
```

---

## 1. System prerequisites

These are **not** pip-installable. Install them before `pip install`.

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y \
    tesseract-ocr libtesseract-dev \
    poppler-utils \
    ghostscript \
    default-jdk \
    libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libffi-dev \
    libgl1 libglib2.0-0 \
    build-essential pkg-config
```

### Fedora / RHEL / Amazon Linux 2023

```bash
sudo dnf install -y \
    tesseract tesseract-devel \
    poppler-utils \
    ghostscript \
    java-21-openjdk \
    pango cairo libffi-devel \
    mesa-libGL glib2 \
    gcc gcc-c++ pkgconfig make
```

### Arch / Manjaro

```bash
sudo pacman -S --needed \
    tesseract poppler ghostscript jdk-openjdk \
    pango cairo libffi \
    glibc gcc pkgconf
```

### Why each one

| Package | Why it's needed | Required by |
|---|---|---|
| `tesseract-ocr` (and `-dev`) | OCR engine binary + headers for `pytesseract` | every OCR solution |
| `poppler-utils` | optional PDF rasterizer (`pdftoppm`) | `img2table_*` fallback |
| `ghostscript` | rasterizes vector PDFs for Camelot | `[tables-vector]` (Camelot) |
| `default-jdk` / `java-21-openjdk` | JVM that `tabula-py` invokes | `[tables-vector]` (Tabula) |
| `libpango-1.0-0`, `libcairo2`, `libffi-dev` | text shaping + PDF backends for WeasyPrint | report PDF export |
| `libgl1` | OpenCV / paddle native libs | `opencv_tesseract`, paddle solutions |
| `build-essential` / `gcc` | building any wheel that lacks a manylinux binary | some optional extras |

**Minimal local dev** needs only `tesseract-ocr`. Install the rest when you
add the matching optional solution groups.

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
python -m spacy download en_core_web_lg   # ~500 MB
```

This gives you the core solutions that need no optional extras:

| Solution | What it does |
|---|---|
| `ocr_tesseract_baseline` | Raw Tesseract OCR |
| `opencv_tesseract` | OpenCV pre-processing + Tesseract |
| `claude_vision` | Structured JSON extraction via Claude (needs `ANTHROPIC_API_KEY`) |
| `native_pymupdf` | Native PDF text + table extraction via PyMuPDF |

### 2b. Install optional solution groups

Each group is independent — install only what you'll use. Model weights are
downloaded on first run (not at install time); see §4 for sizes.

#### LLM vision providers

```bash
pip install -e ".[llm-openai]"   # openai_vision (needs OPENAI_API_KEY)
pip install -e ".[llm-gemini]"   # gemini_vision (needs GEMINI_API_KEY)
```

#### img2table — rasterized-page table detection

```bash
pip install -e ".[tables-img]"
```

Unlocks: `img2table_tesseract`, `img2table_easyocr`, `img2table_doctr`, `img2table_paddle`

#### Camelot + Tabula — vector-PDF table extraction

Requires `ghostscript` and a JDK from §1.

```bash
pip install -e ".[tables-vector]"
```

If `tabula-py` can't find Java, set `JAVA_HOME`:

```bash
# Ubuntu / Debian — default-jdk lives at /usr/lib/jvm/default-java
export JAVA_HOME=/usr/lib/jvm/default-java
```

Unlocks: `camelot_vector`, `camelot_lattice`, `camelot_stream`, `tabula_vector`, `tabula_lattice`, `tabula_stream`

#### EasyOCR — alternative OCR baseline

```bash
pip install -e ".[ocr-easy]"
```

#### DocTR — alternative OCR baseline

```bash
pip install -e ".[ocr-doctr]"
```

#### PaddleOCR PP-StructureV3 — layout + table + OCR

```bash
pip install -e ".[ocr-paddle]"
PADDLEX_VER=$(pip show paddlex | awk '/^Version/{print $2}')
pip install "paddlex[ocr]==${PADDLEX_VER}"
```

Unlocks: `paddle_structure`, `img2table_paddle`, and (transitively) the
detector used by `trocr_*`.

**CUDA on Linux.** Unlike macOS, paddlepaddle has functional GPU support on
Linux. To get the CUDA build:

```bash
pip uninstall -y paddlepaddle
pip install paddlepaddle-gpu==<version>  # match your CUDA: see paddlepaddle.org.cn
```

CUDA 12.x is the safe pick for Ubuntu 22.04+ with a Hopper / Ada / Ampere GPU.

#### Docling — IBM document layout + table

```bash
pip install -e ".[docling]"
```

PyTorch on Linux includes CUDA wheels — `pip` will pull the right one if a
GPU is visible. To force CPU-only:

```bash
pip install --index-url https://download.pytorch.org/whl/cpu torch
```

#### PaddleOCR baseline — standalone PP-OCRv4

```bash
pip install -e ".[ocr-paddle]"
```

Unlocks: `paddleocr_baseline`

Linux machines with ≥ 16 GB RAM can opt into the newer PP-OCRv5 model:

```python
PaddleOCRStage(params={"ocr_version": "PP-OCRv5", "lang": "en"})
```

(On Mac the default stays at PP-OCRv4 to avoid OOM.)

#### Native PDF — PyMuPDF + pdfplumber

```bash
# PyMuPDF (fitz) is in core deps; only install pdfplumber extras
pip install -e ".[native-pdfplumber]"
```

Unlocks: `native_pymupdf` (no extras needed), `native_pdfplumber`

#### Layout-Parser — layout detection + doc-format label

```bash
pip install -e ".[layout-parser]"
```

Unlocks: `layout_parser`

**Backend choice on Linux is *different* from macOS.** The Detectron2
backend has working wheels for Linux x86_64 — install it directly if you
want the higher-accuracy Mask R-CNN PubLayNet weights:

```bash
# CPU (Linux x86_64)
pip install 'git+https://github.com/facebookresearch/detectron2.git'

# CUDA — must match your installed PyTorch + CUDA major version
# (Example: PyTorch 2.x + CUDA 12.1)
pip install 'detectron2 @ git+https://github.com/facebookresearch/detectron2.git@v0.6'
```

Then switch backends per-run:

| `params.backend` | Backend | Linux status |
|---|---|---|
| `"paddle"` *(default)* | `PaddleDetectionLayoutModel` (PubLayNet PP-YOLOv2) | Works everywhere; reuses `[ocr-paddle]` |
| `"detectron2"` | `Detectron2LayoutModel` (PubLayNet Mask R-CNN) | ✅ Recommended on Linux — higher accuracy, GPU-accelerated |

Opt-in code:

```python
from app.stages.layout.layout_parser_stage import LayoutParserStage
LayoutParserStage(params={"backend": "detectron2", "score_threshold": 0.5})
```

The shared `DocFormatStage` (wired into `paddle_structure`, `docling`,
`claude_vision`, `openai_vision`, `gemini_vision`, `layout_parser`) lights
up the `format: …` pill on every layout-emitting card whether or not you
install `layout-parser`.

#### RAGFlow deepdoc — vendored ONNX layout + TSR + swappable OCR

Pure-ONNX pipeline vendored from
[infiniflow/ragflow](https://github.com/infiniflow/ragflow) (Apache 2.0) at
`backend/vendor/deepdoc/`. Same 5-card set as macOS — see SETUP.md §2b for
the architecture details.

```bash
pip install -e ".[ocr-deepdoc]"
```

Unlocks: `deepdoc_baseline`, `deepdoc_tesseract`, `deepdoc_easyocr`, `deepdoc_doctr`, `deepdoc_paddle`

**Linux-specific differences from macOS:**

- **GPU acceleration via ONNX Runtime.** Linux has a working
  `onnxruntime-gpu` wheel. Swap manually:
  ```bash
  pip uninstall -y onnxruntime
  pip install "onnxruntime-gpu>=1.18,<2"
  ```
  Detected automatically by deepdoc's `TextDetector` / `TextRecognizer` if
  the GPU is visible.
- **SSL trust is usually a no-op** — system CA bundle covers Hugging Face's
  CDN. The stage still calls `ssl_env_overrides()` but it's a defensive
  no-op when no Homebrew OpenSSL is found.
- **No 8 GB Mac OOM concern** — Linux servers typically have more RAM; you
  can opt PaddleOCR PP-OCRv5 back on inside `deepdoc_paddle` via
  `DeepdocStage(params={"ocr_backend": "paddle", "ocr_version": "PP-OCRv5"})`
  (requires loosening the worker — currently hard-coded to PP-OCRv4 in the
  adapter; adjust `PaddleDeepdocOCR.__init__`).

#### TrOCR — handwriting + printed-text transformer recognition

```bash
pip install -e ".[ocr-trocr]"
```

Unlocks: `trocr_handwritten`, `trocr_printed`

**Version pins.** The extras pin `transformers>=4.40,<5` +
`huggingface_hub<1` — see SETUP.md §2b for the regression rationale.
**Do not loosen these pins** even on Linux; the bug is in the libraries,
not the OS.

**GPU acceleration.** TrOCR runs ~10× faster on a CUDA GPU than CPU. If
PyTorch was installed with a CUDA wheel, the worker will pick it up
automatically — no code changes needed. To force CPU even when a GPU is
visible, set `CUDA_VISIBLE_DEVICES=` before starting the backend.

#### Convenience meta-groups

```bash
pip install -e ".[phase2-light]"                       # tables-img + tables-vector + easyocr + doctr
pip install -e ".[phase2,llm-openai,llm-gemini]"       # everything heavy: paddle + docling + all LLM providers
```

### 2c. Configure `.env`

Same as macOS — see SETUP.md §2c. Linux-specific notes:

- `JAVA_HOME` is `/usr/lib/jvm/default-java` on Ubuntu/Debian,
  `/usr/lib/jvm/jre` or `/usr/lib/jvm/java-21-openjdk` on Fedora/RHEL.
- For GPU runs, set `CUDA_VISIBLE_DEVICES=0` (or your GPU index) before
  starting the backend.

### 2d. Run

```bash
cd backend
source .venv/bin/activate
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

If you want the backend reachable from another machine, replace `127.0.0.1`
with `0.0.0.0` and open port 8002 in your firewall.

---

## 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

For a production-style deploy on Linux:

```bash
cd frontend
npm run build
npm run start         # serves on port 3000
```

Behind nginx? A minimal config:

```nginx
server {
    listen 80;
    server_name your-host.example.com;

    location /api/ {
        proxy_pass http://127.0.0.1:8002/;
    }
    location / {
        proxy_pass http://127.0.0.1:3000/;
        proxy_set_header Host $host;
    }
}
```

---

## 4. First-run model downloads

Same caches as macOS (see SETUP.md §4). One Linux difference: SSL bundles.

### SSL trust on Linux (usually nothing to do)

System trust on Linux already includes the CAs that HuggingFace,
`paddlepaddle.org.cn`, and Layout-Parser's Dropbox mirror chain through.
The subprocess stages call `ssl_env_overrides()` which scans for a system
CA bundle at:

```
/etc/ssl/cert.pem                       (some distros)
/etc/ssl/certs/ca-certificates.crt      (Debian / Ubuntu)
/opt/homebrew/etc/openssl@3/cert.pem    (Homebrew on Linux — uncommon)
/usr/local/etc/openssl@3/cert.pem
```

If none are found, the stages run with whatever `certifi` provides — which
on Linux is usually sufficient. If a worker hits `SSLCertVerificationError`:

```bash
# Ubuntu / Debian
sudo apt install -y ca-certificates
sudo update-ca-certificates
```

### GPU support

Unlike macOS (no CUDA, MPS has float64 gaps), Linux gets real GPU acceleration:

| Solution | GPU benefit |
|---|---|
| `paddle_structure`, `paddleocr_baseline`, `img2table_paddle` | 5–10× speedup with `paddlepaddle-gpu` |
| `docling` | 3–5× speedup if PyTorch CUDA wheel is installed |
| `trocr_*` | 10× speedup with PyTorch CUDA wheel |
| `easyocr_baseline`, `img2table_easyocr` | Set `gpu=True` in the worker (currently hard-coded `gpu=False`) |
| `doctr_baseline`, `img2table_doctr` | Picks up CUDA automatically when present |
| `layout_parser` (Detectron2 backend) | 5–10× speedup with CUDA wheel |

To check that PyTorch sees your GPU:

```bash
.venv/bin/python -c "import torch; print('cuda:', torch.cuda.is_available(), torch.cuda.device_count())"
```

To check paddle:

```bash
.venv/bin/python -c "import paddle; print('cuda:', paddle.is_compiled_with_cuda())"
```

---

## 5. Workflow persistence

Identical to macOS — see SETUP.md §5. The SQLite DB at
`backend/storage/workflows.db` is the only persistence layer.

---

## 6a. Memory & concurrency tuning

Same knobs as macOS — see SETUP.md §6a for the full explanation. Linux
notes:

- `psutil.virtual_memory().available` on Linux includes the file cache,
  which is fine for budgeting.
- With a 32 GB+ box you almost always want `RAM_PER_SOLUTION_GB=2.5` or
  lower to use more cores.
- GPU-accelerated solutions (when `onnxruntime-gpu` / `torch+cuda` are
  installed) shift load from CPU+RAM to VRAM. The auto-tune still uses
  system RAM as its budgeting signal; if you're GPU-bound, lower the
  divisor manually.

```dotenv
# backend/.env
MAX_CONCURRENT_SOLUTIONS=0   # 0 = auto from psutil
RAM_PER_SOLUTION_GB=2.5      # tighter on big-RAM boxes lets more run in parallel
```

Multi-document batches still run docs sequentially. Within each doc, the
auto-tuned solution-concurrency cap applies. Track live progress at
`/batches/<batch_id>`.

---

## 6. Configuration variations

Identical knobs as macOS — see SETUP.md §6. **Two Linux-only differences:**

1. **`layout_parser` defaults stay on `paddle` backend**, but switching to
   `detectron2` is the recommended path on Linux (better accuracy, real GPU
   support, install actually works). On macOS the default is forced
   because Detectron2 has no usable arm64 wheel.
2. **TrOCR uses PyTorch CUDA wheels automatically** when CUDA is visible.
   To opt back into CPU, set `CUDA_VISIBLE_DEVICES=`.

---

## 7. Risk register / known gotchas

Most macOS gotchas (SETUP.md §7) don't apply on Linux. The Linux-only ones:

| Symptom | Cause | Fix |
|---|---|---|
| `JAVA_HOME` not set / Tabula warnings | OpenJDK installed but `JAVA_HOME` unset | Ubuntu: `export JAVA_HOME=/usr/lib/jvm/default-java`; Fedora: `export JAVA_HOME=/usr/lib/jvm/java-21-openjdk` |
| `libGL.so.1: cannot open shared object file` | OpenCV / paddle native lib missing system OpenGL | Ubuntu: `sudo apt install -y libgl1`; Fedora: `sudo dnf install -y mesa-libGL` |
| `ImportError: libGLU.so.1` (some docling/paddle paths) | GLU not installed | Ubuntu: `sudo apt install -y libglu1-mesa` |
| `RuntimeError: CUDA driver version is insufficient` | Installed CUDA wheel newer than driver | `nvidia-smi` shows driver/CUDA — install matching `paddlepaddle-gpu` / `torch` wheel |
| `nvidia-smi: command not found` but GPU is present | NVIDIA driver missing | Ubuntu: `sudo ubuntu-drivers autoinstall` then reboot |
| `Could not load libcudnn_cnn_infer.so.8` | cuDNN missing | Install matching cuDNN — `apt install libcudnn8` (Ubuntu w/ NVIDIA repo) |
| `paddlepaddle-gpu` install hangs | Defaulting to the wrong CUDA wheel | Pick the explicit URL from `paddlepaddle.org.cn`; example for CUDA 12.0: `pip install paddlepaddle-gpu -i https://www.paddlepaddle.org.cn/packages/stable/cu120/` |
| Detectron2 build fails with `nvcc: command not found` | CUDA toolkit not installed (only runtime is) | `sudo apt install -y nvidia-cuda-toolkit` or use the CPU wheel |
| `_pickle.UnpicklingError` from a subprocess worker | venv Python version mismatch between parent and child | Always start the backend with the same `python3.12` that built `.venv` |
| `BrokenPipeError` from a worker | Backend killed mid-run; orphaned subprocess wrote to closed stdin | Restart backend; tune `timeout_sec` on the stage if the worker is genuinely slow |

Cross-platform gotchas (apply equally on Linux):

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: camelot` / `easyocr` / `doctr` / etc. | Install the matching extras group |
| `Cannot send a request, as the client has been closed` (TrOCR) | `pip install -e ".[ocr-trocr]" --force-reinstall` to enforce the `transformers<5` pin |
| `format: tabular-heavy` pill missing on a card | Solution doesn't run any layout-emitting stage; that's expected for raw OCR baselines |

---

## 8. Tearing down

```bash
rm -rf backend/.venv frontend/node_modules
```

Model weight caches:

```bash
rm -rf ~/.paddlex ~/.paddledet ~/.cache/docling ~/.cache/huggingface \
       ~/.cache/layoutparser ~/.EasyOCR ~/.cache/doctr_cache
```

System packages from §1 are managed by your distro's package manager; remove
them only if no other project on the machine needs them.
