"""Автокалибровка камер по проходящим людям — без ручной разметки и шахматных досок.

1. Одна камера. Для стоящего человека известны пиксель стоп и пиксель макушки, а рост
   ~1.7 м. Подбираем фокус f, наклон, крен и высоту установки камеры так, чтобы «человек
   ростом 1.7 м, стоящий в точке пола под стопами» проецировался в наблюдаемую макушку.
   Люди на разных расстояниях от камеры однозначно задают все параметры, после чего пол
   кадра переводится в метры (GroundMapping.from_camera).
2. Несколько камер. У каждой своя система координат пола. Камеры, смотрящие на одно
   помещение, видят одних и тех же людей в одни и те же моменты времени, поэтому жёсткое
   преобразование (поворот + сдвиг) между системами ищется RANSAC-ом по одновременным
   положениям людей. Так из 2-3 камер собирается единая карта помещения.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from .homography import CameraModel, apply_h, rigid2d

# индексы ключевых точек COCO
NOSE, L_SH, R_SH, L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANK, R_ANK = 0, 5, 6, 11, 12, 13, 14, 15, 16


def upright_observation(box: np.ndarray, kpts: np.ndarray | None, frame_hw: tuple[int, int],
                        kp_thr: float = 0.5) -> tuple[float, float, float, float] | None:
    """(u_foot, v_foot, u_head, v_head) для человека, который стоит/идёт целиком в кадре, иначе None."""
    h, w = frame_hw
    x1, y1, x2, y2 = box
    bh, bw = y2 - y1, x2 - x1
    if bh < 0.08 * h or bh / max(bw, 1) < 1.6:  # слишком мелкий или не вертикальный
        return None
    if y1 < 3 or y2 > h - 4 or x1 < 3 or x2 > w - 4:  # обрезан краем кадра
        return None
    if kpts is None:
        return (x1 + x2) / 2, y2, (x1 + x2) / 2, y1
    v = kpts[:, 2]
    if v[[L_ANK, R_ANK]].max() < kp_thr or v[[L_SH, R_SH]].min() < kp_thr or v[[L_HIP, R_HIP]].min() < kp_thr:
        return None  # ноги перекрыты (стол, станок) — точка стоп недостоверна
    sh = kpts[[L_SH, R_SH], :2].mean(0)
    hp = kpts[[L_HIP, R_HIP], :2].mean(0)
    if abs(sh[0] - hp[0]) > 0.35 * abs(hp[1] - sh[1]) + 1:  # корпус наклонён (присел, наклонился)
        return None
    ank = kpts[[L_ANK, R_ANK]]
    ank = ank[ank[:, 2] >= kp_thr]
    foot_v = max(float(ank[:, 1].max()), y2 - 0.02 * bh)
    foot_u = float(ank[:, 0].mean())
    head_u = float(kpts[NOSE, 0]) if v[NOSE] >= kp_thr else float(sh[0])
    return foot_u, foot_v, head_u, float(y1)


def _residuals(params: np.ndarray, obs: np.ndarray, cx: float, cy: float, person_h: float) -> np.ndarray:
    f, tilt, roll, hgt = params
    cam = CameraModel(f, tilt, roll, hgt, cx, cy)
    Hgi = cam.ground_to_image()
    try:
        Hig = np.linalg.inv(Hgi)
    except np.linalg.LinAlgError:
        return np.full(2 * len(obs), 10.0)
    g = apply_h(Hig, obs[:, :2])
    head = cam.project(np.c_[g, np.full(len(g), person_h)])
    ph = np.maximum(obs[:, 1] - obs[:, 3], 1.0)
    # точки выше горизонта на пол не проецируются — штрафуем
    bad = obs[:, 1] <= cam.horizon_v() + 2
    rv = (head[:, 1] - obs[:, 3]) / ph
    ru = 0.3 * (head[:, 0] - obs[:, 2]) / ph
    rv[bad] = 3.0
    return np.r_[rv, ru]


@dataclass
class CalibrationResult:
    camera: CameraModel
    rms_rel: float  # ошибка роста в долях (0.05 = 5%)
    n_obs: int
    ok: bool
    note: str = ""

    def to_dict(self) -> dict:
        return {"camera": self.camera.to_dict(), "rms_rel": round(self.rms_rel, 4), "n_obs": self.n_obs,
                "ok": self.ok, "note": self.note}


def fit_camera(obs: np.ndarray, frame_hw: tuple[int, int], person_h: float = 1.7,
               focal_px: float | None = None, min_spread: float = 0.12) -> CalibrationResult:
    """obs: (N, 4) = u_foot, v_foot, u_head, v_head.

    focal_px — фокусное расстояние, если известно (паспорт камеры / угол обзора): тогда подбираются только
    наклон, крен и высота, и хватает людей, проходящих почти на одном расстоянии от камеры.
    """
    obs = np.asarray(obs, np.float64)
    h, w = frame_hw
    cx, cy = w / 2, h / 2
    if len(obs) < 12:
        return CalibrationResult(CameraModel(w, math.radians(20), 0, 4.0, cx, cy), 1.0, len(obs), False,
                                 "мало наблюдений")
    spread = np.ptp(obs[:, 1]) / h
    lo = np.array([0.3 * w, math.radians(-5), math.radians(-12), 1.0])
    hi = np.array([4.0 * w, math.radians(85), math.radians(12), 30.0])
    f_init = (0.7 * w, 1.1 * w, 1.8 * w)
    if focal_px:
        lo[0], hi[0], f_init = 0.98 * focal_px, 1.02 * focal_px, (focal_px,)
    best = None
    try:
        from scipy.optimize import least_squares

        for f0 in f_init:
            for t0 in (10, 25, 45, 65):
                for h0 in (3.0, 7.0):
                    x0 = np.array([f0, math.radians(t0), 0.0, h0])
                    r = least_squares(_residuals, x0, args=(obs, cx, cy, person_h), bounds=(lo, hi),
                                      loss="soft_l1", f_scale=0.05, max_nfev=400)
                    if best is None or r.cost < best[1]:
                        best = (r.x, r.cost)
        x = best[0]
    except ImportError:
        # без scipy: грубый перебор по сетке
        fs = np.array([focal_px]) if focal_px else np.linspace(0.4 * w, 3 * w, 14)
        ts = np.radians(np.linspace(0, 75, 16))
        hs = np.linspace(1.5, 15, 14)
        bestc, x = 1e18, None
        for f in fs:
            for t in ts:
                for hh in hs:
                    r = _residuals(np.array([f, t, 0, hh]), obs, cx, cy, person_h)
                    c = float(np.sum(np.minimum(r * r, 0.04)))
                    if c < bestc:
                        bestc, x = c, np.array([f, t, 0, hh])
    res = _residuals(x, obs, cx, cy, person_h)[: len(obs)]
    rms = float(np.sqrt(np.median(res ** 2)))
    cam = CameraModel(float(x[0]), float(x[1]), float(x[2]), float(x[3]), cx, cy)
    ok = bool(rms < 0.08 and spread > min_spread)
    note = "" if ok else ("люди стояли на одном расстоянии от камеры" if spread <= min_spread else "большая ошибка")
    return CalibrationResult(cam, rms, len(obs), ok, note)


class CalibrationCollector:
    """Копит наблюдения стоящих людей, пока их не хватит для подбора параметров камеры."""

    def __init__(self, frame_hw: tuple[int, int], min_obs: int = 60, min_tracks: int = 2, every_s: float = 0.4,
                 focal_px: float | None = None):
        self.frame_hw = frame_hw
        self.min_obs, self.min_tracks, self.every_s = min_obs, min_tracks, every_s
        self.focal_px = focal_px
        # разброс стоп по высоте кадра: без известного фокуса нужен больше, иначе f и наклон не разделить
        self.min_spread = 0.06 if focal_px else 0.15
        self.obs: list[tuple[float, float, float, float]] = []
        self._last: dict[int, float] = {}
        self.track_ids: set[int] = set()

    def add(self, t: float, track_id: int, box, kpts) -> None:
        if t - self._last.get(track_id, -1e9) < self.every_s:
            return
        o = upright_observation(np.asarray(box), kpts, self.frame_hw)
        if o is not None:
            self.obs.append(o)
            self._last[track_id] = t
            self.track_ids.add(track_id)

    def ready(self) -> bool:
        if len(self.obs) < self.min_obs or len(self.track_ids) < self.min_tracks:
            return False
        # по одному человеку наклон и высота камеры почти взаимозаменяемы: нужен вдвое больший разброс по глубине
        need = self.min_spread * (2.0 if len(self.track_ids) < 2 else 1.0)
        return np.ptp(np.asarray(self.obs)[:, 1]) / self.frame_hw[0] > need

    def fit(self, person_h: float = 1.7) -> CalibrationResult:
        return fit_camera(np.asarray(self.obs), self.frame_hw, person_h, self.focal_px, 0.8 * self.min_spread)


# ---------------------------------------------------------------- совмещение нескольких камер

@dataclass
class SyncedPositions:
    """Положения людей на полу в системе координат одной камеры, сгруппированные по времени."""

    bin_s: float = 0.25
    data: dict[int, list[np.ndarray]] = field(default_factory=lambda: defaultdict(list))

    def add(self, t: float, xy: np.ndarray) -> None:
        if len(xy):
            self.data[int(round(t / self.bin_s))].append(np.asarray(xy, np.float64).reshape(-1, 2))

    def get(self, b: int) -> np.ndarray | None:
        v = self.data.get(b)
        return None if not v else np.concatenate(v)


def _kabsch2d(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Жёсткое преобразование, переводящее b в a (оба (N,2))."""
    ca, cb = a.mean(0), b.mean(0)
    U, _, Vt = np.linalg.svd((b - cb).T @ (a - ca))
    R = (U @ Vt).T
    if np.linalg.det(R) < 0:
        Vt[-1] *= -1
        R = (U @ Vt).T
    t = ca - R @ cb
    M = np.eye(3)
    M[:2, :2], M[:2, 2] = R, t
    return M


def align_cameras(ref: SyncedPositions, other: SyncedPositions, iters: int = 3000, inlier_m: float = 0.8,
                  seed: int = 0) -> tuple[np.ndarray | None, dict]:
    """RANSAC по одновременным положениям людей: возвращает 3x3 (other -> ref) и статистику."""
    rng = np.random.default_rng(seed)
    common = sorted(set(ref.data) & set(other.data))
    if len(common) < 10:
        return None, {"ok": False, "note": "мало общих моментов времени", "common_bins": len(common)}
    A = {b: ref.get(b) for b in common}
    B = {b: other.get(b) for b in common}

    def score(M):
        pa, pb = [], []
        for b in common:
            tb = apply_h(M, B[b])
            d = np.linalg.norm(A[b][:, None] - tb[None], axis=2)
            j = d.argmin(0)
            ok = d[j, np.arange(len(tb))] < inlier_m
            pa.append(A[b][j[ok]])
            pb.append(B[b][ok])
        pa, pb = np.concatenate(pa), np.concatenate(pb)
        return len(pa), pa, pb

    best = (0, None)
    for _ in range(iters):
        b1, b2 = rng.choice(common, 2, replace=False)
        a1, a2 = A[b1][rng.integers(len(A[b1]))], A[b2][rng.integers(len(A[b2]))]
        q1, q2 = B[b1][rng.integers(len(B[b1]))], B[b2][rng.integers(len(B[b2]))]
        da, db = np.linalg.norm(a1 - a2), np.linalg.norm(q1 - q2)
        if da < 1.0 or abs(da - db) > 0.4:
            continue
        th = math.atan2(*(a2 - a1)[::-1]) - math.atan2(*(q2 - q1)[::-1])
        c, s = math.cos(th), math.sin(th)
        t = a1 - np.array([[c, -s], [s, c]]) @ q1
        M = rigid2d(th, *t)
        n, _, _ = score(M)
        if n > best[0]:
            best = (n, M)
    if best[1] is None:
        return None, {"ok": False, "note": "не найдено согласованных пар"}
    M = best[1]
    for _ in range(3):  # уточнение по всем инлайерам
        n, pa, pb = score(M)
        if n >= 3:
            M = _kabsch2d(pa, pb)
    n, pa, pb = score(M)
    err = float(np.median(np.linalg.norm(apply_h(M, pb) - pa, axis=1))) if n else 1e9
    total = sum(len(B[b]) for b in common)
    ok = bool(n >= 20 and n / max(total, 1) > 0.3)
    return M, {"ok": ok, "inliers": int(n), "total": int(total), "median_err_m": round(err, 3),
               "yaw_deg": round(math.degrees(math.atan2(M[1, 0], M[0, 0])), 2)}
