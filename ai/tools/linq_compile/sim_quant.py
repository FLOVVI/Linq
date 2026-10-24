"""Эмуляция квантованной модели (SDK, torch-граф) на входах из снимка с реальной платы (dump_tpu.py).

Показывает, где теряется точность: в самом квантовании (эмуляция расходится с ONNX так же, как плата)
или на плате/в облаке (эмуляция совпадает с ONNX, плата — нет). Запуск в Docker с SDK:
    python tools/linq_compile/sim_quant.py --spec models/helmet_cls_v8n_v2_96.json --dump runs/simcheck/dump.npz
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from compile_tpu import cosine  # noqa: E402


_GRAPHS: dict[int, object] = {}


def simulate(qm, sample: dict[str, np.ndarray], out_names: list[str]) -> dict[str, np.ndarray]:
    import builtins

    import torch
    try:
        from tpu_framework import TpuDtype
    except ImportError:
        from dnn_quant.api import TpuDtype

    builtins.np = np
    if id(qm) not in _GRAPHS:
        _GRAPHS[id(qm)] = qm.as_torch_graph(batch_size=1)
    g = _GRAPHS[id(qm)]
    anchors = g.get_outputs_anchors() | g.get_inputs_anchors()
    inp = qm.rescale({anchors[k]: v for k, v in sample.items()}, TpuDtype.Input)
    g.gm.eval()
    with torch.no_grad():
        outs = g.gm(*[torch.as_tensor(inp[n]) for n in g._input_layer_names])
    outs = outs if isinstance(outs, (tuple, list)) else (outs,)
    ordered = [anchors[n] for n in out_names]
    q = qm.rescale({n: o.detach().cpu().numpy() for n, o in zip(ordered, outs)}, TpuDtype.Output)
    return {n: q[anchors[n]] for n in out_names}  # NHWC; в NCHW — to_nchw()


def to_nchw(a: np.ndarray, ref_shape: tuple) -> np.ndarray:
    a = np.asarray(a)
    if a.shape == tuple(ref_shape):
        return a
    n, c, h, w = ref_shape
    if a.shape == (n, h, w, c):
        return a.transpose(0, 3, 1, 2)
    return a.reshape(ref_shape)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--dump")
    ap.add_argument("--images", help="классификатор: папка вида <класс>/*.jpg — точность ONNX и эмуляции")
    ap.add_argument("--n", type=int, default=150, help="изображений на класс для --images")
    ap.add_argument("--qm", help="квантованная модель (.qm.onnx); по умолчанию из models/build/<name>")
    a = ap.parse_args()
    import onnxruntime as ort
    from tpu_framework import QuantizedModel

    spec = json.load(open(a.spec, encoding="utf-8"))
    mdir = os.path.dirname(os.path.abspath(a.spec))
    name = spec["name"]
    is_cls = spec.get("task") == "classify"
    out_names = spec["outputs"] if is_cls else [l[k] for l in spec["levels"] for k in ("box", "cls", "kpt") if k in l]
    qm = QuantizedModel.load(a.qm or os.path.join(mdir, "build", name, f"quant_{name}.qm.onnx"))
    sess = ort.InferenceSession(os.path.join(mdir, spec["onnx"]), providers=["CPUExecutionProvider"])
    if a.images and is_cls:
        return eval_classifier(a, spec, qm, sess, out_names[0])
    if a.images:
        return eval_detector(a, spec, qm, sess, out_names)
    z = np.load(a.dump)
    for i in range(16):
        key = f"{name}|{i}|__input"
        if key not in z.files:
            break
        x = {spec["input"]["name"]: z[key].astype(np.float32) / 255.0}
        ref = dict(zip(out_names, sess.run(out_names, x)))
        sim = simulate(qm, x, out_names)
        row = []
        for n in out_names:
            tpu = z[f"{name}|{i}|{n}"].astype(np.float32)
            s = to_nchw(sim[n], ref[n].shape)
            row.append(f"{n}: эмуляция/onnx {cosine(s, ref[n]):.3f}  плата/onnx {cosine(tpu, ref[n]):.3f}  "
                       f"плата/эмуляция {cosine(tpu, s):.3f}")
            if is_cls:
                row.append(f"   onnx {ref[n].ravel().round(2)}  эмуляция {np.asarray(s).ravel().round(2)}  "
                           f"плата {tpu.ravel().round(2)}")
        print(f"[{i}]", "\n    ".join(row))


def eval_classifier(a, spec, qm, sess, out: str, thr: float = 0.85):
    """Точность и согласие ONNX/эмуляции; «ложные no_helmet» — p(no_helmet) >= thr на каске (порог тревоги)."""
    import glob

    import cv2

    size = spec["input"]["shape"][2]
    classes = spec["classes"]
    rng = np.random.default_rng(1)
    soft = lambda v: np.exp(v - v.max()) / np.exp(v - v.max()).sum()  # noqa: E731
    acc = {"onnx": 0, "sim": 0}
    fa = {"onnx": 0, "sim": 0}
    dp, total, n_helmet = [], 0, 0
    for ci, c in enumerate(classes):
        files = sorted(glob.glob(os.path.join(a.images, c, "*")))
        for f in [files[i] for i in rng.permutation(len(files))[:a.n]]:
            img = cv2.imread(f)
            if img is None:
                continue
            x = cv2.cvtColor(cv2.resize(img, (size, size)), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            x = {spec["input"]["name"]: x.transpose(2, 0, 1)[None]}
            po = soft(sess.run([out], x)[0].ravel())
            ps = soft(np.asarray(simulate(qm, x, [out])[out]).ravel())
            for k, p in (("onnx", po), ("sim", ps)):
                acc[k] += int(p.argmax() == ci)
                if c == "helmet":
                    fa[k] += int(p[classes.index("no_helmet")] >= thr)
            dp.append(abs(po[1] - ps[1]))
            total += 1
            n_helmet += c == "helmet"
    print(f"{total} изображений: точность ONNX {acc['onnx'] / total:.3f}, эмуляция {acc['sim'] / total:.3f}; "
          f"|Δp| среднее {np.mean(dp):.3f}, p95 {np.percentile(dp, 95):.3f}; "
          f"каски с p(no_helmet)>={thr}: ONNX {fa['onnx']}/{n_helmet}, эмуляция {fa['sim']}/{n_helmet}")


def eval_detector(a, spec, qm, sess, out_names, conf: float = 0.3):
    """Полнота эмуляции относительно ONNX: доля детекций ONNX, найденных эмуляцией (IoU>0.5, тот же класс)."""
    import glob

    import cv2

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from safetyvision.geometry.boxes import iou_matrix
    from safetyvision.inference.yolo import decode, preprocess

    names = spec["classes"]
    hit, tot, extra = {}, {}, 0
    for f in sorted(glob.glob(os.path.join(a.images, "*.jpg")))[:a.n]:
        x = {spec["input"]["name"]: preprocess(cv2.imread(f), tuple(spec["input"]["shape"][2:]))[0]}
        ref = dict(zip(out_names, sess.run(out_names, x)))
        sim = simulate(qm, x, out_names)
        sim = {k: to_nchw(v, ref[k].shape) for k, v in sim.items()}
        bo, _, co, _ = decode(ref, spec, conf, 0.5)
        bs, _, cs, _ = decode(sim, spec, conf, 0.5)
        m = iou_matrix(bo, bs) if len(bo) and len(bs) else np.zeros((len(bo), len(bs)))
        for i, c in enumerate(co):
            ok = bool(len(bs)) and any(m[i, j] > 0.5 and cs[j] == c for j in range(len(bs)))
            tot[names[c]] = tot.get(names[c], 0) + 1
            hit[names[c]] = hit.get(names[c], 0) + ok
        extra += max(0, len(bs) - int((m.max(0) > 0.5).sum()) if len(bs) else 0)
    allh, allt = sum(hit.values()), sum(tot.values())
    top = sorted(tot, key=tot.get, reverse=True)[:8]
    print(f"полнота эмуляции {allh}/{allt} = {allh / max(allt, 1):.3f}; лишних рамок {extra}; "
          + ", ".join(f"{k} {hit[k]}/{tot[k]}" for k in top))


if __name__ == "__main__":
    main()
