"""Вырезки частей тела для классификаторов (одинаково при обучении и в рантайме)."""

from __future__ import annotations

import cv2
import numpy as np


def head_crop(img: np.ndarray, box, size: int = 96, margin: float = 0.15) -> np.ndarray | None:
    """Квадратная вырезка вокруг рамки головы с полем margin, size×size."""
    h, w = img.shape[:2]
    x1, y1, x2, y2 = [float(v) for v in box]
    bw, bh = x2 - x1, y2 - y1
    if bw < 8 or bh < 8:
        return None
    s = max(bw, bh) * (1 + 2 * margin)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    a, b = int(round(cx - s / 2)), int(round(cy - s / 2))
    c, d = int(round(cx + s / 2)), int(round(cy + s / 2))
    pad = max(0, -a, -b, c - w, d - h)
    if pad:
        img = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        a, b, c, d = a + pad, b + pad, c + pad, d + pad
    return cv2.resize(img[b:d, a:c], (size, size), interpolation=cv2.INTER_AREA)
