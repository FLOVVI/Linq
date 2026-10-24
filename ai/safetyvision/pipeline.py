"""Конвейер: камеры -> нейросети (LinQ TPU / ONNX) -> треки -> карта -> правила -> события.

Один поток обработки по очереди берёт кадры со всех камер (для записей — строго по времени,
чтобы камеры одного помещения шли синхронно). Все нейросети вызываются из этого потока,
поэтому одна плата LinQ обслуживает несколько видеопотоков без гонок.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import cv2
import numpy as np

from .analytics.evaluators import VEHICLE_KINDS, Observation, ObjectSet, RuleEvaluator
from .catalog import RULE_BY_CODE, RULES
from .config import Calibration, CameraConfig, SiteConfig, ZoneConfig, parse_zone
from .events.aggregator import Event, EventAggregator, TaggedObservation
from .events.recorder import ClipRecorder
from .events.sinks import EventStore, JsonlSink, WebhookSink
from .fusion import GlobalTracker
from .geometry.autocalib import CalibrationCollector, SyncedPositions, align_cameras
from .geometry.homography import CameraModel, GroundMapping, rigid2d
from .geometry.mapbuilder import MapBuilder, MapCanvas
from .geometry.zones import DynamicAnchor, ZoneIndex
from .analytics.crops import head_crop
from .inference.yolo import ClassifierModel, Detections, YoloModel
from .render import draw_camera, draw_minimap
from .sources import FramePacket, open_source
from .tracking.bytetrack import ByteTracker, Track

PPE_RULES = {"helmet", "vest", "gloves", "goggles"}
OBJECT_RULES = {"smoking", "phone", "vehicle_proximity", "fire"}
OPERATOR_EXEMPT = {"danger_zone", "vehicle_proximity", "running"}  # не действуют на водителя в кабине техники
OBJECT_TITLES = {"smoke": "дым", "fire": "огонь", "smoking": "сигарета", "phone": "телефон"}
# короткие подписи над людьми на кадре (полные названия — в событиях и API): длинные строки
# «Нет спецодежды (жилет/комбинезон), Нахождение в опасной зоне» налезали друг на друга
SHORT_TITLES = {"helmet": "без каски", "vest": "без жилета", "smoking": "курит", "phone": "телефон", "running": "бег",
                "danger_zone": "опасная зона", "vehicle_proximity": "у техники", "fall": "падение",
                "gloves": "без перчаток", "goggles": "без очков"}
# параллельные вызовы моделей одного кадра (у каждой модели свой бэкенд со своей блокировкой)
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sv-model")


class ModelSet:
    def __init__(self, site: SiteConfig):
        self.site = site
        self.models: dict[str, YoloModel] = {}
        self.cfg = site.models
        for name, mc in site.models.items():
            spec_path = site.resolve(mc.spec)
            spec = json.load(open(spec_path, encoding="utf-8"))
            class_conf = dict(mc.class_conf)
            if mc.classes:
                for c in spec["classes"]:
                    if c not in mc.classes:
                        class_conf[c] = 1.01  # класс не нужен — не декодируем
            if spec.get("task") == "classify":
                self.models[name] = ClassifierModel(spec_path, backend=mc.backend or site.backend,
                                                    **site.backend_options)
                continue
            self.models[name] = YoloModel(spec_path, backend=mc.backend or site.backend, conf=mc.conf, iou=mc.iou,
                                          class_conf=class_conf, **site.backend_options)

    def by_role(self, role: str) -> list[tuple[str, YoloModel]]:
        return [(n, m) for n, m in self.models.items() if self.cfg[n].role == role]

    def stats(self) -> list[dict[str, Any]]:
        return [{"name": n, "role": self.cfg[n].role, "every_n": self.cfg[n].every_n, **m.stats()}
                for n, m in self.models.items()]


def _person_dets(pose: Detections) -> Detections:
    return pose.of("person") if "person" in pose.names else pose


def _crop_for_people(frame_hw, boxes: np.ndarray, in_hw: tuple[int, int], min_gain: float = 1.3):
    """Окно вокруг людей с пропорциями входа сети: мелкие СИЗ получают больше пикселей."""
    if len(boxes) == 0:
        return None
    h, w = frame_hw
    x1, y1 = boxes[:, 0].min(), boxes[:, 1].min()
    x2, y2 = boxes[:, 2].max(), boxes[:, 3].max()
    pw, ph = x2 - x1, y2 - y1
    x1, x2 = x1 - 0.12 * pw - 16, x2 + 0.12 * pw + 16
    y1, y2 = y1 - 0.12 * ph - 16, y2 + 0.06 * ph + 8
    ar = in_hw[1] / in_hw[0]
    cw, ch = x2 - x1, y2 - y1
    if cw / ch < ar:
        cw = ch * ar
    else:
        ch = cw / ar
    if cw >= w / min_gain or ch >= h / min_gain:
        return None
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    x1 = int(np.clip(cx - cw / 2, 0, w - cw))
    y1 = int(np.clip(cy - ch / 2, 0, h - ch))
    return x1, y1, int(x1 + cw), int(y1 + ch)


def _speed(points_t: np.ndarray, pts: np.ndarray, window: float = 1.0) -> float | None:
    """Скорость по МНК-наклону траектории за последнее окно (устойчиво к дрожанию рамки)."""
    if len(points_t) < 4:
        return None
    m = points_t >= points_t[-1] - window
    t, p = points_t[m], pts[m]
    if len(t) < 4 or t[-1] - t[0] < 0.5:
        return None
    tc = t - t.mean()
    den = float((tc ** 2).sum())
    vx = float((tc * (p[:, 0] - p[:, 0].mean())).sum() / den)
    vy = float((tc * (p[:, 1] - p[:, 1].mean())).sum() / den)
    return math.hypot(vx, vy)


# тон в HSV OpenCV (0..180): цвета жилетов и спецодежды, которые можно задать в rule_params.vest.vest_colors
VEST_HUES = {"red": [(0, 6), (172, 180)], "orange": [(6, 20)], "yellow": [(20, 34)], "lime": [(34, 50)],
             "green": [(50, 85)], "blue": [(95, 128)]}
# минимальные насыщенность и яркость: флуоресцентные цвета яркие по природе, синяя ткань темнее (и в тени
# остаётся насыщенной, но теряет яркость)
VEST_SV = {"blue": (60, 50), "green": (70, 55)}
VEST_SV_DEFAULT = (90, 70)


def _color_fraction(frame: np.ndarray, box, colors: list[str]) -> float | None:
    """Доля пикселей цвета жилета на корпусе: в середине корпуса — или по обоим бокам сразу
    (расстёгнутый жилет поверх тёмной куртки виден только полами слева и справа)."""
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    h = y2 - y1
    y1, y2 = y1 + h // 6, y2 - h // 6
    H, W = frame.shape[:2]
    x1, y1, x2, y2 = max(x1, 0), max(y1, 0), min(x2, W), min(y2, H)
    if x2 - x1 < 6 or y2 - y1 < 4:
        return None
    hsv = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    m = np.zeros(hue.shape, bool)
    for c in colors:
        smin, vmin = VEST_SV.get(c, VEST_SV_DEFAULT)
        for lo, hi in VEST_HUES.get(c, []):
            m |= (hue >= lo) & (hue < hi) & (sat >= smin) & (val >= vmin)
    w = m.shape[1]
    third = max(1, w // 3)
    inner = m[:, w // 5: w - w // 5].mean()
    sides = min(m[:, :third].mean(), m[:, -third:].mean())
    return float(max(inner, sides))


def _dedup_vehicles(boxes: np.ndarray, scores: np.ndarray, kinds: list[str]):
    """Одну машину часто находят две модели (погрузчик — «forklift» и COCO «truck»): оставляем одну рамку,
    вид — погрузчик, если его нашла хоть одна модель."""
    if len(boxes) < 2:
        return boxes, scores, kinds
    from .geometry.boxes import iou_matrix

    order = np.argsort(-np.asarray(scores))
    m = iou_matrix(boxes, boxes)
    area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    keep, kk = [], []
    used = np.zeros(len(boxes), bool)
    for i in order:
        if used[i]:
            continue
        ix1, iy1 = np.maximum(boxes[i, :2], boxes[:, :2]).T
        ix2, iy2 = np.minimum(boxes[i, 2:], boxes[:, 2:]).T
        inter = np.clip(ix2 - ix1, 0, None) * np.clip(iy2 - iy1, 0, None)
        same = (m[i] > 0.5) | (inter / np.minimum(area[i], area).clip(1) > 0.8)
        same &= ~used
        used |= same
        keep.append(i)
        kk.append("forklift" if any(kinds[j] == "forklift" for j in np.flatnonzero(same)) else kinds[i])
    keep = np.array(keep)
    return boxes[keep], np.asarray(scores)[keep], kk


def _is_operator(pbox, vehicles: list[dict]) -> bool:
    """Человек, чья рамка почти целиком внутри рамки техники, — водитель в кабине."""
    pa = max(float((pbox[2] - pbox[0]) * (pbox[3] - pbox[1])), 1.0)
    for v in vehicles:
        b = v["box"]
        iw = min(pbox[2], b[2]) - max(pbox[0], b[0])
        ih = min(pbox[3], b[3]) - max(pbox[1], b[1])
        if iw > 0 and ih > 0 and iw * ih / pa > 0.6:
            return True
    return False


def _speed_pinhole(hist: np.ndarray, frame_hw: tuple[int, int], hfov_deg: float = 60.0,
                   body_h: float = 1.7) -> float | None:
    """Скорость человека без калибровки пола: модель камеры-обскуры по росту в пикселях.

    Расстояние Z = f·H/h, поперечное смещение X = (u − cx)·H/h. Ловит и бег поперёк кадра, и бег
    на камеру / от камеры (растёт или падает рост в пикселях). Рамки, обрезанные краем кадра, не берём.
    hist: (t, foot_x, foot_y, box_h)."""
    h_img, w_img = frame_hw
    f = w_img / 2 / math.tan(math.radians(hfov_deg) / 2)
    t, u, v, bh = hist[:, 0], hist[:, 1], hist[:, 2], hist[:, 3]
    edge = 0.01 * h_img
    ok = (v < h_img - edge) & (v - bh > edge) & (bh > 0.08 * h_img)
    if ok.sum() < 4:
        return None
    t, u, bh = t[ok], u[ok], np.maximum(bh[ok], 1.0)
    X = (u - w_img / 2) * body_h / bh
    Z = f * body_h / bh
    return _speed(t, np.c_[X, Z])


class CameraRuntime:
    def __init__(self, cfg: CameraConfig, pipe: "Pipeline"):
        self.cfg, self.pipe, self.id = cfg, pipe, cfg.id
        self.source = None
        self.tracker = ByteTracker()
        self.vtracker = ByteTracker(high_thresh=0.4, low_thresh=0.1, new_track_thresh=0.45, track_buffer_s=2.0)
        self.mapping: GroundMapping | None = None  # кадр -> карта
        self.local: GroundMapping | None = None  # кадр -> пол в системе камеры (авто-калибровка)
        self.collector: CalibrationCollector | None = None
        self.calib_info: dict[str, Any] = {}
        self.sync = SyncedPositions()
        self.frame_hw: tuple[int, int] | None = None
        self.n = 0
        self.last_pkt: FramePacket | None = None
        self.last_state: dict[str, Any] = {}
        self.proc_ms: deque = deque(maxlen=100)
        self.e2e_ms: deque = deque(maxlen=100)
        self.ts_hist: deque = deque(maxlen=50)
        self.persons: list[Track] = []
        self.person_map: dict[int, np.ndarray | None] = {}
        self.vehicles: list[dict[str, Any]] = []
        self.subjects: dict[int, str] = {}
        self.marks: list[tuple[np.ndarray, str, float]] = []  # предметы, участвующие в правилах на этом кадре
        self.fire_disp: tuple[np.ndarray, str, float] | None = None  # сглаженная рамка очага для отрисовки

    # ------------------------------------------------------------- калибровка
    def init_mapping(self, frame_hw: tuple[int, int]) -> None:
        self.frame_hw = frame_hw
        c = self.cfg.calibration
        if c is None:
            return
        try:
            if c.homography:
                self.mapping = GroundMapping(np.asarray(c.homography), frame_hw=frame_hw)
                self.calib_info = {"source": "homography"}
                self.pipe.map_dirty = True
            elif c.image_points and c.map_points:
                self.mapping = GroundMapping.from_points(c.image_points, c.map_points, frame_hw=frame_hw)
                self.calib_info = {"source": "points", "points": len(c.image_points)}
                self.pipe.map_dirty = True
            elif c.camera:
                self.local = GroundMapping.from_camera(CameraModel.from_dict(c.camera), frame_hw=frame_hw)
                self.calib_info = {"source": "config", "camera": c.camera}
                self._place()
            elif c.auto is not None:
                focal = c.auto.get("focal_px")
                if focal is None and c.auto.get("hfov_deg"):
                    focal = frame_hw[1] / 2 / math.tan(math.radians(float(c.auto["hfov_deg"])) / 2)
                self.collector = CalibrationCollector(frame_hw, min_obs=int(c.auto.get("min_obs", 60)),
                                                      min_tracks=int(c.auto.get("min_tracks", 2)),
                                                      every_s=float(c.auto.get("every_s", 0.4)),
                                                      focal_px=float(focal) if focal else None)
                self.calib_info = {"source": "auto", "state": "collecting"}
        except Exception as e:  # noqa: BLE001
            self.calib_info = {"error": repr(e)}

    def _place(self) -> None:
        """Ставит локальную систему камеры на карту: явное размещение или совмещение с другой камерой."""
        c = self.cfg.calibration
        if self.local is None:
            return
        if c.align_to and c.align_to != self.id:
            M = self.pipe.alignments.get(self.id)
            ref = self.pipe.cams.get(c.align_to)
            if M is None or ref is None or ref.local is None:
                return  # ждём совмещения
            P = self.pipe.placement_of(ref.cfg) @ M
        else:
            P = self.pipe.placement_of(self.cfg)
        self.mapping = GroundMapping(P @ self.local.H, camera=self.local.camera, frame_hw=self.frame_hw)
        self.pipe.map_dirty = True
        for other in self.pipe.cams.values():  # камеры, совмещённые с этой, тоже переставляем
            if other is not self and other.cfg.calibration and other.cfg.calibration.align_to == self.id:
                other._place()

    def camera_xy(self) -> np.ndarray | None:
        """Положение камеры на карте (для авто-калибровки — точка пола под камерой)."""
        if self.mapping is None or self.local is None:
            return None
        P = self.mapping.H @ np.linalg.inv(self.local.H)
        p = P @ np.array([0, 0, 1.0])
        return p[:2] / p[2]

    def maybe_finish_calibration(self) -> None:
        if self.collector is None or not self.collector.ready():
            return
        res = self.collector.fit(float(self.cfg.calibration.auto.get("person_height_m", 1.7)))
        self.calib_info = {"source": "auto", **res.to_dict(), "state": "ok" if res.ok else "retry"}
        if not res.ok:
            self.collector.min_obs += 40
            return
        self.collector = None
        self.local = GroundMapping.from_camera(res.camera, frame_hw=self.frame_hw)
        self.pipe.log(f"[{self.id}] авто-калибровка: f={res.camera.f:.0f}px, наклон "
                      f"{math.degrees(res.camera.tilt):.1f}°, высота {res.camera.height:.2f} м, "
                      f"ошибка роста {res.rms_rel * 100:.1f}%")
        self._place()


class Pipeline:
    def __init__(self, site: SiteConfig, models: ModelSet | None = None, log: Callable[[str], None] = print):
        self.site = site
        self.log = log
        self.models = models or ModelSet(site)
        self.params = {r.code: site.params(r.code) for r in RULES}
        self.evaluator = RuleEvaluator(self.params)
        self.zones = ZoneIndex(site.zones)
        self.cams: dict[str, CameraRuntime] = {c.id: CameraRuntime(c, self) for c in site.cameras}
        self.fusion = GlobalTracker()
        self.alignments: dict[str, np.ndarray] = {}
        self.align_info: dict[str, Any] = {}
        out = site.resolve(site.events.output_dir)
        self.out_dir = out
        for d in ("snapshots", "clips", "review"):
            os.makedirs(os.path.join(out, d), exist_ok=True)
        ev = site.events
        self.recorder = ClipRecorder(os.path.join(out, "clips"), ev.pre_roll_s, ev.post_roll_s, ev.max_clip_s,
                                     ev.clip_width)
        self.store = EventStore()
        self.sinks: list[Callable[[str, dict], None]] = [self.store]
        if ev.jsonl:
            self.sinks.append(JsonlSink(os.path.join(out, "events.jsonl")))
        self.sinks += [WebhookSink(u) for u in ev.webhooks]
        self.agg = EventAggregator(lambda code: self.params[code], on_start=self._on_start, on_end=self._on_end,
                                   on_update=self._on_reopen)
        self.canvas = MapCanvas(site.map)
        self.mapbuilder = MapBuilder(self.canvas, self.site.map.max_range_m)
        self.map_dirty = False
        self.map_info: dict[str, Any] = {}
        self._frames: dict[str, np.ndarray] = {}
        self.lock = threading.RLock()
        self.running = False
        self.t_start = time.time()
        self.frames_total = 0
        self._last_align_try = -1e18

    # ------------------------------------------------------------- утилиты
    def placement_of(self, cam: CameraConfig) -> np.ndarray:
        p = (cam.calibration.placement if cam.calibration else None) or {}
        if not p:  # по умолчанию камера у верхнего края карты по центру и смотрит «вниз» по карте
            return rigid2d(0.0, self.site.map.origin_m[0] + self.site.map.size_m[0] / 2, self.site.map.origin_m[1])
        return rigid2d(math.radians(p.get("yaw_deg", 0.0)), p.get("x", 0.0), p.get("y", 0.0))

    def calibration_snapshot(self) -> dict[str, dict]:
        """Итог калибровки в виде блоков calibration для yaml: модель камеры + место на карте.

        Совмещённые камеры (align_to) получают явное placement, так что при следующем запуске
        карта готова с первого кадра."""
        out = {}
        for c in self.cams.values():
            if c.mapping is None or c.local is None or c.local.camera is None:
                continue
            P = c.mapping.H @ np.linalg.inv(c.local.H)
            P = P / P[2, 2]
            out[c.id] = {"camera": {k: round(float(v), 4) for k, v in c.local.camera.to_dict().items()},
                         "placement": {"x": round(float(P[0, 2]), 3), "y": round(float(P[1, 2]), 3),
                                       "yaw_deg": round(math.degrees(math.atan2(P[1, 0], P[0, 0])), 2)}}
        return out

    def emit(self, kind: str, ev: Event) -> None:
        d = ev.to_dict()
        for s in self.sinks:
            try:
                s(kind, d)
            except Exception as e:  # noqa: BLE001
                self.log(f"[sink] {e!r}")
        if kind == "started":
            self.log(f"⚠ ТРЕВОГА [{d['camera_id']}] {d['title']} — субъект {d['subject']}, "
                     f"с {d['start_time']} (зоны: {', '.join(d['zone_names']) or '—'})")
        elif kind == "ended":
            self.log(f"✓ завершено [{d['camera_id']}] {d['title']} — {d['duration_s']} c, клип: {d['clip']}")

    def _rel(self, path: str | None) -> str | None:
        return None if path is None else os.path.relpath(path, self.out_dir)

    # ------------------------------------------------------------- события
    def _on_start(self, ev: Event, o: TaggedObservation) -> None:
        frame = self._frames.get(o.camera_id)
        label = RULE_BY_CODE[ev.rule].title
        if frame is not None:
            p = os.path.join(self.out_dir, "snapshots", f"{ev.id}.jpg")
            self.recorder.snapshot(o.camera_id, frame, o.box, label, p)
            ev.snapshot = self._rel(p)
        self.recorder.start(o.camera_id, ev.id, set(ev.track_ids), label, ev.start_ts, done_cb=self._clip_done)
        self.emit("started", ev)

    def _on_reopen(self, ev: Event) -> None:
        self.recorder.start(ev.camera_id, ev.id, set(ev.track_ids), RULE_BY_CODE[ev.rule].title, ev.last_ts,
                            done_cb=self._clip_done, suffix=f"_{ev.reopen_count}")
        self.emit("reopened", ev)

    def _on_end(self, ev: Event) -> None:
        self.recorder.stop(ev.id, ev.end_ts)

    def _clip_done(self, event_id: str, path: str | None) -> None:
        ev = self.agg.events.get(event_id)
        if ev is None:
            return
        if path:
            ev.clips.append(self._rel(path))
        self.emit("ended" if ev.status == "ended" else "updated", ev)

    # ------------------------------------------------------------- правила
    def possible_rules(self, cam: CameraRuntime) -> set[str]:
        """Все правила, которые могут действовать хоть где-то в кадре камеры (для выбора нейросетей)."""
        eff = self.site.effective_rules(cam.id, [])
        on = {k for k, v in eff.items() if v}
        for z in self.site.zones:
            if z.camera in (None, cam.id):
                on |= {k for k, v in z.rules.items() if v}
                if z.kind in ("danger", "dynamic"):
                    on.add("danger_zone")
        return on

    def _rules_for(self, cam_id: str, zones: list[ZoneConfig]) -> set[str]:
        eff = self.site.effective_rules(cam_id, zones)
        return {k for k, v in eff.items() if v}

    # ------------------------------------------------------------- обработка кадра
    def process(self, cam: CameraRuntime, pkt: FramePacket) -> None:
        t0 = time.perf_counter()
        frame, ts = pkt.frame, pkt.ts
        if cam.frame_hw is None:
            cam.init_mapping(frame.shape[:2])
        self._frames[cam.id] = frame
        cam.n += 1
        possible = self.possible_rules(cam)
        mcfg = self.site.models

        # 3 (заранее). детекторы объектов от позы не зависят — на облаке LinQ их запрос идёт параллельно с позой,
        # и кадр ждёт две круговые задержки сети вместо трёх
        dyn_zones = any(z.kind == "dynamic" for z in self.site.zones)
        obj_jobs = []
        if possible & OBJECT_RULES or dyn_zones:
            obj_jobs = [_POOL.submit(m, frame) for name, m in self.models.by_role("objects")
                        if cam.n % mcfg[name].every_n == 0]

        # 1. люди + поза (каждый кадр)
        _, pose = self.models.by_role("pose")[0]
        pd = _person_dets(pose(frame))
        tracks = cam.tracker.update(pd.boxes, pd.scores, ts, kpts=pd.kpts)
        cam.persons = tracks

        # 2. СИЗ — только если хоть одно правило СИЗ может действовать на этой камере
        ppe_dets = None
        if possible & PPE_RULES and tracks:
            for name, m in self.models.by_role("ppe"):
                if cam.n % mcfg[name].every_n == 0:
                    crop = _crop_for_people(frame.shape[:2], np.array([t.box for t in tracks]), m.in_hw)
                    if crop is None:
                        ppe_dets = m(frame)
                    else:
                        x1, y1, x2, y2 = crop
                        ppe_dets = m(frame[y1:y2, x1:x2])
                        ppe_dets.boxes[:, [0, 2]] += x1
                        ppe_dets.boxes[:, [1, 3]] += y1

        # 3. объекты: телефон, сигарета, огонь, техника
        objs = ObjectSet.from_detections([j.result() for j in obj_jobs]) if obj_jobs else None

        # 4. техника — отдельный трекер (нужна её скорость)
        if objs is not None:
            vb, vs = objs.of(*VEHICLE_KINDS)
            vk = [k for k in objs.kinds if k in VEHICLE_KINDS]
            vb, vs, vk = _dedup_vehicles(vb, vs, vk)
            vtr = cam.vtracker.update(vb, vs, ts, classes=np.array([VEHICLE_KINDS.index(k) for k in vk], int))
        else:
            vtr = [t for t in cam.vtracker.tracks if t.state == "tracked"]
        vehicles = []
        for v in vtr:
            item = {"box": v.box, "kind": VEHICLE_KINDS[v.cls], "track_id": v.track_id, "map_seg": None,
                    "speed_mps": None}
            hist = np.array(list(v.history))
            if cam.mapping is not None:
                seg = np.array([[v.box[0], v.box[3]], [v.box[2], v.box[3]]])
                if cam.mapping.valid_image_points(seg).all():
                    item["map_seg"] = cam.mapping.to_map(seg)
                if len(hist) >= 4 and cam.mapping.valid_image_points(hist[:, 1:3]).all():
                    item["speed_mps"] = _speed(hist[:, 0], cam.mapping.to_map(hist[:, 1:3]))
            elif len(hist) >= 4:
                sp = _speed(hist[:, 0], hist[:, 1:3])
                if sp is not None:  # без калибровки: масштаб по высоте рамки техники (~2 м)
                    item["speed_mps"] = sp / max(float(np.median(hist[:, 3])), 1) * 2.0
            vehicles.append(item)
        cam.vehicles = vehicles

        # 5. карта: положение людей в метрах, скорость, поза
        person_map: dict[int, np.ndarray | None] = {}
        speeds: dict[int, float | None] = {}
        postures: dict[int, str] = {}
        for t in tracks:
            foot = np.array([t.foot])
            xy = None
            if cam.mapping is not None and cam.mapping.valid_image_points(foot)[0]:
                xy = cam.mapping.to_map(foot)[0]
            person_map[t.track_id] = xy
            hist = np.array(list(t.history))
            if cam.mapping is not None and len(hist) >= 4:
                ok = cam.mapping.valid_image_points(hist[:, 1:3])
                speeds[t.track_id] = _speed(hist[ok, 0], cam.mapping.to_map(hist[ok, 1:3])) if ok.sum() >= 4 else None
            elif len(hist) >= 4 and cam.frame_hw:
                # камера ещё не откалибрована: оценка по росту в пикселях (угол обзора — из паспорта или 60°)
                auto = (cam.cfg.calibration.auto if cam.cfg.calibration else None) or {}
                speeds[t.track_id] = _speed_pinhole(hist, cam.frame_hw, float(auto.get("hfov_deg", 60.0)),
                                                    float(auto.get("person_height_m", 1.7)))
            postures[t.track_id] = self.evaluator.posture(t, frame.shape[:2])
            if cam.collector is not None:
                cam.collector.add(ts, t.track_id, t.box, t.kpts)
        if cam.local is not None:
            loc = [cam.local.to_map(np.array([t.foot]))[0] for t in tracks
                   if postures[t.track_id] == "upright" and cam.local.valid_image_points(np.array([t.foot]))[0]]
            cam.sync.add(ts, np.array(loc).reshape(-1, 2))
        cam.person_map = person_map
        cam.maybe_finish_calibration()
        self._maybe_align(ts)

        # 6. глобальные ID по всем камерам
        prev = cam.subjects
        cam.subjects = self.fusion.update(cam.id, ts, [(t.track_id, person_map[t.track_id]) for t in tracks])
        changed = [(prev[tid], k) for tid, k in cam.subjects.items() if tid in prev and prev[tid] != k]
        if changed:
            with self.lock:
                for old, new in changed:
                    self.agg.rename(old, new)

        # 7. зоны и действующие правила для каждого человека
        anchors = [DynamicAnchor(v["kind"], None if v["map_seg"] is None else v["map_seg"].mean(0),
                                 np.array([(v["box"][0] + v["box"][2]) / 2, v["box"][3]]),
                                 max(float(v["box"][3] - v["box"][1]), 1) / 2.0, np.asarray(v["box"], float))
                   for v in vehicles]
        pzones, operators = [], set()
        for t in tracks:
            # водитель в кабине: зоны проезда и радиус техники — для пешеходов, а его скорость — скорость машины.
            # Признак держится 2 с: рамку техники детектор теряет на отдельных кадрах
            if _is_operator(t.box, vehicles):
                t.extra["operator_until"] = ts + 2.0
            if ts < t.extra.get("operator_until", -1.0):
                pzones.append([])
                operators.add(t.track_id)
                continue
            # без калибровки метры считаем по росту самого человека (~1.7 м), если он виден целиком
            scale = (t.box[3] - t.box[1]) / 1.7 if postures[t.track_id] == "upright" else None
            pzones.append(self.zones.at(cam.id, np.array(t.foot), person_map[t.track_id], ts, anchors,
                                        person_px_per_m=scale))
        enabled = [self._rules_for(cam.id, z) - (OPERATOR_EXEMPT if t.track_id in operators else set())
                   for t, z in zip(tracks, pzones)]

        # 8. правила
        obs: list[Observation] = []
        if ppe_dets is not None:
            verifier = None
            cls = self.models.by_role("helmet_cls")
            if cls:
                clf = cls[0][1]
                i_no = clf.names.index("no_helmet") if "no_helmet" in clf.names else 1

                def verifier(box, inside=False, _f=frame, _c=clf, _i=i_no):
                    h, w = _f.shape[:2]
                    if inside and (box[0] < 0 or box[1] < 0 or box[2] > w or box[3] > h):
                        return None
                    crop = head_crop(_f, box, _c.size)
                    return None if crop is None else float(_c([crop])[0, _i])
            colors = self.site.params("vest").get("vest_colors")
            vest_color = (lambda box, _f=frame, _c=colors: _color_fraction(_f, box, _c)) if colors else None
            obs += self.evaluator.ppe(tracks, ppe_dets, enabled, ts, helmet_verifier=verifier, vest_color=vest_color)
        if objs is not None:
            obs += self.evaluator.handheld(tracks, objs, enabled)

            def enabled_at(pt):
                pt = np.asarray(pt, np.float64)
                xy = None
                if cam.mapping is not None and cam.mapping.valid_image_points(pt[None])[0]:
                    xy = cam.mapping.to_map(pt[None])[0]
                return self._rules_for(cam.id, self.zones.at(cam.id, pt, xy, ts, anchors))
            obs += self.evaluator.fire(objs, frame.shape[:2], enabled_at)
            # на кадре рисуем только предметы, которые участвуют в правилах, а не все сырые рамки детекторов
            # (обновляются на кадрах, где работали детекторы объектов — без мигания через кадр)
            cam.marks = [(o.details["obj_box"], o.rule, o.conf) for o in obs
                         if o.value and o.rule in ("phone", "smoking") and "obj_box" in o.details]
            cam.marks += [(o.box, o.details.get("kind", "fire"), o.conf) for o in obs if o.rule == "fire" and o.value]
        obs += self.evaluator.motion(tracks, speeds, postures, enabled, cam.mapping is not None)
        obs += self.evaluator.zones(tracks, pzones, enabled)
        obs += self.evaluator.vehicles(tracks, [person_map[t.track_id] for t in tracks], vehicles, enabled)

        # 9. агрегация в события
        by_id = {t.track_id: (t, pzones[i]) for i, t in enumerate(tracks)}
        rec_boxes: dict[str, np.ndarray] = {}
        with self.lock:
            for o in obs:
                if o.subject.startswith("p"):
                    tid = int(o.subject[1:])
                    t, zs = by_id[tid]
                    subj = cam.subjects.get(tid, f"{cam.id}:p{tid}")
                    tobs = TaggedObservation(o.rule, subj, o.value, o.conf, ts, cam.id, t.box, person_map[tid],
                                             float(t.box[3] - t.box[1]), zs, o.details, pkt.capture_wall,
                                             track_start=t.t_start)
                else:
                    subj = f"{cam.id}:{o.subject}"
                    tobs = TaggedObservation(o.rule, subj, o.value, o.conf, ts, cam.id, o.box, None, 0.0, [],
                                             o.details, pkt.capture_wall)
                    rec_boxes[subj] = o.box
                self.agg.observe(tobs)
            self.agg.tick(ts)
        for t in tracks:
            rec_boxes[cam.subjects.get(t.track_id, f"{cam.id}:p{t.track_id}")] = t.box
        self.recorder.push(cam.id, ts, frame, rec_boxes)

        # 10. состояние для отрисовки и API
        cam.last_pkt = pkt
        cam.last_state = self._overlay_state(cam, tracks, vehicles, objs, ts)
        cam.proc_ms.append((time.perf_counter() - t0) * 1000)
        cam.e2e_ms.append((time.time() - pkt.capture_wall) * 1000)
        cam.ts_hist.append(time.time())
        self.frames_total += 1
        if self.map_dirty:
            self.rebuild_map()

    def _overlay_state(self, cam, tracks, vehicles, objs, ts) -> dict[str, Any]:
        status = self.subject_status()
        persons = []
        for t in tracks:
            key = cam.subjects.get(t.track_id, f"{cam.id}:p{t.track_id}")
            st, rules = status.get(key, ("ok", []))
            label = f"#{key.split(':')[-1].lstrip('pg')}"
            if rules:
                label += " " + ", ".join(SHORT_TITLES.get(r, RULE_BY_CODE[r].title) for r in rules)
            persons.append({"box": t.box, "kpts": t.kpts, "status": st, "label": label, "subject": key,
                            "map_xy": cam.person_map.get(t.track_id)})
        zones = []
        for z in self.site.zones:
            if not z.active_at(ts):
                continue
            if z.polygon_px and z.camera == cam.id:
                zones.append({"pts": z.polygon_px, "kind": z.kind, "name": z.name, "color": z.color})
            elif z.polygon and cam.mapping is not None and z.camera in (None, cam.id):
                pts = cam.mapping.to_image(np.asarray(z.polygon))
                if np.all(np.isfinite(pts)) and np.abs(pts).max() < 1e5:
                    zones.append({"pts": pts, "kind": z.kind, "name": z.name, "color": z.color})
        objects = []
        # очаг огня/дыма — одной сглаженной рамкой и только пока правило копит подтверждение или сработало:
        # граница облака дыма от кадра к кадру «прыгает», сырые рамки выглядят как шум
        fire = next(((b, k, s) for b, k, s in cam.marks if k in ("fire", "smoke")), None)
        if status.get(f"{cam.id}:fire", ("ok", []))[0] == "ok":
            cam.fire_disp = None
        elif fire is not None:
            prev = cam.fire_disp
            box = fire[0] if prev is None else 0.75 * prev[0] + 0.25 * np.asarray(fire[0], np.float32)
            cam.fire_disp = (np.asarray(box, np.float32), fire[1], fire[2])
        if cam.fire_disp is not None:
            b, kind, s = cam.fire_disp
            objects.append({"box": b, "kind": OBJECT_TITLES.get(kind, kind), "score": float(s)})
        for b, kind, s in cam.marks:
            if kind not in ("fire", "smoke"):
                objects.append({"box": b, "kind": OBJECT_TITLES.get(kind, kind), "score": float(s)})
        hdr = f"{cam.cfg.name or cam.id} | {time.strftime('%H:%M:%S', time.localtime(ts))} | {self.cam_fps(cam):.1f} FPS"
        return {"persons": persons, "zones": zones, "objects": objects, "header": hdr,
                "vehicles": [{"box": v["box"], "kind": v["kind"],
                              "speed": "" if v["speed_mps"] is None else f"{v['speed_mps']:.1f} м/с"} for v in vehicles]}

    def subject_status(self) -> dict[str, tuple[str, list[str]]]:
        out: dict[str, tuple[str, list[str]]] = {}
        with self.lock:
            for (rule, subj), st in self.agg.states.items():
                cur = out.get(subj, ("ok", []))
                if st.event is not None and st.event.status == "active":
                    out[subj] = ("violation", cur[1] + [rule])
                elif st.streak_start is not None and cur[0] == "ok":
                    out[subj] = ("pending", cur[1])
        return out

    # ------------------------------------------------------------- совмещение камер и карта
    def _maybe_align(self, ts: float) -> None:
        if ts - self._last_align_try < 5.0:
            return
        self._last_align_try = ts
        for cam in self.cams.values():
            c = cam.cfg.calibration
            if c is None or not c.align_to or cam.id in self.alignments or cam.local is None:
                continue
            ref = self.cams.get(c.align_to)
            if ref is None or ref.local is None:
                continue
            M, info = align_cameras(ref.sync, cam.sync)
            self.align_info[cam.id] = {"to": ref.id, **info}
            if M is not None and info["ok"]:
                self.alignments[cam.id] = M
                self.log(f"[{cam.id}] совмещена с {ref.id}: поворот {info['yaw_deg']}°, "
                         f"медианная ошибка {info['median_err_m']} м по {info['inliers']} точкам")
                cam._place()

    def rebuild_map(self) -> None:
        self.map_dirty = False
        mappings = {c.id: c.mapping for c in self.cams.values() if c.mapping is not None}
        if not mappings:
            return
        if self.site.map.auto_fit:
            fps = [c.mapping.footprint(c.frame_hw, self.site.map.max_range_m) for c in self.cams.values()
                   if c.mapping is not None and c.frame_hw]
            zones = [np.asarray(zp) for z in self.site.zones if (zp := self.zone_map_polygon(z))]
            cams = [xy.reshape(1, 2) for c in self.cams.values() if (xy := c.camera_xy()) is not None]
            cfg = MapCanvas.fit_to([f for f in fps if len(f)] + zones + cams, self.site.map.px_per_m)
            self.site.map.size_m, self.site.map.origin_m = cfg.size_m, cfg.origin_m
            self.canvas = MapCanvas(self.site.map)
            self.mapbuilder = MapBuilder(self.canvas, self.site.map.max_range_m)
        frames = {cid: f for cid, f in self._frames.items() if cid in mappings}
        self.mapbuilder.build(frames, mappings)
        room = np.asarray(self.site.map.room) if self.site.map.room else None
        blind = self.mapbuilder.blind_zones(room)
        self.map_info = {"coverage": round(self.mapbuilder.coverage_ratio(room), 3),
                         "blind_zones": [b.round(2).tolist() for b in blind],
                         "footprints": {k: v.round(2).tolist() for k, v in self.mapbuilder.footprints.items()}}
        if self.site.map.background:
            bg = cv2.imread(self.site.resolve(self.site.map.background))
            if bg is not None:
                self.mapbuilder.background = cv2.resize(bg, (self.canvas.W, self.canvas.H))

    def map_state(self) -> dict[str, Any]:
        """Люди, техника, зоны, камеры на карте в метрах — для отрисовки миникарты на фронтенде."""
        status = self.subject_status()
        t = max((c.last_pkt.ts for c in self.cams.values() if c.last_pkt), default=time.time())
        people = []
        for gid, xy, cams in self.fusion.positions(t):
            st, rules = status.get(f"g{gid}", ("ok", []))
            people.append({"id": f"g{gid}", "xy": [round(float(v), 2) for v in xy], "status": st, "rules": rules,
                           "cameras": cams, "label": f"#{gid}"})
        vehicles = []
        for c in self.cams.values():
            for v in c.vehicles:
                if v["map_seg"] is not None:
                    vehicles.append({"xy": [round(float(x), 2) for x in v["map_seg"].mean(0)], "kind": v["kind"],
                                     "camera": c.id, "speed_mps": v["speed_mps"]})
        cams = {}
        for c in self.cams.values():
            xy = c.camera_xy()
            cams[c.id] = {"xy": None if xy is None else [round(float(v), 2) for v in xy], "mapped": c.mapping is not None,
                          "footprint": self.map_info.get("footprints", {}).get(c.id)}
        return {"ts": t, "map": {"size_m": list(self.canvas.cfg.size_m), "origin_m": list(self.canvas.cfg.origin_m),
                                 "px_per_m": self.canvas.s, "room": self.site.map.room},
                "people": people, "vehicles": vehicles, "cameras": cams,
                "zones": [{"id": z.id, "name": z.name, "kind": z.kind, "polygon": self.zone_map_polygon(z),
                           "camera": z.camera, "polygon_px": z.polygon_px, "radius_m": z.radius_m,
                           "attach_to": z.attach_to, "active": z.active_at(t)} for z in self.site.zones],
                "blind_zones": self.map_info.get("blind_zones", []), "coverage": self.map_info.get("coverage")}

    def zone_map_polygon(self, z: ZoneConfig) -> list[list[float]] | None:
        """Зона на карте в метрах: заданная в метрах — как есть; заданная на кадре — проекция на пол,
        когда камера откалибрована (все вершины должны лежать на полу ниже горизонта)."""
        if z.polygon:
            return z.polygon
        cam = self.cams.get(z.camera) if z.polygon_px else None
        if cam is None or cam.mapping is None:
            return None
        pts = np.asarray(z.polygon_px, np.float64)
        if not cam.mapping.valid_image_points(pts).all():
            return None
        return cam.mapping.to_map(pts).round(2).tolist()

    def minimap(self, long_side: int = 900) -> np.ndarray:
        st = self.map_state()
        dyn = [z for z in self.site.zones if z.kind == "dynamic"]
        # мозаика из кадров — только для расчёта покрытия; на схеме подложкой идёт лишь план помещения
        plan = self.mapbuilder.background if self.site.map.background else None
        return draw_minimap(self.canvas, plan, {
            "zones": [{"polygon": zp, "kind": z.kind, "name": z.name, "color": z.color}
                      for z in self.site.zones if z.active_at(st["ts"]) and (zp := self.zone_map_polygon(z))],
            "footprints": self.mapbuilder.footprints,
            "room": np.asarray(self.site.map.room) if self.site.map.room else None,
            "camera_names": [c.id for c in self.site.cameras],
            "camera_titles": [c.name or c.id for c in self.site.cameras],
            "people": [{**p, "xy": np.asarray(p["xy"])} for p in st["people"]],
            "vehicles": [{"xy": np.asarray(v["xy"]), "kind": v["kind"], "radius_m": dyn[0].radius_m if dyn else None}
                         for v in st["vehicles"]],
            "cameras": {k: None if v["xy"] is None else np.asarray(v["xy"]) for k, v in st["cameras"].items()},
            "blind": [np.asarray(b) for b in st["blind_zones"]]}, long_side=long_side)

    def camera_view(self, cam_id: str) -> np.ndarray | None:
        cam = self.cams.get(cam_id)
        if cam is None or cam.last_pkt is None:
            return None
        return draw_camera(cam.last_pkt.frame, cam.last_state)

    # ------------------------------------------------------------- метрики
    def cam_fps(self, cam: CameraRuntime) -> float:
        if len(cam.ts_hist) < 2:
            return 0.0
        return (len(cam.ts_hist) - 1) / max(cam.ts_hist[-1] - cam.ts_hist[0], 1e-6)

    def perf(self) -> dict[str, Any]:
        cams = {}
        for c in self.cams.values():
            pm = np.asarray(c.proc_ms) if c.proc_ms else np.zeros(1)
            em = np.asarray(c.e2e_ms) if c.e2e_ms else np.zeros(1)
            cams[c.id] = {"fps": round(self.cam_fps(c), 2), "frames": c.n,
                          "proc_ms_mean": round(float(pm.mean()), 1),
                          "proc_ms_p95": round(float(np.percentile(pm, 95)), 1),
                          "latency_ms_mean": round(float(em.mean()), 1),
                          "persons": len(c.persons), "calibration": c.calib_info or None,
                          "mapped": c.mapping is not None}
        return {"backend": self.site.backend, "uptime_s": round(time.time() - self.t_start, 1),
                "frames_total": self.frames_total, "streams": len(cams),
                "total_fps": round(sum(v["fps"] for v in cams.values()), 2),
                "cameras": cams, "models": self.models.stats(), "alignment": self.align_info}

    # ------------------------------------------------------------- управление (API)
    def set_camera_rules(self, cam_id: str, rules: dict[str, int]) -> None:
        with self.lock:
            self.site.camera(cam_id).rules = rules

    def upsert_zone(self, z: dict[str, Any]) -> ZoneConfig:
        zone = parse_zone(z)
        with self.lock:
            self.site.zones = [x for x in self.site.zones if x.id != zone.id] + [zone]
            self.zones.set(self.site.zones)
        return zone

    def delete_zone(self, zone_id: str) -> bool:
        with self.lock:
            n = len(self.site.zones)
            self.site.zones = [x for x in self.site.zones if x.id != zone_id]
            self.zones.set(self.site.zones)
            return len(self.site.zones) < n

    def set_calibration(self, cam_id: str, image_points, map_points) -> dict[str, Any]:
        cam = self.cams[cam_id]
        gm = GroundMapping.from_points(image_points, map_points, frame_hw=cam.frame_hw)
        cam.cfg.calibration = Calibration(image_points=image_points, map_points=map_points)
        cam.mapping, cam.local, cam.collector = gm, None, None
        cam.calib_info = {"source": "manual", "points": len(image_points)}
        self.map_dirty = True
        return {"homography": gm.H.tolist()}

    def review(self, event_id: str, status: str, comment: str = "", user: str | None = None) -> dict[str, Any]:
        """Оператор подтверждает/отклоняет событие; материалы складываются в набор для дообучения."""
        ev = self.store.get(event_id)
        if ev is None:
            raise KeyError(event_id)
        rv = {"status": status, "comment": comment, "by": user, "at": round(time.time(), 3)}
        e = self.agg.events.get(event_id)
        if e is not None:
            e.review = rv
        ev = {**ev, "review": rv}
        for s in self.sinks:
            s("reviewed", ev)
        dst = os.path.join(self.out_dir, "review", status, ev["rule"])
        os.makedirs(dst, exist_ok=True)
        if ev.get("snapshot"):
            src = os.path.join(self.out_dir, ev["snapshot"])
            if os.path.exists(src):
                shutil.copy(src, os.path.join(dst, f"{event_id}.jpg"))
        with open(os.path.join(dst, f"{event_id}.json"), "w", encoding="utf-8") as f:
            json.dump(ev, f, ensure_ascii=False, indent=2)
        return ev

    # ------------------------------------------------------------- главный цикл
    def open_sources(self) -> None:
        t0 = time.time()
        for c in self.cams.values():
            src = c.cfg.source
            if isinstance(src, str) and "://" not in src and not src.isdigit():
                src = self.site.resolve(src)  # путь к файлу — относительно конфига
            c.source = open_source(src, c.cfg.process_fps, t0, loop=c.cfg.loop, realtime=c.cfg.realtime,
                                   offset_s=c.cfg.start_offset_s)

    def run(self, max_frames: int | None = None, duration_s: float | None = None,
            on_frame: Callable[["Pipeline", CameraRuntime], None] | None = None) -> None:
        if not any(c.source for c in self.cams.values()):
            self.open_sources()
        self.running = True
        t_end = None if duration_s is None else time.time() + duration_s
        try:
            while self.running:
                if max_frames is not None and self.frames_total >= max_frames:
                    break
                if t_end is not None and time.time() > t_end:
                    break
                files = [c for c in self.cams.values() if not c.source.live and not c.source.finished]
                lives = [c for c in self.cams.values() if c.source.live]
                did = False
                if files:  # записи — строго по времени кадра
                    cam = min(files, key=lambda c: c.source.next_ts())
                    pkt = cam.source.read()
                    if pkt is not None:
                        self.process(cam, pkt)
                        did = True
                        if on_frame:
                            on_frame(self, cam)
                for cam in lives:
                    pkt = cam.source.read()
                    if pkt is not None:
                        self.process(cam, pkt)
                        did = True
                        if on_frame:
                            on_frame(self, cam)
                if not files and not lives:
                    break
                if not did:
                    time.sleep(0.005)
        finally:
            self.running = False
            last = max((c.last_pkt.ts for c in self.cams.values() if c.last_pkt), default=time.time())
            with self.lock:
                self.agg.close_all(last)
            self.recorder.flush()
            for c in self.cams.values():
                if c.source:
                    c.source.close()

    def stop(self) -> None:
        self.running = False
