"""Компиляция обрезанной YOLO-модели (ONNX) в программу для LinQ TPU (платформа H1M).

Запускается внутри Docker-образа с tpu_framework (SDK есть только под linux x86_64 / Python 3.12):

    docker run --rm --platform linux/amd64 -v "$PWD":/work linq-tpu-compiler:2026.9.45 \
        python tools/linq_compile/compile_tpu.py --spec models/pose_v8n_384x640.json \
        --calib data/calib --preset o5

Шаги (как в compile.py из SDK, но с реальными кадрами для калибровки):
  1. preliminary_model_conditioning — оптимизация графа;
  2. calibrate_torch на реальных кадрах (letterbox как в рантайме) -> quantize;
  3. сверка квантованной модели с ONNX (косинусная близость каждого выхода);
  4. compiler.compile_ (O5, при ошибке откат на O1) -> .tpu;
  5. в json-спецификацию модели записываются путь к .tpu и имена выходов.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

import numpy as np
import onnx

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)


def load_calibration(calib_dir: str, in_hw: tuple[int, int], n: int, seed: int = 0, resize: bool = False) -> np.ndarray:
    """resize=False — letterbox как у детекторов; True — простое масштабирование (классификаторы)."""
    import cv2

    from safetyvision.inference.yolo import preprocess

    files = sorted(sum((glob.glob(os.path.join(calib_dir, "**", e), recursive=True)
                        for e in ("*.jpg", "*.jpeg", "*.png")), []))
    if not files:
        raise SystemExit(f"Нет изображений для калибровки в {calib_dir}")
    rng = np.random.default_rng(seed)
    files = [files[i] for i in rng.permutation(len(files))[:n]]
    batch = []
    for f in files:
        img = cv2.imread(f)
        if img is None:
            continue
        if resize:
            x = cv2.cvtColor(cv2.resize(img, (in_hw[1], in_hw[0])), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            batch.append(x.transpose(2, 0, 1)[None])
        else:
            batch.append(preprocess(img, in_hw)[0])
    print(f"Калибровка: {len(batch)} изображений из {calib_dir}")
    return np.concatenate(batch, 0).astype(np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a.reshape(-1).astype(np.float64), b.reshape(-1).astype(np.float64)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def check_quantized(quant_model, onnx_path: str, sample: dict[str, np.ndarray], out_names: list[str]) -> dict:
    """Прогоняет квантованную модель (torch-граф с эмуляцией int-арифметики) и ONNX на одном кадре."""
    import onnxruntime as ort
    import torch

    try:
        from tpu_framework import TpuDtype
    except ImportError:
        from dnn_quant.api import TpuDtype

    import builtins

    builtins.np = np  # сгенерированный SDK torch-граф ссылается на глобальный np
    ref = dict(zip(out_names, ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
                   .run(out_names, sample)))
    g = quant_model.as_torch_graph(batch_size=1)
    anchors = g.get_outputs_anchors() | g.get_inputs_anchors()
    inp = quant_model.rescale({anchors[k]: v for k, v in sample.items()}, TpuDtype.Input)
    g.gm.eval()
    with torch.no_grad():
        outs = g.gm(*[torch.as_tensor(inp[n]) for n in g._input_layer_names])
    if not isinstance(outs, (tuple, list)):
        outs = (outs,)
    ordered = [anchors[n] for n in out_names]
    q = quant_model.rescale({n: o.detach().cpu().numpy() for n, o in zip(ordered, outs)}, TpuDtype.Output)
    report = {}
    for n in out_names:
        a = q[anchors[n]]
        r = ref[n]
        if a.shape != r.shape and a.ndim == 4:
            a = a.transpose(0, 3, 1, 2)  # NHWC -> NCHW
        report[n] = round(cosine(a, r), 4)
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="json-спецификация из tools/export_onnx.py")
    ap.add_argument("--calib", default=os.path.join(ROOT, "data", "calib"))
    ap.add_argument("--num-calib", type=int, default=48)
    ap.add_argument("--preset", default="o5", choices=["o1", "o3", "o5", "o5fgs"])
    ap.add_argument("--percentile", type=float, default=99.99,
                    help="samplewise_percentile для порогов (устойчивость к выбросам); 100 = максимум")
    ap.add_argument("--act-percentile", type=float,
                    help="activation_percentile: перцентиль |x| внутри тензора (срезает пространственные выбросы)")
    ap.add_argument("--fine-tune", type=int, default=0, help="эпох дообучения порогов (0 — без)")
    ap.add_argument("--skip-check", action="store_true")
    a = ap.parse_args()

    import tpu_framework as tf_
    from tpu_framework import (TPU_H1M, Network, QuantizedModel, RegularModel, TpuProgram, compiler,
                               preliminary_model_conditioning)

    spec_path = os.path.abspath(a.spec)
    spec = json.load(open(spec_path, encoding="utf-8"))
    mdir = os.path.dirname(spec_path)
    onnx_path = os.path.join(mdir, spec["onnx"])
    in_name = spec["input"]["name"]
    in_hw = tuple(spec["input"]["shape"][2:])
    is_cls = spec.get("task") == "classify"
    out_names = spec["outputs"] if is_cls else [lvl[k] for lvl in spec["levels"] for k in ("box", "cls", "kpt") if k in lvl]
    work = os.path.join(mdir, "build", spec["name"])
    os.makedirs(work, exist_ok=True)
    t0 = time.time()

    print("\n1/4 Оптимизация графа")
    m = onnx.load(onnx_path)
    m_opt = preliminary_model_conditioning(m)
    opt_path = os.path.join(work, "opt.onnx")
    onnx.save(m_opt, opt_path)

    print("\n2/4 Калибровка и квантование")
    calib = load_calibration(a.calib, in_hw, a.num_calib, resize=is_cls)
    regular = RegularModel(model=onnx.load(opt_path))
    data = {in_name: calib}
    pct = None if a.percentile >= 100 else a.percentile
    try:
        thr = regular.calibrate_torch(calibration_data=data, samplewise_percentile=pct,
                                      activation_percentile=a.act_percentile)
    except KeyError:
        mapping = regular.anchors_mapping
        data = {mapping[k]: v for k, v in data.items()}
        thr = regular.calibrate_torch(calibration_data=data, samplewise_percentile=pct,
                                      activation_percentile=a.act_percentile)
    if a.fine_tune:
        thr = regular.fine_tune_torch(thresholds=thr, fine_tuning_epochs=a.fine_tune, fine_tuning_data=data)
    RegularModel.dump_thresholds(os.path.join(work, "thresholds.json"), thr)
    qm = regular.quantize(thr)
    qname = f"quant_{spec['name']}.qm.onnx"
    qm.save(file_dir=work, file_name=qname)

    report = {}
    if not a.skip_check:
        try:
            report = check_quantized(qm, onnx_path, {in_name: calib[:1]}, out_names)
            print("Косинусная близость int8 vs fp32 по выходам:", report)
        except Exception as e:  # noqa: BLE001 — проверка вспомогательная, компиляцию не блокирует
            import traceback

            traceback.print_exc()
            print("Проверку квантованной модели пропускаю:", repr(e))

    print(f"\n3/4 Компиляция ({a.preset.upper()})")
    presets = {"o1": tf_.O1, "o5": tf_.O5, "o3": getattr(tf_, "O3", tf_.O1), "o5fgs": getattr(tf_, "O5_FGS", tf_.O5)}
    network, _ = Network.from_quantized_model(QuantizedModel.load(os.path.join(work, qname)))
    preset = a.preset
    try:
        executable, descr = compiler.compile_(hardware_parameters=TPU_H1M, network=network,
                                              parameters=presets[preset])
    except Exception as e:  # noqa: BLE001
        if preset == "o1":
            raise
        print(f"{preset.upper()} не скомпилировался ({e!r}), откат на O1")
        preset = "o1"
        network, _ = Network.from_quantized_model(QuantizedModel.load(os.path.join(work, qname)))
        executable, descr = compiler.compile_(hardware_parameters=TPU_H1M, network=network, parameters=tf_.O1)

    tpu_name = f"{spec['name']}_b1_{preset}_h1m.tpu"
    TpuProgram.from_executable(executable, descr).to_file(os.path.join(mdir, tpu_name))

    print("\n4/4 Обновление спецификации")
    descr_names = []
    try:
        items = descr.items() if isinstance(descr, dict) else enumerate(descr)
        for key, d in items:
            info = {"key": str(key)}
            for k, v in vars(d).items():
                if isinstance(v, (str, int, float, bool)) or (isinstance(v, (list, tuple)) and len(v) < 8):
                    info[k] = v if isinstance(v, (str, int, float, bool)) else [str(x) for x in v]
                else:
                    info[k] = str(v)[:60]
            descr_names.append(info)
    except Exception as e:  # noqa: BLE001
        descr_names.append({"error": repr(e)})
    spec["tpu"] = tpu_name
    spec["tpu_build"] = {"preset": preset, "calib_images": int(len(calib)), "percentile": pct,
                         "act_percentile": a.act_percentile, "fine_tune": a.fine_tune,
                         "quant_cosine": report, "tensor_descriptions": descr_names[:32],
                         "compile_s": round(time.time() - t0, 1)}
    # если имена выходов в программе изменятся — их можно сопоставить вручную через tpu_output_alias
    spec.setdefault("tpu_output_alias", {})
    json.dump(spec, open(spec_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Готово: {os.path.join(mdir, tpu_name)} за {time.time() - t0:.0f} c")


if __name__ == "__main__":
    main()
