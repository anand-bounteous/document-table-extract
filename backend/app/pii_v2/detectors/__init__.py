"""Detector imports — side-effect: each module registers itself.

Heavy ML detectors (GLiNER, Piiranha) are imported lazily in the runner so
that the registry stays importable even when the optional ML deps are not
installed.
"""

from app.pii_v2.detectors import presidio_regex_detector  # noqa: F401
from app.pii_v2.detectors import presidio_spacy_detector  # noqa: F401
from app.pii_v2.detectors import gliner_detector  # noqa: F401
from app.pii_v2.detectors import piiranha_detector  # noqa: F401
from app.pii_v2.detectors import hybrid_detector  # noqa: F401
