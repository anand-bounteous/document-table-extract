"""Stub for ``common.settings``.

Upstream exposes a module with constants used by deepdoc. We only need:

- ``PARALLEL_DEVICES``: deepdoc's OCR class checks ``> 0`` to enable a
  multi-GPU detect/recognize batching path. Set to 0 so we use the simple
  single-device path.
- ``LIGHTEN``: an upstream feature flag for "lightweight" model variants;
  False is the upstream default.
"""

PARALLEL_DEVICES = 0
LIGHTEN = False
