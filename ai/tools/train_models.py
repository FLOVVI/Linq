"""Обучение собственных моделей (воспроизводимость). Наборы собираются скриптами из tools/datasets.

    python tools/train_models.py helmet_cls      # каска / голова без каски, 96×96 (YOLOv8n-cls)
    python tools/train_models.py helmet_cls_v2   # дообучение на трудных негативах (кепки, шапки)
    python tools/train_models.py hazards         # сигарета / огонь / дым / погрузчик (YOLOv8s)

Дальше: tools/export_onnx.py -> tools/linq_compile/compile_tpu.py (см. AI.md).
"""

from __future__ import annotations

import argparse
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.path.join(ROOT, "data", "datasets")
RUNS = os.path.join(ROOT, "runs", "train")
AUG_CLS = dict(hsv_h=0.02, hsv_s=0.5, hsv_v=0.4, fliplr=0.5, erasing=0.2)

RECIPES = {
    # build_helmet_cls.py -> data/datasets/helmet_cls
    "helmet_cls": dict(weights="yolov8n-cls.pt", data=f"{DATA}/helmet_cls", imgsz=96, epochs=15, batch=128,
                       patience=5, **AUG_CLS),
    # mine_hard_negatives.py + ручная отбраковка шлемов -> data/datasets/helmet_cls_v2
    "helmet_cls_v2": dict(weights=f"{ROOT}/models/src/helmet_cls_v8n_96.pt", data=f"{DATA}/helmet_cls_v2",
                          imgsz=96, epochs=8, batch=128, lr0=0.002, warmup_epochs=0, **AUG_CLS),
    # build_hazards.py -> data/datasets/hazards; старт с COCO-весов (погрузчик/дым близки к классам COCO).
    # 512 px: на Apple M4 (MPS) YOLOv8s@640 идёт 1.8 с/шаг (13 мин/эпоха), @512 — заметно быстрее
    "hazards": dict(weights=f"{ROOT}/data/weights/yolov8s.pt", data=f"{DATA}/hazards/hazards.yaml", imgsz=512,
                    epochs=20, batch=16, patience=8, close_mosaic=5, mixup=0.05, degrees=3.0),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("recipe", choices=sorted(RECIPES))
    ap.add_argument("--device", default="mps", help="mps (Mac), 0 (CUDA), cpu")
    ap.add_argument("--epochs", type=int)
    ap.add_argument("--init", help="начальные веса вместо указанных в рецепте (например, после прерванного запуска)")
    a = ap.parse_args()
    from ultralytics import YOLO

    r = dict(RECIPES[a.recipe])
    model = YOLO(a.init or r.pop("weights"))
    r.pop("weights", None)
    if a.epochs:
        r["epochs"] = a.epochs
    model.train(device=a.device, workers=4, project=RUNS, name=a.recipe, exist_ok=True, verbose=False, **r)


if __name__ == "__main__":
    main()
