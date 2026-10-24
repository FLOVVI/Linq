"""Замер скорости на ускорителе LinQ (запускать на сервере LinQ в Jupyter / терминале).

1) Каждая .tpu-программа отдельно: задержка инференса (mean / p50 / p95) и FPS.
2) Все модели вместе, как в пайплайне: N «камер» по очереди (pose каждый кадр, СИЗ и объекты —
   через кадр) -> сколько потоков видео тянет одна плата при заданном FPS на поток.
3) Сверка с ONNX (если есть onnxruntime): совпадение выходов TPU и исходной модели.

На сервере хакатона платы в контейнере нет: запросы идут через облачный брокер LinQ
(safetyvision.inference.backends.CloudTpuBackend), поэтому задержка включает сеть и очередь.
Отдельно меряется пропускная способность, когда несколько кадров «в полёте» одновременно.

Нагрузка на сервер ограничена: по умолчанию 5 прогревочных + 100 замерных вызовов на модель.

    python tools/linq_bench/bench_tpu.py --iters 100 --streams 4
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import sys
import time

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)


def stats(ms: list[float]) -> dict:
    a = np.asarray(ms)
    return {"n": len(a), "mean_ms": round(float(a.mean()), 3), "p50_ms": round(float(np.percentile(a, 50)), 3),
            "p95_ms": round(float(np.percentile(a, 95)), 3), "fps": round(1000.0 / float(a.mean()), 1)}


def real_input(spec: dict, image: str | None) -> np.ndarray:
    from safetyvision.inference.yolo import preprocess

    h, w = spec["input"]["shape"][2:]
    if image:
        import cv2

        img = cv2.imread(image)
        if img is not None:
            return preprocess(img, (h, w))[0]
    return np.random.default_rng(0).random((1, 3, h, w), dtype=np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=sorted(glob.glob(os.path.join(ROOT, "models", "*.json"))))
    ap.add_argument("--iters", type=int, default=100)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--inflight", type=int, default=4, help="задач в полёте в тесте пропускной способности")
    ap.add_argument("--streams", type=int, default=4, help="сколько камер имитировать в тесте 2")
    ap.add_argument("--image", default=os.path.join(ROOT, "data", "samples", "bus.jpg"))
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "bench_tpu.json"))
    a = ap.parse_args()

    from safetyvision.inference.backends import make_backend

    report = {"host": platform.node(), "time": time.strftime("%Y-%m-%d %H:%M:%S"), "models": {}, "pipeline": {}}

    loaded = {}
    for sp in a.models:
        spec = json.load(open(sp, encoding="utf-8"))
        if not spec.get("tpu"):
            print(f"- {spec['name']}: нет .tpu, пропуск")
            continue
        be = make_backend("tpu", spec, os.path.dirname(sp))
        report.setdefault("backend", be.name)
        x = {spec["input"]["name"]: real_input(spec, a.image)}
        for _ in range(a.warmup):
            out = be.run(x)
        print(f"  {spec['name']}: выходы {[(k, list(np.asarray(v).shape)) for k, v in out.items()]}, "
              f"воркер {getattr(be, 'last_worker', {})}")
        ms = []
        for _ in range(a.iters):
            t0 = time.perf_counter()
            out = be.run(x)
            ms.append((time.perf_counter() - t0) * 1000)
        r = stats(ms)
        if getattr(be, "tpu_latency", None) and be.tpu_latency.samples:
            t = be.tpu_latency.summary()  # чистое время на плате по отчёту воркера
            r["tpu_mean_ms"], r["tpu_p95_ms"] = round(t["mean_ms"], 2), round(t["p95_ms"], 2)
        if hasattr(be, "run_many"):  # пропускная способность при нескольких кадрах в полёте
            n = max(a.iters // a.inflight, 1)
            t0 = time.perf_counter()
            for _ in range(n):
                be.run_many([x] * a.inflight)
            r["throughput_fps"] = round(n * a.inflight / (time.perf_counter() - t0), 1)
        # сверка с ONNX
        try:
            import onnxruntime as ort

            sess = ort.InferenceSession(os.path.join(os.path.dirname(sp), spec["onnx"]), providers=["CPUExecutionProvider"])
            names = [o.name for o in sess.get_outputs()]
            ref = dict(zip(names, sess.run(names, x)))
            cos = {}
            for n in names:
                if n in out:
                    t = np.asarray(out[n], np.float32)
                    o = ref[n]
                    if t.shape != o.shape and t.ndim == 4:
                        t = t.transpose(0, 3, 1, 2)
                    t, o = t.reshape(-1), o.reshape(-1)
                    cos[n] = round(float(t @ o / (np.linalg.norm(t) * np.linalg.norm(o) + 1e-12)), 4)
            r["cosine_vs_onnx"] = cos
            r["output_shapes"] = {k: list(np.asarray(v).shape) for k, v in out.items()}
        except Exception as e:  # noqa: BLE001
            r["cosine_vs_onnx"] = f"нет onnxruntime/onnx: {e}"
        report["models"][spec["name"]] = r
        loaded[spec["name"]] = (spec, be, x)
        print(f"- {spec['name']:<22} {r['mean_ms']:7.2f} мс  p95 {r['p95_ms']:7.2f}  {r['fps']:7.1f} FPS"
              + (f"  | {a.inflight} в полёте: {r['throughput_fps']} FPS" if "throughput_fps" in r else "")
              + (f"  | на плате {r['tpu_mean_ms']} мс (p95 {r['tpu_p95_ms']})" if "tpu_mean_ms" in r else ""))

    # тест 2: пайплайн N камер на одной плате
    # классификатор каски в цикл кадра не входит: он вызывается только на головы без найденной каски
    det = [k for k in loaded if loaded[k][0].get("task") != "classify"]
    roles = {"pose": [k for k in det if k.startswith("pose")],
             "ppe": [k for k in det if k.startswith("ppe")],
             "objects": [k for k in det if not k.startswith(("pose", "ppe"))]}
    if roles["pose"]:
        n_frames = max(a.iters // 2, 20)
        t0 = time.perf_counter()
        calls = 0
        for f in range(n_frames):
            for role, names in roles.items():
                if role != "pose" and f % 2:
                    continue  # СИЗ и объекты — через кадр (every_n: 2)
                for nm in names[:1]:
                    spec, be, x = loaded[nm]
                    if hasattr(be, "run_many"):  # облако: кадры всех камер уходят одной пачкой
                        be.run_many([x] * a.streams)
                    else:
                        for _ in range(a.streams):
                            be.run(x)
                    calls += a.streams
        dt = time.perf_counter() - t0
        per_stream = n_frames / dt
        report["pipeline"] = {"streams": a.streams, "frames_per_stream": n_frames, "seconds": round(dt, 2),
                              "fps_per_stream": round(per_stream, 2), "fps_total": round(per_stream * a.streams, 2),
                              "nn_calls": calls, "models": {r: v[:1] for r, v in roles.items()}}
        print(f"\nПайплайн: {a.streams} потоков × {per_stream:.1f} FPS = {per_stream * a.streams:.1f} кадров/с "
              f"(только нейросети на TPU)")

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(report, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("Отчёт:", a.out)


if __name__ == "__main__":
    main()
