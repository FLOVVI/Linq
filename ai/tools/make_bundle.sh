#!/usr/bin/env bash
# Собирает архив для сервера LinQ (Jupyter): код, спецификации моделей, .tpu-программы, конфиги, демо-видео.
# ONNX кладётся только с --with-onnx (нужен для сверки TPU vs ONNX в бенчмарке; +130 МБ).
#   bash tools/make_bundle.sh [--with-onnx]
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=dist/linq_bundle.tar.gz
mkdir -p dist
FILES=(safetyvision tools/linq_bench configs requirements-linq.txt data/samples)
FILES+=(models/*.json models/*.tpu)
# классификатор каски работает на CPU (int8 его ломает) — его ONNX нужен всегда (6 МБ)
if [[ "${1:-}" == "--with-onnx" ]]; then FILES+=(models/*.onnx); else FILES+=(models/*cls*.onnx); fi
[[ -d data/videos/demo ]] && FILES+=(data/videos/demo)
# заводские ролики с неподвижной камерой и зонами (configs/factory/*.yaml), 1280×720
[[ -d data/videos/factory ]] && FILES+=(data/videos/factory)
# пара синхронных камер CAVIAR — демо карты из двух камер (configs/caviar_2cam_calibrated.yaml)
compgen -G "data/videos/caviar/ThreePastShop1*.mpg" >/dev/null && FILES+=(data/videos/caviar/ThreePastShop1*.mpg)
COPYFILE_DISABLE=1 tar --no-xattrs --no-fflags --exclude='__pycache__' -czf "$OUT" "${FILES[@]}"
ls -lh "$OUT"
echo "Загрузите $OUT в Jupyter (/auto/cache/<LOGIN>), затем в терминале Jupyter:"
echo "  tar xzf linq_bundle.tar.gz && pip install --user -r requirements-linq.txt"
echo "  python tools/linq_bench/bench_tpu.py --iters 100 --streams 4"
echo "  python -m safetyvision run configs/demo_linq.yaml --backend tpu --save-video runs/linq_demo.mp4 --duration 30"
