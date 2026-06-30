"""OpenCV preprocessing: deskew, denoise, adaptive threshold, ruled-line detection.

Visible step in the pipeline — saves intermediates as artifacts so the report can
show them. Skips the ruled-line pass when the heuristic finds no strong lines.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Tuple

import cv2
import numpy as np

from app.core.geometry import bbox_from_xyxy
from app.core.schemas import BBox
from app.pipeline.base import RunState
from app.pipeline.context import RunContext

logger = logging.getLogger("ote.stage.opencv")


@dataclass
class PreprocessOpenCV:
    name: str = "preprocess_opencv"
    tool: str = "opencv"
    detect_lines: bool = True

    def run(self, ctx: RunContext, state: RunState) -> RunState:
        for idx, png in ctx.page_images.items():
            img = cv2.imread(str(png))
            if img is None:
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = _deskew(gray)
            gray = cv2.fastNlMeansDenoising(gray, h=10)
            thr = cv2.adaptiveThreshold(
                gray,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=31,
                C=15,
            )
            pre_name = f"preproc/page-{idx:03d}.png"
            ctx.save_bytes(pre_name, cv2.imencode(".png", thr)[1].tobytes())
            state.extras.setdefault("preproc", {})[idx] = ctx.artifact_path(pre_name)

            if self.detect_lines:
                lines = _detect_ruled_lines(thr)
                state.extras.setdefault("ruled_lines", {})[idx] = lines
                if lines:
                    boxes = _line_grid_to_cells(lines, page_index=idx, dpi=ctx.dpi)
                    state.extras.setdefault("ruled_cells", {})[idx] = boxes
                    overlay = cv2.cvtColor(thr, cv2.COLOR_GRAY2BGR)
                    for h_line in lines[0]:
                        cv2.line(overlay, (h_line[0], h_line[1]), (h_line[2], h_line[3]), (0, 0, 255), 2)
                    for v_line in lines[1]:
                        cv2.line(overlay, (v_line[0], v_line[1]), (v_line[2], v_line[3]), (255, 0, 0), 2)
                    ctx.save_bytes(
                        f"preproc/page-{idx:03d}-lines.png",
                        cv2.imencode(".png", overlay)[1].tobytes(),
                    )
        return state


def _deskew(gray: np.ndarray) -> np.ndarray:
    inverted = cv2.bitwise_not(gray)
    coords = cv2.findNonZero(inverted)
    if coords is None or len(coords) < 50:
        return gray
    rect = cv2.minAreaRect(coords)
    angle = rect[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    if abs(angle) < 0.1:
        return gray
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _detect_ruled_lines(
    binary: np.ndarray,
) -> Tuple[List[Tuple[int, int, int, int]], List[Tuple[int, int, int, int]]]:
    """Return (horizontal_lines, vertical_lines) as (x1, y1, x2, y2)."""
    inv = cv2.bitwise_not(binary)
    h, w = binary.shape
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, w // 30), 1))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, h // 30)))
    h_morph = cv2.morphologyEx(inv, cv2.MORPH_OPEN, h_kernel, iterations=1)
    v_morph = cv2.morphologyEx(inv, cv2.MORPH_OPEN, v_kernel, iterations=1)

    h_lines = _contours_to_segments(h_morph, horizontal=True)
    v_lines = _contours_to_segments(v_morph, horizontal=False)
    return h_lines, v_lines


def _contours_to_segments(mask: np.ndarray, *, horizontal: bool) -> List[Tuple[int, int, int, int]]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out: List[Tuple[int, int, int, int]] = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if horizontal and w > 60:
            out.append((x, y + h // 2, x + w, y + h // 2))
        elif not horizontal and h > 60:
            out.append((x + w // 2, y, x + w // 2, y + h))
    return out


def _line_grid_to_cells(
    lines: Tuple[List[Tuple[int, int, int, int]], List[Tuple[int, int, int, int]]],
    *,
    page_index: int,
    dpi: int,
) -> List[BBox]:
    """Make a rough grid of cell BBoxes from detected horizontal+vertical lines."""
    h_lines, v_lines = lines
    if len(h_lines) < 2 or len(v_lines) < 2:
        return []
    ys = sorted({l[1] for l in h_lines})
    xs = sorted({l[0] for l in v_lines})
    boxes: List[BBox] = []
    for r in range(len(ys) - 1):
        for c in range(len(xs) - 1):
            boxes.append(
                bbox_from_xyxy(xs[c], ys[r], xs[c + 1], ys[r + 1], page_index=page_index, dpi=dpi)
            )
    return boxes
