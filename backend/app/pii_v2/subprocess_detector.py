"""Subprocess helper for heavy ML detectors.

Reuses the same conventions as :mod:`app.pipeline.isolation`: write the input
JSON to stdin, read the result JSON from ``$OTE_RESULT_PATH``, capture stderr
into an artifact. Each call spawns a fresh Python process so the ML model
loads in a separate address space and is fully released after the call.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from app.pii_v2.schema import PIIEntity

logger = logging.getLogger("ote.pii_v2.subprocess")

_REPO_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

# Per-process cache: once a worker has failed (dep missing, model not on disk),
# don't keep spawning subprocesses for the same module within this run.
_WORKER_UNAVAILABLE: set[str] = set()


class WorkerUnavailable(RuntimeError):
    """Raised when a worker fails on cached unavailability."""


def reset_unavailable_cache() -> None:
    """Test-only — wipe the cached unavailability set."""
    _WORKER_UNAVAILABLE.clear()


def call_worker(
    *,
    worker_module: str,
    text: str,
    jurisdictions: List[str],
    extra_env: Dict[str, str] | None = None,
    timeout_sec: float = 30.0,
) -> List[PIIEntity]:
    """Run ``worker_module`` on ``text`` and return its PIIEntity list.

    Raises ``RuntimeError`` if the subprocess exits non-zero. The detector
    classes catch this and surface a clean error in ``DetectorResult.error``.
    """
    if worker_module in _WORKER_UNAVAILABLE:
        raise WorkerUnavailable(f"{worker_module} previously failed in this process")
    payload = {
        "text": text,
        "jurisdictions": list(jurisdictions),
    }
    # Offline by default — flip via PII_V2_HF_ONLINE=1 to allow first-time model
    # downloads from HuggingFace (see SETUP.md §6b.3). When online we also
    # propagate Homebrew OpenSSL's cert bundle if present, so requests can
    # validate huggingface.co on macOS systems where certifi is stale.
    online = os.environ.get("PII_V2_HF_ONLINE", "0") == "1"
    hf_env: Dict[str, str] = {}
    if online:
        for cert in (
            "/opt/homebrew/etc/openssl@3/cert.pem",
            "/usr/local/etc/openssl@3/cert.pem",
            "/etc/ssl/cert.pem",
        ):
            if Path(cert).exists():
                hf_env.setdefault("SSL_CERT_FILE", cert)
                hf_env.setdefault("REQUESTS_CA_BUNDLE", cert)
                break
    else:
        hf_env["HF_HUB_OFFLINE"] = "1"
        hf_env["TRANSFORMERS_OFFLINE"] = "1"

    with tempfile.TemporaryDirectory(prefix="pii_v2_") as tmp:
        tmp_path = Path(tmp)
        result_path = tmp_path / "result.json"
        env = {
            **hf_env,
            **os.environ,
            **(extra_env or {}),
            "OTE_RESULT_PATH": str(result_path),
        }
        try:
            proc = subprocess.run(
                [sys.executable, "-m", worker_module],
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                env=env,
                timeout=timeout_sec,
                cwd=str(_REPO_BACKEND_ROOT),
            )
        except subprocess.TimeoutExpired:
            _WORKER_UNAVAILABLE.add(worker_module)
            raise RuntimeError(f"worker {worker_module} timed out after {timeout_sec}s")
        if proc.returncode != 0:
            tail = (proc.stderr or "").strip().splitlines()[-5:]
            stderr_lower = (proc.stderr or "").lower()
            # ModuleNotFoundError / ImportError on the heavy ML dep → cache it
            # so we stop re-spawning for this worker in this process.
            if "modulenotfounderror" in stderr_lower or "importerror" in stderr_lower:
                _WORKER_UNAVAILABLE.add(worker_module)
            raise RuntimeError(
                f"worker {worker_module} exited {proc.returncode}: {' / '.join(tail)}"
            )
        if not result_path.exists():
            _WORKER_UNAVAILABLE.add(worker_module)
            raise RuntimeError(f"worker {worker_module} produced no result file")
        data = json.loads(result_path.read_text())
        return [PIIEntity(**e) for e in data.get("entities", [])]
