"""Набор для классификатора «каска / голова без каски» из вырезок голов.

Источники: hard-hat-detection (Roboflow, CC BY 4.0: hardhat / no-hardhat) и Construction-PPE
(Ultralytics: helmet / no_helmet). Вырезка делается так же, как в рантайме: рамка головы от
детектора + 15% поля, квадрат, 96×96.

    python tools/datasets/build_helmet_cls.py --out data/datasets/helmet_cls
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import random
import sys
import zipfile

import cv2
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from safetyvision.analytics.crops import head_crop  # noqa: E402


def from_coco_zip(zpath: str, cls_map: dict[str, str], out: list):
    z = zipfile.ZipFile(zpath)
    ann = json.loads(z.read("_annotations.coco.json"))
    cats = {c["id"]: c["name"] for c in ann["categories"]}
    imgs = {i["id"]: i["file_name"] for i in ann["images"]}
    by_img: dict[int, list] = {}
    for a in ann["annotations"]:
        name = cats[a["category_id"]]
        if name in cls_map:
            by_img.setdefault(a["image_id"], []).append((cls_map[name], a["bbox"]))
    for iid, items in by_img.items():
        data = np.frombuffer(z.read(imgs[iid]), np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            continue
        for label, (x, y, w, h) in items:
            c = head_crop(img, (x, y, x + w, y + h))
            if c is not None:
                out.append((label, c, f"hh_{iid}"))


def from_yolo_dir(root: str, cls_map: dict[int, str], out: list):
    for lbl in glob.glob(os.path.join(root, "labels", "*", "*.txt")):
        imgp = lbl.replace(os.sep + "labels" + os.sep, os.sep + "images" + os.sep)[:-4] + ".jpg"
        img = cv2.imread(imgp)
        if img is None:
            continue
        h, w = img.shape[:2]
        for line in open(lbl):
            p = line.split()
            if len(p) < 5 or int(p[0]) not in cls_map:
                continue
            cx, cy, bw, bh = (float(v) for v in p[1:5])
            box = ((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h)
            c = head_crop(img, box)
            if c is not None:
                out.append((cls_map[int(p[0])], c, "cp_" + os.path.basename(lbl)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "datasets", "helmet_cls"))
    ap.add_argument("--max-per-class", type=int, default=9000)
    a = ap.parse_args()
    items: list = []
    raw = os.path.join(ROOT, "data", "datasets", "raw", "hardhat")
    for z in sorted(glob.glob(os.path.join(raw, "*.zip"))):
        n0 = len(items)
        try:
            from_coco_zip(z, {"hardhat": "helmet", "no-hardhat": "no_helmet"}, items)
        except zipfile.BadZipFile:
            print("пропуск (недокачан):", z)
            continue
        print(z, len(items) - n0)
    n0 = len(items)
    from_yolo_dir(os.path.join(ROOT, "data", "datasets", "construction-ppe"), {0: "helmet", 7: "no_helmet"}, items)
    print("construction-ppe", len(items) - n0)
    random.seed(0)
    random.shuffle(items)
    # разбиение по исходному изображению, чтобы вырезки одного кадра не попали и в train, и в val
    src_ids = sorted({s for _, _, s in items})
    val_src = set(random.sample(src_ids, len(src_ids) // 10))
    counts: dict = {}
    for label, crop, src in items:
        split = "val" if src in val_src else "train"
        k = (split, label)
        counts[k] = counts.get(k, 0) + 1
        if split == "train" and counts[k] > a.max_per_class:
            continue
        d = os.path.join(a.out, split, label)
        os.makedirs(d, exist_ok=True)
        cv2.imwrite(os.path.join(d, f"{src}_{counts[k]}.jpg"), crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print({f"{s}/{l}": min(n, a.max_per_class if s == "train" else n) for (s, l), n in sorted(counts.items())})


if __name__ == "__main__":
    main()
