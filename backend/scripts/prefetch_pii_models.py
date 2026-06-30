"""One-shot prefetch for the pii_v2 ML model assets.

Downloads:
- spaCy ``en_core_web_sm`` (Track B)
- ``urchade/gliner_small-v2.1`` (Track C)
- ``iiiorg/piiranha-v1-detect-personal-information`` (Track D)

After this runs successfully, the subprocess detectors can stay in their
default ``HF_HUB_OFFLINE=1`` mode and still find the cached models on disk.

Usage:

    uv run python -m scripts.prefetch_pii_models
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _ensure_ssl_cert() -> None:
    """Point requests/HuggingFace at Homebrew's OpenSSL bundle on macOS.

    Same trick the existing TrOCR / Layout-Parser stages use — certifi can
    be too old to validate huggingface.co, but Homebrew's openssl@3 bundle
    works.
    """
    for cert in (
        "/opt/homebrew/etc/openssl@3/cert.pem",   # Apple Silicon Homebrew
        "/usr/local/etc/openssl@3/cert.pem",      # Intel Homebrew
        "/etc/ssl/cert.pem",                       # Linux distros
    ):
        if Path(cert).exists():
            os.environ.setdefault("SSL_CERT_FILE", cert)
            os.environ.setdefault("REQUESTS_CA_BUNDLE", cert)
            return


def _prefetch_spacy() -> bool:
    print(">> Track B  · spaCy en_core_web_sm")
    try:
        import spacy  # noqa: F401
    except ImportError:
        print("   ❌ spacy not installed. Run: uv pip install spacy")
        return False
    try:
        import spacy
        spacy.load("en_core_web_sm")
        print("   ✓ already installed")
        return True
    except OSError:
        pass
    proc = subprocess.run([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
    return proc.returncode == 0


def _prefetch_gliner() -> bool:
    name = os.environ.get("PII_V2_GLINER_MODEL", "urchade/gliner_small-v2.1")
    print(f">> Track C  · GLiNER ({name})")
    try:
        from gliner import GLiNER  # type: ignore
    except ImportError:
        print("   ❌ gliner not installed. Run: uv pip install gliner")
        return False
    try:
        GLiNER.from_pretrained(name)
        print("   ✓ cached")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"   ❌ download failed: {exc}")
        return False


def _prefetch_piiranha() -> bool:
    name = os.environ.get(
        "PII_V2_PIIRANHA_MODEL", "iiiorg/piiranha-v1-detect-personal-information"
    )
    print(f">> Track D  · Piiranha ({name})")
    try:
        from transformers import pipeline  # type: ignore
    except ImportError:
        print("   ❌ transformers not installed (pulled in by gliner; install gliner)")
        return False
    try:
        pipeline("token-classification", model=name, aggregation_strategy="simple")
        print("   ✓ cached")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"   ❌ download failed: {exc}")
        return False


def main() -> int:
    _ensure_ssl_cert()
    results = {
        "spacy": _prefetch_spacy(),
        "gliner": _prefetch_gliner(),
        "piiranha": _prefetch_piiranha(),
    }
    print()
    print("Summary:")
    for k, ok in results.items():
        print(f"  {k:10} {'✓' if ok else '✗'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
