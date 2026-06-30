# Vendored upstream

## RAGFlow `deepdoc/vision`

- **Upstream**: https://github.com/infiniflow/ragflow
- **Pinned commit**: `0d836afd3495` (2026-06-11)
- **License**: Apache 2.0 (see `LICENSE.ragflow`)
- **Path mapping**:
  ```
  ragflow/deepdoc/__init__.py            → vendor/deepdoc/__init__.py
  ragflow/deepdoc/vision/*.py            → vendor/deepdoc/vision/*.py
  ```

### Why vendored and not pip-installed

1. RAGFlow ships as a monorepo. Its `pyproject.toml` is configured for a full
   working tree (`packages = ['agent', 'api', 'deepdoc', ...]`) — `pip install
   git+https://github.com/infiniflow/ragflow.git` fails because pip's
   isolated build can't find `graphrag/` and similar.
2. The upstream `pyproject.toml` requires `python>=3.13,<3.15`; this repo is
   on 3.12 by design.
3. We only consume `deepdoc/vision/*` (the layout + OCR engine). The richer
   `deepdoc/parser/pdf_parser.py` pulls in vision-LLM and RAG-prompt
   machinery we have no use for in benchmarking.

### What was excluded

`deepdoc/parser/` and `deepdoc/vision/t_ocr.py`, `t_recognizer.py`,
`seeit.py` are NOT vendored — they're CLI / demo / LLM-orchestration code we
don't need. Our own orchestrator lives at
`backend/app/workers/deepdoc_worker.py`.

### What was stubbed (`_ragflow_stubs/`)

`deepdoc/vision/*` imports from `common.*` and `rag.*` for a small handful
of helpers. We provide those via `_ragflow_stubs/` — the worker prepends
that directory to `sys.path` before importing deepdoc.

- `common.file_utils.get_project_base_directory()` → returns cache dir.
- `common.misc_utils.pip_install_torch()` → no-op (we manage torch ourselves).
- `common.misc_utils.thread_pool_exec()` → minimal `concurrent.futures` wrapper.
- `common.settings.PARALLEL_DEVICES` / `LIGHTEN` → 0 / False.
- `rag.utils.lazy_image.ensure_pil_image()` → PIL conversion helper.
- `rag.nlp.rag_tokenizer` → whitespace tokenizer with stub `tag()` (TSR
  uses these only for Chinese-name disambiguation; English documents
  benchmark fine without it).

### Updating

Re-sparse-clone ragflow at a newer commit, then:
1. `cp -R <new>/deepdoc/__init__.py <new>/deepdoc/vision/*.py vendor/deepdoc/...`
2. Re-run `python -c "from deepdoc.vision.ocr import OCR; print(OCR)"` from
   `backend/` to confirm imports resolve.
3. Update the commit hash above.
