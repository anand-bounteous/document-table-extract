"""Stub for ``common.misc_utils`` — only what ``deepdoc/vision/*`` consumes."""

from __future__ import annotations

import concurrent.futures
from typing import Any, Callable, Iterable


def pip_install_torch(*args: Any, **kwargs: Any) -> None:
    """No-op. Upstream uses this to lazily ``pip install`` torch the first
    time deepdoc is invoked. We require the user to install torch via the
    repo's extras (``[ocr-deepdoc]``) so this becomes a no-op."""
    return None


def thread_pool_exec(fn: Callable, iterable: Iterable, max_workers: int = 4):
    """Concurrent map — upstream uses this for parallel page processing.

    Returns the same shape as upstream: a list of fn(item) results in input
    order.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(fn, iterable))


def hash_str2int(s: str) -> int:
    """Stable string → int hash. Used by upstream for some seeded routines;
    unused on the codepath we exercise, but provided for completeness."""
    import hashlib
    return int.from_bytes(hashlib.md5(s.encode("utf-8")).digest()[:8], "big")
