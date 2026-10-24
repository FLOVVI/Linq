"""Снимок выходов моделей на LinQ TPU для сверки с ONNX на ноутбуке (на сервере нет onnxruntime).

На сервере:   python tools/linq_bench/dump_tpu.py            -> runs/tpu_dump.npz (скачать из Jupyter)
На ноутбуке:  python tools/linq_bench/dump_tpu.py --compare ~/Downloads/tpu_dump.npz

Входы сохраняются как uint8 (вход сети = кадр/255 после letterbox, поэтому это без потерь),
выходы — float16. Сравниваются косинусная близость выходов и итоговые детекции (IoU, классы).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)


def frames(n: int) -> list[np.ndarray]:
    import cv2

    out = [cv2.imread(os.path.join(ROOT, "data", "samples", "bus.jpg"))]
    cap = cv2.VideoCapture(os.path.join(ROOT, "data", "videos", "demo", "construction_walk_5434223.mp4"))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    for i in range(n - 1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((1 + 2 * i) * fps))  # 1, 3, 5 ... с — участок демо
        ok, f = cap.read()
        if ok:
            out.append(f)
    return out


def specs() -> list[tuple[str, dict]]:
    res = []
    for sp in sorted(glob.glob(os.path.join(ROOT, "models", "*.json"))):
        spec = json.load(open(sp, encoding="utf-8"))
        if spec.get("tpu"):
            res.append((sp, spec))
    return res


def inputs_for(spec: dict, imgs: list[np.ndarray]) -> list[np.ndarray]:
    import cv2

    from safetyvision.inference.yolo import preprocess

    if spec.get("task") == "classify":  # центральные вырезки, как голова в рамке
        s = spec["input"]["shape"][2]
        xs = []
        for im in imgs:
            h, w = im.shape[:2]
            c = im[h // 4:h // 4 + h // 3, w // 2 - h // 6:w // 2 + h // 6]
            xs.append(cv2.cvtColor(cv2.resize(c, (s, s)), cv2.COLOR_BGR2RGB).transpose(2, 0, 1)[None])
        return xs
    h, w = spec["input"]["shape"][2:]
    return [np.round(preprocess(im, (h, w))[0] * 255).astype(np.uint8) for im in imgs]


def dump(a):
    from safetyvision.inference.backends import make_backend

    imgs = frames(a.frames)
    blob = {}
    for sp, spec in specs():
        be = make_backend("tpu", spec, os.path.dirname(sp))
        for i, x8 in enumerate(inputs_for(spec, imgs)):
            out = be.run({spec["input"]["name"]: x8.astype(np.float32) / 255.0})
            blob[f"{spec['name']}|{i}|__input"] = x8
            for k, v in out.items():
                blob[f"{spec['name']}|{i}|{k}"] = np.asarray(v, np.float16)
        print("-", spec["name"], "кадров", len(imgs))
        be.close()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    np.savez_compressed(a.out, **blob)
    print("Сохранено:", a.out, f"{os.path.getsize(a.out) / 1e6:.1f} МБ — скачайте его из Jupyter")


def compare(a):
    from safetyvision.geometry.boxes import iou_matrix
    from safetyvision.inference.backends import make_backend
    from safetyvision.inference.yolo import decode

    z = np.load(a.compare)
    keys = sorted({tuple(k.split("|")[:2]) for k in z.files}, key=lambda t: (t[0], int(t[1])))
    by_name = {spec["name"]: (sp, spec) for sp, spec in specs()}
    report = {}
    for name, i in keys:
        sp, spec = by_name[name]
        be = make_backend("onnx", spec, os.path.dirname(sp))
        x = z[f"{name}|{i}|__input"].astype(np.float32) / 255.0
        ref = be.run({spec["input"]["name"]: x})
        tpu = {k.split("|")[2]: z[k].astype(np.float32) for k in z.files
               if k.startswith(f"{name}|{i}|") and not k.endswith("__input")}
        cos = {k: float(tpu[k].ravel() @ ref[k].ravel()
                        / (np.linalg.norm(tpu[k]) * np.linalg.norm(ref[k]) + 1e-12)) for k in ref if k in tpu}
        r = report.setdefault(name, {"cos_min": [], "det": []})
        r["cos_min"].append(min(cos.values()))
        if spec.get("task") == "classify":
            p = lambda o: np.exp(o.ravel() - o.max()) / np.exp(o.ravel() - o.max()).sum()  # noqa: E731
            pt, po = p(tpu["logits"]), p(ref["logits"])
            r["det"].append(f"p(no_helmet) tpu {pt[-1]:.3f} / onnx {po[-1]:.3f}  (классы {spec['classes']})")
            continue
        (bt, st, ct, _), (bo, so, co, _) = decode(tpu, spec, 0.3, 0.5), decode(ref, spec, 0.3, 0.5)
        same = 0
        if len(bt) and len(bo):
            m = iou_matrix(bo, bt)
            j = m.argmax(1)
            same = int(((m.max(1) > 0.5) & (ct[j] == co)).sum())
        r["det"].append(f"onnx {len(bo)} / tpu {len(bt)} / совпало {same}")
    for name, r in report.items():
        print(f"{name:<24} косинус min {min(r['cos_min']):.4f}")
        for d in r["det"]:
            print("   ", d)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=4)
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "tpu_dump.npz"))
    ap.add_argument("--compare", help="npz с сервера: сверить с ONNX на этой машине")
    a = ap.parse_args()
    compare(a) if a.compare else dump(a)
