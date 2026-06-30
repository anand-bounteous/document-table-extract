"""Stub for ``rag.utils.lazy_image``.

Upstream defines a ``LazyImage`` wrapper that defers PIL loads. The only
symbol ``deepdoc/vision/operators.py`` calls is ``ensure_pil_image()``;
``open_image_for_processing`` and ``is_image_like`` aren't reached on our
codepath but we ship trivial impls so any future import resolves.
"""

from __future__ import annotations

from typing import Any

from PIL import Image
import numpy as np


def ensure_pil_image(img: Any) -> Image.Image:
    """Coerce a PIL.Image / numpy array / path string into a PIL.Image."""
    if isinstance(img, Image.Image):
        return img
    if isinstance(img, np.ndarray):
        return Image.fromarray(img)
    if isinstance(img, (str, bytes)):
        return Image.open(img).convert("RGB")
    raise TypeError(f"Unsupported image type: {type(img).__name__}")


def open_image_for_processing(path: Any) -> Image.Image:
    """Open ``path`` as an RGB PIL.Image — what deepdoc demos expect."""
    return Image.open(path).convert("RGB")


def is_image_like(obj: Any) -> bool:
    return isinstance(obj, (Image.Image, np.ndarray))


class LazyImage:
    """Tiny stand-in for upstream's LazyImage. We materialise eagerly because
    the laziness optimisation isn't on the codepath we exercise."""

    def __init__(self, img: Any) -> None:
        self._img = ensure_pil_image(img)

    def get(self) -> Image.Image:
        return self._img
