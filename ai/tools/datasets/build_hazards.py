"""Набор для детектора опасностей (YOLO): cigarette, fire, smoke, forklift.

Источники:
  * D-Fire (огонь/дым, ~21 тыс. фото; берём 4 шарда с HF badsaarow/d-fire);
  * keremberke/forklift-object-detection (Roboflow, CC BY 4.0) — погрузчики;
  * ccclllwww/smoking_img_final — фото курящих; рамок сигарет в нём нет, их размечает
    модель-учитель (basant18/Smoking-detection-YOLO26s, Apache-2.0) — псевдоразметка;
  * негативы: Construction-PPE и hard-hat (люди на производстве без огня и сигарет).

    python tools/datasets/build_hazards.py --out data/datasets/hazards
"""

from __future__ import annotations

import argparse
import glob
import io
import json
import os
import random
import zipfile

import cv2
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW = os.path.join(ROOT, "data", "datasets", "raw")
NAMES = ["cigarette", "fire", "smoke", "forklift"]
MAX_SIDE = 960


class Writer:
    def __init__(self, out: str):
        self.out = out
        self.n = {"train": 0, "val": 0}
        self.inst = {}
        for s in ("train", "val"):
            os.makedirs(os.path.join(out, "images", s), exist_ok=True)
            os.makedirs(os.path.join(out, "labels", s), exist_ok=True)

    def add(self, split: str, name: str, img: np.ndarray, boxes: list[tuple[int, float, float, float, float]]):
        """boxes: (cls, x1, y1, x2, y2) в пикселях img."""
        h, w = img.shape[:2]
        s = min(1.0, MAX_SIDE / max(h, w))
        if s < 1:
            img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        lines = []
        for c, x1, y1, x2, y2 in boxes:
            x1, x2 = np.clip([x1, x2], 0, w)
            y1, y2 = np.clip([y1, y2], 0, h)
            if x2 - x1 < 2 or y2 - y1 < 2:
                continue
            lines.append(f"{c} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}")
            self.inst[(split, NAMES[c])] = self.inst.get((split, NAMES[c]), 0) + 1
        cv2.imwrite(os.path.join(self.out, "images", split, name + ".jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        with open(os.path.join(self.out, "labels", split, name + ".txt"), "w") as f:
            f.write("\n".join(lines))
        self.n[split] += 1


def dfire(w: Writer, max_neg: int = 700):
    import pyarrow.parquet as pq

    remap = {0: 2, 1: 1}  # D-Fire: 0 smoke, 1 fire
    neg = 0
    for f in sorted(glob.glob(os.path.join(RAW, "dfire", "data", "*.parquet"))):
        split = "val" if "test" in os.path.basename(f) else "train"
        t = pq.read_table(f)
        for row in t.to_pylist():
            lab = (row["label"] or "").strip()
            if not lab:
                if split == "val" or neg >= max_neg:
                    continue
                neg += 1
            img = cv2.imdecode(np.frombuffer(row["image"]["bytes"], np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            h, wd = img.shape[:2]
            boxes = []
            for line in lab.splitlines():
                p = line.split()
                c, cx, cy, bw, bh = int(p[0]), *map(float, p[1:5])
                boxes.append((remap[c], (cx - bw / 2) * wd, (cy - bh / 2) * h, (cx + bw / 2) * wd, (cy + bh / 2) * h))
            w.add(split, "dfire_" + os.path.splitext(row["filename"])[0], img, boxes)
        print("D-Fire", os.path.basename(f), w.n)


def forklift(w: Writer):
    rnd = random.Random(1)
    for z in sorted(glob.glob(os.path.join(RAW, "forklift", "*.zip"))):
        try:
            zf = zipfile.ZipFile(z)
        except zipfile.BadZipFile:
            continue
        ann = json.loads(zf.read("_annotations.coco.json"))
        cats = {c["id"]: c["name"].lower() for c in ann["categories"]}
        by = {}
        for a in ann["annotations"]:
            if "forklift" in cats[a["category_id"]]:
                x, y, bw, bh = a["bbox"]
                by.setdefault(a["image_id"], []).append((3, x, y, x + bw, y + bh))
        for im in ann["images"]:
            img = cv2.imdecode(np.frombuffer(zf.read(im["file_name"]), np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            split = "val" if rnd.random() < 0.15 else "train"
            w.add(split, f"fork_{os.path.basename(z)[:-4]}_{im['id']}", img, by.get(im["id"], []))
        print("forklift", z, w.n)


def teacher_cigarettes(paths: list[str], w: Writer, prefix: str, keep_empty: bool, conf: float = 0.4,
                       val_ratio: float = 0.1):
    from ultralytics import YOLO

    teacher = YOLO(os.path.join(ROOT, "data", "weights", "thirdparty", "cig_v8s_basant18.pt"))
    rnd = random.Random(2)
    kept = 0
    for i in range(0, len(paths), 16):
        chunk = paths[i:i + 16]
        imgs = [cv2.imread(p) for p in chunk]
        pairs = [(p, im) for p, im in zip(chunk, imgs) if im is not None]
        if not pairs:
            continue
        res = teacher.predict([im for _, im in pairs], imgsz=640, conf=conf, verbose=False, device="mps")
        for (p, im), r in zip(pairs, res):
            b = r.boxes.xyxy.cpu().numpy()
            if len(b) == 0 and not keep_empty:
                continue
            split = "val" if rnd.random() < val_ratio else "train"
            w.add(split, prefix + os.path.splitext(os.path.basename(p))[0], im, [(0, *bb) for bb in b])
            kept += 1
    print(prefix, "оставлено", kept, "из", len(paths), w.n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "datasets", "hazards"))
    ap.add_argument("--neg-people", type=int, default=900)
    a = ap.parse_args()
    w = Writer(a.out)
    dfire(w)
    forklift(w)
    smk = sorted(glob.glob(os.path.join(RAW, "smoking", "images", "*", "smoking", "*")))
    teacher_cigarettes(smk, w, "smk_", keep_empty=False)
    rnd = random.Random(3)
    notsmk = sorted(glob.glob(os.path.join(RAW, "smoking", "images", "train", "not_smoking", "*")))
    teacher_cigarettes(rnd.sample(notsmk, min(500, len(notsmk))), w, "nsmk_", keep_empty=True)
    people = sorted(glob.glob(os.path.join(ROOT, "data", "datasets", "construction-ppe", "images", "train", "*.jpg")))
    teacher_cigarettes(rnd.sample(people, min(a.neg_people, len(people))), w, "ppl_", keep_empty=True)
    yaml = os.path.join(a.out, "hazards.yaml")
    with open(yaml, "w") as f:
        f.write(f"path: {a.out}\ntrain: images/train\nval: images/val\nnames:\n")
        for i, n in enumerate(NAMES):
            f.write(f"  {i}: {n}\n")
    print("изображений:", w.n, "объектов:", w.inst, "\n", yaml)


if __name__ == "__main__":
    main()
