"""Экспорт YOLOv8 (.pt) в ONNX с «сырыми» выходами головы для LinQ TPU.

Голова сети отдаёт только результаты свёрток (box/cls/kpt на каждый stride), без DFL, якорей,
sigmoid и NMS — всё это делает safetyvision.inference.yolo на CPU. Вход фиксированный
(LinQ не поддерживает динамические формы).

Пример:
    python tools/export_onnx.py --weights data/weights/yolov8n-pose.pt --name pose_v8n --imgsz 384 640
"""

from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path

import numpy as np
import onnx
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def raw_head_forward(self, x):
    outs = []
    for i in range(self.nl):
        outs.append(self.cv2[i](x[i]))
        outs.append(self.cv3[i](x[i]))
        if getattr(self, "kpt_shape", None) is not None:
            outs.append(self.cv4[i](x[i]))
    return tuple(outs)


class ConvClassifyHead(torch.nn.Module):
    """Голова YOLOv8-cls без Flatten/Gemm: Linear -> эквивалентная свёртка 1×1 на тензоре C×1×1.

    Компилятор LinQ не раскладывает Reshape из 4D в 2D перед Gemm (O5 и O1 падают), а свёртки
    и пулинг — его родные операции. Выход — логиты 1×K×1×1, softmax считается на CPU."""

    def __init__(self, head):
        super().__init__()
        self.conv, self.pool = head.conv, head.pool
        lin = head.linear
        self.fc = torch.nn.Conv2d(lin.in_features, lin.out_features, 1)
        self.fc.weight.data = lin.weight.data.view(lin.out_features, lin.in_features, 1, 1).clone()
        self.fc.bias.data = lin.bias.data.clone()

    def forward(self, x):
        if isinstance(x, list):
            x = torch.cat(x, 1)
        return self.fc(self.pool(self.conv(x)))


def export_classifier(yolo, weights: str, name: str, size: int, out_dir: Path, opset: int = 13) -> Path:
    """YOLOv8-cls: вход 1×3×S×S (RGB, 0..1, без нормализации), выход — логиты классов 1×K×1×1."""
    model = yolo.model.float().eval()
    model.fuse()
    ref_head = model.model[-1]
    ref_head.export = True
    x0 = torch.rand(1, 3, size, size)
    with torch.no_grad():
        ref = model(x0)
    model.model[-1] = ConvClassifyHead(ref_head)
    for attr in ("f", "i", "type"):  # служебные поля Ultralytics для обхода графа
        setattr(model.model[-1], attr, getattr(ref_head, attr))
    for p in model.parameters():
        p.requires_grad_(False)
    with torch.no_grad():
        got = model(x0).flatten(1).softmax(1)
    print("сверка головы: max |Δp| =", float((got - ref).abs().max()))
    out_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = out_dir / f"{name}_{size}.onnx"
    torch.onnx.export(model, torch.zeros(1, 3, size, size), str(onnx_path), input_names=["images"],
                      output_names=["logits"], opset_version=opset, do_constant_folding=True, dynamo=False)
    m = onnx.load(str(onnx_path))
    try:
        import onnxslim

        m = onnxslim.slim(m)
    except Exception as e:  # noqa: BLE001
        print("onnxslim пропущен:", e)
    onnx.save(m, str(onnx_path))
    spec = {"name": f"{name}_{size}", "task": "classify", "source_weights": str(weights),
            "input": {"name": "images", "shape": [1, 3, size, size], "format": "RGB, 0..1, NCHW, resize"},
            "outputs": ["logits"], "output_kind": "logits", "classes": [yolo.names[i] for i in range(len(yolo.names))],
            "onnx": onnx_path.name, "tpu": None}
    spec_path = out_dir / f"{name}_{size}.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ONNX:", onnx_path, "\nSPEC:", spec_path, "\nОператоры графа:", ", ".join(sorted({n.op_type for n in m.graph.node})))
    return spec_path


def export(weights: str, name: str, imgsz: tuple[int, int], out_dir: Path, opset: int = 13,
           class_names: list[str] | None = None) -> Path:
    from ultralytics import YOLO

    yolo = YOLO(weights)
    if yolo.task == "classify":
        return export_classifier(yolo, weights, name, imgsz[0], out_dir, opset)
    model = yolo.model.float().eval()
    model.fuse()
    head = model.model[-1]
    head.forward = types.MethodType(raw_head_forward, head)
    for p in model.parameters():
        p.requires_grad_(False)

    is_pose = getattr(head, "kpt_shape", None) is not None
    strides = [int(s) for s in head.stride.tolist()]
    out_names, levels = [], []
    for s in strides:
        lvl = {"stride": s, "box": f"box_s{s}", "cls": f"cls_s{s}"}
        out_names += [lvl["box"], lvl["cls"]]
        if is_pose:
            lvl["kpt"] = f"kpt_s{s}"
            out_names.append(lvl["kpt"])
        levels.append(lvl)

    h, w = imgsz
    assert h % 32 == 0 and w % 32 == 0, "размер входа должен быть кратен 32"
    dummy = torch.zeros(1, 3, h, w)
    out_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = out_dir / f"{name}_{h}x{w}.onnx"
    torch.onnx.export(model, dummy, str(onnx_path), input_names=["images"], output_names=out_names,
                      opset_version=opset, do_constant_folding=True, dynamo=False)
    m = onnx.load(str(onnx_path))
    try:
        import onnxslim

        m = onnxslim.slim(m)
    except Exception as e:  # noqa: BLE001
        print("onnxslim пропущен:", e)
    onnx.checker.check_model(m)
    onnx.save(m, str(onnx_path))

    names = class_names or [yolo.names[i] for i in range(len(yolo.names))]
    spec = {
        "name": f"{name}_{h}x{w}",
        "task": "pose" if is_pose else "detect",
        "source_weights": str(weights),
        "input": {"name": "images", "shape": [1, 3, h, w], "format": "RGB, 0..1, NCHW, letterbox 114"},
        "levels": levels,
        "reg_max": int(head.reg_max),
        "classes": names,
        "kpt_shape": list(head.kpt_shape) if is_pose else None,
        "onnx": onnx_path.name,
        "tpu": None,
    }
    spec_path = out_dir / f"{name}_{h}x{w}.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ONNX:", onnx_path, "\nSPEC:", spec_path)
    ops = sorted({n.op_type for n in m.graph.node})
    print("Операторы графа:", ", ".join(ops))
    return spec_path


def verify(spec_path: Path, weights: str, image: str) -> None:
    """Сверяет наш декодер (onnxruntime + numpy) с штатным предсказанием Ultralytics."""
    import cv2
    from ultralytics import YOLO

    from safetyvision.inference.yolo import YoloModel

    img = cv2.imread(image)
    ours = YoloModel(str(spec_path), backend="onnx", conf=0.3, iou=0.5)(img)
    spec = json.loads(spec_path.read_text())
    h, w = spec["input"]["shape"][2:]
    ref = YOLO(weights).predict(img, imgsz=[h, w], conf=0.3, iou=0.5, verbose=False)[0]
    rb = ref.boxes.xyxy.cpu().numpy()
    print(f"наш декодер: {len(ours)} объектов, ultralytics: {len(rb)}")
    if len(ours) and len(rb):
        from safetyvision.geometry.boxes import iou_matrix

        best = iou_matrix(ours.boxes, rb).max(1)
        print("средний IoU с эталоном: %.3f" % float(np.mean(best)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--imgsz", nargs=2, type=int, default=[384, 640], metavar=("H", "W"))
    ap.add_argument("--out", default=str(ROOT / "models"))
    ap.add_argument("--opset", type=int, default=13)
    ap.add_argument("--verify-image")
    a = ap.parse_args()
    sp = export(a.weights, a.name, tuple(a.imgsz), Path(a.out), a.opset)
    if a.verify_image and json.loads(sp.read_text())["task"] != "classify":
        verify(sp, a.weights, a.verify_image)
