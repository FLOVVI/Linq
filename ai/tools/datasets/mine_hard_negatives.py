"""Трудные негативы для классификатора каски: головы без каски, которые он считает касками.

Берём фото людей вне стройки (набор про курение), находим головы детектором СИЗ (SH17, как в
рантайме), отбрасываем головы, на которых тот же детектор видит каску, и оставляем вырезки,
где текущий классификатор ошибается (p(no_helmet) < 0.5) — кепки, шапки, капюшоны.
Перед дообучением кандидаты просматриваются глазами (contact sheet).

    python tools/datasets/mine_hard_negatives.py --out data/datasets/helmet_hn
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

import cv2
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from safetyvision.analytics.crops import head_crop  # noqa: E402
from safetyvision.inference import ClassifierModel, YoloModel  # noqa: E402


def overlap(a, b) -> float:
    """Доля площади a, накрытая b."""
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return inter / max((a[2] - a[0]) * (a[3] - a[1]), 1e-6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="+", default=[
        os.path.join(ROOT, "data", "datasets", "raw", "smoking", "images", "*", "*", "*")])
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "datasets", "helmet_hn"))
    ap.add_argument("--max-p", type=float, default=0.5, help="брать вырезки с p(no_helmet) ниже")
    a = ap.parse_args()
    det = YoloModel(os.path.join(ROOT, "models", "ppe_sh17s_384x640.json"), "onnx", conf=0.3)
    cls = ClassifierModel(os.path.join(ROOT, "models", "helmet_cls_v8n_96.json"), "onnx")
    i_head, i_helm = det.names.index("head"), det.names.index("helmet")
    i_no = cls.names.index("no_helmet")
    files = sorted(f for g in a.images for f in glob.glob(g))
    os.makedirs(a.out, exist_ok=True)
    kept = seen = 0
    for n, f in enumerate(files):
        img = cv2.imread(f)
        if img is None:
            continue
        d = det(img)
        helmets = d.boxes[d.classes == i_helm]
        for b, s in zip(d.boxes[d.classes == i_head], d.scores[d.classes == i_head]):
            if s < 0.55 or (b[3] - b[1]) < 24:
                continue
            if any(overlap(b, h) > 0.2 for h in helmets):
                continue
            crop = head_crop(img, b, cls.size)
            if crop is None:
                continue
            seen += 1
            p = float(cls([crop])[0, i_no])
            if p < a.max_p:
                kept += 1
                name = f"{os.path.splitext(os.path.basename(f))[0]}_{int(b[0])}_{int(b[1])}_{p:.2f}.jpg"
                cv2.imwrite(os.path.join(a.out, name), crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if n % 500 == 0:
            print(f"{n}/{len(files)}: голов {seen}, трудных {kept}", flush=True)
    print(f"готово: голов {seen}, трудных негативов {kept} -> {a.out}")


if __name__ == "__main__":
    main()
