"""Concurrency planning for the per-solution scheduler.

The benchmark harness can have 30+ solution cards selected at once. Each
solution-subprocess loads its own ML model (0.4–2 GB). Firing them all in
parallel — the historical behaviour of ``_execute_run`` — easily exceeds 40
GB RAM. This module decides how many subprocesses should be alive at once
based on the configured policy.
"""

from __future__ import annotations

import logging
from typing import Tuple

from app.config import settings

logger = logging.getLogger("ote.pipeline.scheduler")

# Hard ceiling — even with a 256 GB box we never run more than this in
# parallel. Stops accidental misconfiguration (e.g. RAM_PER_SOLUTION_GB=0.1
# would otherwise compute "boil the ocean" numbers).
_HARD_CEILING = 16


def compute_solution_concurrency(n_solutions: int) -> Tuple[int, str]:
    """Return (concurrency, reason).

    Reason is a one-line human-readable string logged at run start so the
    user can correlate UI behaviour with the chosen budget.
    """
    if n_solutions <= 1:
        return 1, "single-solution run"

    if settings.max_concurrent_solutions > 0:
        n = max(1, min(_HARD_CEILING, min(settings.max_concurrent_solutions, n_solutions)))
        return n, f"override: MAX_CONCURRENT_SOLUTIONS={settings.max_concurrent_solutions}"

    try:
        import psutil

        free_gb = psutil.virtual_memory().available / (1024 ** 3)
    except Exception as exc:  # noqa: BLE001
        logger.warning("psutil unavailable, defaulting to 1: %s", exc)
        return 1, "auto: psutil unavailable, falling back to 1"

    budget = settings.ram_per_solution_gb
    if budget <= 0:
        budget = 3.0  # defensive
    n = max(1, min(_HARD_CEILING, min(n_solutions, int(free_gb // budget))))
    return n, f"auto: free={free_gb:.1f} GB / {budget:.1f} GB/sol -> {n}"
