"""Командная строка.

    python -m safetyvision rules                         # каталог правил и позиции в векторе
    python -m safetyvision run configs/demo.yaml --save-video out.mp4
    python -m safetyvision serve configs/demo.yaml --port 8000
    python -m safetyvision calibrate configs/demo.yaml --seconds 90   # авто-калибровка камер -> yaml
    python -m safetyvision bridge configs/site_bridge.yaml            # вместе с сайтом команды (LinQ-feature-frontend)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import cv2
import numpy as np


def _load(args):
    from .config import load_site

    overrides = {}
    if getattr(args, "backend", None):
        overrides["models"] = {"backend": args.backend}
    site = load_site(args.config, overrides)
    if getattr(args, "source", None):
        site.cameras = site.cameras[:1]
        site.cameras[0].source = os.path.abspath(args.source)
    if getattr(args, "out", None):
        site.events.output_dir = os.path.abspath(args.out)
    if getattr(args, "realtime", False):
        for c in site.cameras:
            c.realtime = True
    return site


def cmd_rules(args):
    from .catalog import RULES

    print(f"{'#':>2}  {'код':<18} {'важность':<9} {'нейросети':<16} описание")
    for r in RULES:
        print(f"{r.index:>2}  {r.code:<18} {r.severity:<9} {'+'.join(r.models):<16} {r.title}")
    print("\nПример вектора: [1,0,1,0,0,0,0,0,0] — каска обязательна, курить нельзя, остальное не проверяется.")


def _compose(pipe, cams: list[str], width: int = 1280) -> np.ndarray:
    """Кадры всех камер плиткой + миникарта справа."""
    views = [pipe.camera_view(c) for c in cams]
    views = [v for v in views if v is not None]
    if not views:
        return np.zeros((360, 640, 3), np.uint8)
    cols = 1 if len(views) == 1 else 2
    tw = width // cols
    tiles = []
    for v in views:
        s = tw / v.shape[1]
        tiles.append(cv2.resize(v, (tw, int(v.shape[0] * s))))
    th = max(t.shape[0] for t in tiles)
    tiles = [cv2.copyMakeBorder(t, 0, th - t.shape[0], 0, 0, cv2.BORDER_CONSTANT) for t in tiles]
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
    left = np.vstack(rows)
    # схема рисуется сразу в размере кадра: при уменьшении готовой картинки мелкие подписи не читаются
    mm = pipe.minimap(long_side=max(480, int(left.shape[0] * 0.85)))
    s = left.shape[0] / mm.shape[0]
    mm = cv2.resize(mm, (max(1, int(mm.shape[1] * s)), left.shape[0]))
    if mm.shape[1] > left.shape[1] * 0.8:
        s = left.shape[1] * 0.8 / mm.shape[1]
        mm = cv2.resize(mm, (int(mm.shape[1] * s), int(mm.shape[0] * s)))
        mm = cv2.copyMakeBorder(mm, 0, left.shape[0] - mm.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    return np.hstack([left, mm])


def cmd_run(args):
    from .pipeline import Pipeline

    site = _load(args)
    pipe = Pipeline(site)
    writer = None
    state = {"last": 0.0, "writer": None}
    cams = [c.id for c in site.cameras]

    def on_frame(p, cam):
        if args.save_video and cam.id == cams[-1]:
            img = _compose(p, cams)
            if state["writer"] is None:
                h, w = img.shape[:2]
                state["size"] = (w - w % 2, h - h % 2)
                # H.264 есть не везде (на сервере LinQ его нет) — тот же выбор кодека, что и для клипов
                from .events.recorder import _pick_writer

                w, path = _pick_writer(os.path.splitext(args.save_video)[0], site.cameras[-1].process_fps,
                                       state["size"])
                state["writer"] = w or False  # False — кодека нет, больше не пытаемся
                print("видео:", path or "не удалось открыть ни один кодек", flush=True)
            if state["writer"]:
                state["writer"].write(cv2.resize(img, state["size"]))
        if time.time() - state["last"] > 5:
            state["last"] = time.time()
            perf = p.perf()
            cams_s = ", ".join(f"{k}: {v['fps']} FPS/{v['proc_ms_mean']} мс" for k, v in perf["cameras"].items())
            print(f"[{perf['uptime_s']:>6.0f} c] кадров {perf['frames_total']}, {cams_s}", flush=True)

    t0 = time.time()
    pipe.run(max_frames=args.max_frames, duration_s=args.duration, on_frame=on_frame)
    if state["writer"]:
        state["writer"].release()
    perf = pipe.perf()
    out = os.path.join(pipe.out_dir, "perf.json")
    json.dump(perf, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    cv2.imwrite(os.path.join(pipe.out_dir, "minimap.png"), pipe.minimap())
    evs = pipe.store.query(limit=10 ** 6)
    print(f"\nГотово за {time.time() - t0:.1f} c: {perf['frames_total']} кадров, событий: {len(evs)}")
    for m in perf["models"]:
        if "mean_ms" in m:
            print(f"  модель {m['name']:<6} ({m['backend']}): {m['mean_ms']:.1f} мс/кадр, p95 {m['p95_ms']:.1f} мс, "
                  f"{m['fps']:.1f} FPS, вызовов {m['calls']}"
                  + (f", на плате {m['tpu_mean_ms']:.1f} мс" if "tpu_mean_ms" in m else ""))
    for e in reversed(evs):
        print(f"  [{e['start_time']} — {e['end_time']}] {e['camera_id']} {e['title']} ({e['subject']}) "
              f"{e['duration_s']} c, клип {e['clip']}")
    print("Журнал:", os.path.join(pipe.out_dir, "events.jsonl"))


def cmd_serve(args):
    import uvicorn

    from .server import create_app

    site = _load(args)
    app = create_app(site, autostart=not args.no_start)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


def cmd_bridge(args):
    from .site_bridge import Bridge

    Bridge(args.config, backend=args.backend).run()


def cmd_calibrate(args):
    """Прогоняет записи, пока все камеры с calibration.auto не откалибруются, и печатает готовый yaml."""
    import yaml

    from .pipeline import Pipeline

    site = _load(args)
    pipe = Pipeline(site)

    def done(p, cam):
        pend = [c for c in p.cams.values() if c.cfg.calibration and c.cfg.calibration.auto is not None
                and (c.local is None or (c.cfg.calibration.align_to and c.id not in p.alignments))]
        if not pend:
            p.stop()

    pipe.run(duration_s=args.seconds, on_frame=done)
    out = {}
    for c in pipe.cams.values():
        d = {"calibration_info": c.calib_info}
        if c.local is not None and c.local.camera is not None:
            d["camera"] = c.local.camera.to_dict()
        if c.id in pipe.alignments:
            M = pipe.alignments[c.id]
            d["alignment_to"] = c.cfg.calibration.align_to
            d["alignment"] = pipe.align_info.get(c.id)
        if c.mapping is not None:
            d["homography"] = c.mapping.H.round(8).tolist()
        out[c.id] = d
    print(yaml.safe_dump(out, allow_unicode=True, sort_keys=False))
    snap = pipe.calibration_snapshot()
    if snap:
        print("# вставьте в cameras[].calibration (вместо auto/align_to), чтобы карта была готова сразу:")
        print(yaml.safe_dump(snap, allow_unicode=True, sort_keys=False, default_flow_style=None))
    cv2.imwrite(os.path.join(pipe.out_dir, "minimap_calibrated.png"), pipe.minimap())


def main(argv=None):
    ap = argparse.ArgumentParser(prog="safetyvision", description="Контроль нарушений ТБ по видео (LinQ TPU)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("rules").set_defaults(fn=cmd_rules)

    r = sub.add_parser("run", help="обработать камеры из конфига")
    r.add_argument("config")
    r.add_argument("--backend", choices=["onnx", "tpu"])
    r.add_argument("--max-frames", type=int)
    r.add_argument("--duration", type=float)
    r.add_argument("--save-video", help="записать видео с разметкой и миникартой")
    r.add_argument("--realtime", action="store_true", help="файлы проигрывать в реальном времени")
    r.add_argument("--source", help="заменить источник первой камеры (файл/rtsp/номер веб-камеры)")
    r.add_argument("--out", help="папка для событий/клипов")
    r.set_defaults(fn=cmd_run)

    s = sub.add_parser("serve", help="HTTP API + веб-просмотр")
    s.add_argument("config")
    s.add_argument("--backend", choices=["onnx", "tpu"])
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--no-start", action="store_true")
    s.add_argument("--realtime", action="store_true")
    s.set_defaults(fn=cmd_serve)

    b = sub.add_parser("bridge", help="работать вместе с сайтом команды: камеры и правила оттуда, события туда")
    b.add_argument("config", nargs="?", default="configs/site_bridge.yaml")
    b.add_argument("--backend", choices=["onnx", "tpu"])
    b.set_defaults(fn=cmd_bridge)

    c = sub.add_parser("calibrate", help="авто-калибровка камер по людям")
    c.add_argument("config")
    c.add_argument("--backend", choices=["onnx", "tpu"])
    c.add_argument("--seconds", type=float, default=120)
    c.set_defaults(fn=cmd_calibrate)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
