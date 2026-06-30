"""Env-var defaults that point Python SSL + requests at the system CA bundle.

certifi's cabundle doesn't include every root brew's OpenSSL trusts (e.g. some
roots used by modelscope.cn / paddlepaddle.org.cn). Heavy-ML stages that
download model weights on first run honor these env vars without code changes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

_CANDIDATES = [
    "/opt/homebrew/etc/openssl@3/cert.pem",
    "/usr/local/etc/openssl@3/cert.pem",
    "/etc/ssl/cert.pem",
    "/etc/ssl/certs/ca-certificates.crt",
]


def system_ca_bundle() -> str | None:
    for p in _CANDIDATES:
        if Path(p).is_file():
            return p
    return None


def ssl_env_overrides() -> Dict[str, str]:
    """Return env vars that direct `ssl`/`requests`/`urllib3` at the system bundle.

    User-set values take precedence: we never overwrite an existing SSL_CERT_FILE
    or REQUESTS_CA_BUNDLE.
    """
    out: Dict[str, str] = {}
    bundle = system_ca_bundle()
    if not bundle:
        return out
    for key in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        if not os.environ.get(key):
            out[key] = bundle
    return out
