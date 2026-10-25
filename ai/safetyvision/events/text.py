"""Кириллические подписи на кадрах (OpenCV рисует только ASCII)."""

from __future__ import annotations

import functools
import os

import numpy as np

_WIN_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
_FONT_CANDIDATES = [
    os.path.join(_WIN_FONTS, "arial.ttf"),
    os.path.join(_WIN_FONTS, "segoeui.ttf"),
    os.path.join(_WIN_FONTS, "tahoma.ttf"),
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


@functools.lru_cache(maxsize=8)
def _font(size: int):
    from PIL import ImageFont

    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def put_text(img: np.ndarray, text: str, org: tuple[int, int], color=(255, 255, 255), size: int = 18,
             bg: tuple[int, int, int] | None = None) -> None:
    """Рисует текст на BGR-изображении на месте (через PIL, только по области подписи)."""
    from PIL import Image, ImageDraw

    font = _font(size)
    x, y = int(org[0]), int(org[1])
    l, t, r, b = font.getbbox(text)
    tw, th = r - l + 8, b - t + 6
    h, w = img.shape[:2]
    x = max(0, min(x, w - tw))
    y = max(0, min(y, h - th))
    roi = img[y:y + th, x:x + tw]
    if roi.size == 0:
        return
    if bg is not None:
        roi[:] = bg
    pil = Image.fromarray(roi[..., ::-1].copy())
    ImageDraw.Draw(pil).text((4 - l, 3 - t), text, font=font, fill=tuple(int(c) for c in color[::-1]))
    img[y:y + th, x:x + tw] = np.asarray(pil)[..., ::-1]


def text_size(text: str, size: int) -> tuple[int, int]:
    l, t, r, b = _font(size).getbbox(text)
    return r - l, b - t


def put_text_center(img: np.ndarray, text: str, center, color=(0, 0, 0), size: int = 14) -> None:
    """Подпись по центру точки, без подложки (номер внутри значка на карте)."""
    w, h = text_size(text, size)
    put_text(img, text, (int(center[0]) - w // 2 - 4, int(center[1]) - h // 2 - 3), color, size)
