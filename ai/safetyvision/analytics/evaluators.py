"""Покадровая оценка правил ТБ.

Каждое правило по кадру выдаёт «наблюдения» (Observation) для субъекта — человека-трека или
объекта (огонь): True — нарушение видно, False — видно, что правило соблюдено, None — не
видно (перекрытие, слишком мелко, человек спиной). Решение «есть событие» принимает
агрегатор по окну времени, а не отдельный кадр — это и убирает ложные срабатывания.

СИЗ сопоставляются не с рамкой человека целиком, а с частью тела по ключевым точкам позы:
каска — с областью головы, жилет — с корпусом (плечи-бёдра), перчатки — с кистями.
Поэтому каска в руке или на соседе не засчитывается.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..geometry.boxes import intersection_over_b
from ..geometry.zones import distance_to_segment
from ..inference.yolo import Detections
from ..tracking.bytetrack import Track

NOSE, L_EYE, R_EYE, L_EAR, R_EAR = 0, 1, 2, 3, 4
L_SH, R_SH, L_EL, R_EL, L_WR, R_WR = 5, 6, 7, 8, 9, 10
L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANK, R_ANK = 11, 12, 13, 14, 15, 16
HEAD = [NOSE, L_EYE, R_EYE, L_EAR, R_EAR]

# имена классов разных детекторов -> единый тип объекта
CANON = {
    "cell phone": "phone", "phone": "phone", "mobile phone": "phone", "cellphone": "phone",
    "cigarette": "cigarette", "cigar": "cigarette", "smoking": "cigarette", "vape": "cigarette",
    "fire": "fire", "flame": "fire", "smoke": "smoke",
    "forklift": "forklift", "car": "vehicle", "truck": "vehicle", "bus": "vehicle", "motorcycle": "vehicle",
    "train": "vehicle", "tractor": "vehicle", "excavator": "vehicle", "loader": "vehicle",
}
VEHICLE_KINDS = ("vehicle", "forklift")
PERSON_HEIGHT_M = 1.7


@dataclass
class Observation:
    rule: str
    subject: str  # ключ субъекта в пределах камеры: "p<track_id>" или "fire"
    value: bool | None
    conf: float = 0.0
    box: np.ndarray | None = None  # рамка субъекта в кадре
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ObjectSet:
    """Объекты (не люди) кадра в едином словаре типов."""

    boxes: np.ndarray
    scores: np.ndarray
    kinds: list[str]

    @staticmethod
    def from_detections(dets: list[Detections]) -> "ObjectSet":
        b, s, k = [], [], []
        for d in dets:
            for i in range(len(d)):
                kind = CANON.get(d.names[int(d.classes[i])].lower())
                if kind:
                    b.append(d.boxes[i])
                    s.append(float(d.scores[i]))
                    k.append(kind)
        return ObjectSet(np.asarray(b, np.float32).reshape(-1, 4), np.asarray(s, np.float32), k)

    def of(self, *kinds: str) -> tuple[np.ndarray, np.ndarray]:
        m = np.array([k in kinds for k in self.kinds], bool)
        return self.boxes[m] if len(m) else self.boxes, self.scores[m] if len(m) else self.scores


def _vis(k: np.ndarray | None, idx, thr: float = 0.5) -> bool:
    return k is not None and bool(np.all(k[idx, 2] >= thr))


def _any_vis(k: np.ndarray | None, idx, thr: float = 0.5) -> list[int]:
    if k is None:
        return []
    return [i for i in idx if k[i, 2] >= thr]


def head_box(box: np.ndarray, k: np.ndarray | None) -> tuple[np.ndarray, float, bool]:
    """Область головы (с запасом под каску), её размер в px и надёжность оценки."""
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    vis = _any_vis(k, HEAD, 0.4)
    if len(vis) >= 2:
        pts = k[vis, :2]
        c = pts.mean(0)
        span = float(np.ptp(pts[:, 0])) if len(vis) > 1 else 0.0
        sw = float(np.linalg.norm(k[L_SH, :2] - k[R_SH, :2])) if _vis(k, [L_SH, R_SH], 0.4) else 0.0
        s = max(span * 1.3, sw * 0.55, 0.09 * bh, 6.0)
        hb = np.array([c[0] - 0.85 * s, c[1] - 1.35 * s, c[0] + 0.85 * s, c[1] + 0.7 * s], np.float32)
        return hb, s, True
    s = max(0.6 * bw * 0.5, 0.1 * bh)
    cx = (x1 + x2) / 2
    hb = np.array([cx - s, y1 - 0.2 * s, cx + s, y1 + 1.6 * s], np.float32)
    return hb, s, False


def pose_head_crop_box(k: np.ndarray, s: float) -> np.ndarray:
    """Плотная рамка головы по ключевым точкам — как рамка «head» детектора СИЗ (для классификатора)."""
    vis = _any_vis(k, HEAD, 0.4)
    c = k[vis, :2].mean(0)
    return np.array([c[0] - 0.6 * s, c[1] - 1.0 * s, c[0] + 0.6 * s, c[1] + 0.6 * s], np.float32)


def torso_box(box: np.ndarray, k: np.ndarray | None) -> tuple[np.ndarray | None, float]:
    if not _vis(k, [L_SH, R_SH, L_HIP, R_HIP], 0.45):
        return None, 0.0
    pts = k[[L_SH, R_SH, L_HIP, R_HIP], :2]
    lo, hi = pts.min(0), pts.max(0)
    w = max(hi[0] - lo[0], 0.25 * (hi[1] - lo[1]))
    tb = np.array([lo[0] - 0.25 * w, lo[1] - 0.1 * (hi[1] - lo[1]), hi[0] + 0.25 * w, hi[1] + 0.12 * (hi[1] - lo[1])],
                  np.float32)
    return tb, float(hi[1] - lo[1])


def hand_points(k: np.ndarray | None) -> list[np.ndarray]:
    out = []
    if k is None:
        return out
    for wr, el in ((L_WR, L_EL), (R_WR, R_EL)):
        if k[wr, 2] >= 0.45:
            p = k[wr, :2]
            if k[el, 2] >= 0.45:  # кисть чуть дальше запястья по направлению предплечья
                p = p + 0.25 * (k[wr, :2] - k[el, :2])
            out.append(p)
    return out


def _center(b: np.ndarray) -> np.ndarray:
    return np.array([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2])


def _assign_items(regions: list[np.ndarray | None], items: np.ndarray, min_cover: float) -> dict[int, list[int]]:
    """Каждый предмет (каска/жилет) отдаётся тому региону, который покрывает его больше всего."""
    out: dict[int, list[int]] = {}
    valid = [i for i, r in enumerate(regions) if r is not None]
    if not valid or len(items) == 0:
        return out
    cov = intersection_over_b(np.stack([regions[i] for i in valid]), items)  # (R, items)
    best = cov.argmax(0)
    for j, r in enumerate(best):
        if cov[r, j] >= min_cover:
            out.setdefault(valid[r], []).append(j)
    return out


class RuleEvaluator:
    """Оценивает все правила для людей и объектов одного кадра одной камеры."""

    def __init__(self, params: dict[str, dict[str, Any]]):
        self.p = params

    # ---------------------------------------------------------------- СИЗ
    def ppe(self, persons: list[Track], ppe: Detections, enabled: list[set[str]], now: float = 0.0,
            helmet_verifier=None, vest_color=None) -> list[Observation]:
        """СИЗ с «памятью» трека: если каску на этом человеке уверенно видели недавно (memory_s),
        её пропуск детектором на отдельных кадрах не считается нарушением."""
        obs: list[Observation] = []
        if not persons:
            return obs
        heads = [head_box(t.box, t.kpts) for t in persons]
        torsos = [torso_box(t.box, t.kpts) for t in persons]
        helm = ppe.of("helmet")
        head_det = ppe.of("head", "face")
        vest = ppe.of("safety-vest", "safety-suit")
        glove = ppe.of("gloves")
        hands = ppe.of("hands")
        glass = ppe.of("glasses", "face-guard")
        face = ppe.of("face")

        h_assign = _assign_items([h[0] for h in heads], helm.boxes, 0.35)
        head_det = head_det.select(head_det.scores >= self.p["helmet"].get("min_head_conf", 0.55))
        hd_assign = _assign_items([h[0] for h in heads], head_det.boxes, 0.5)
        v_assign = _assign_items([t[0] for t in torsos], vest.boxes, 0.35)
        g_assign = _assign_items([h[0] for h in heads], glass.boxes, 0.5)
        f_assign = _assign_items([h[0] for h in heads], face.boxes, 0.5)
        min_head = self.p["helmet"].get("min_head_px", 14)
        min_torso = self.p["vest"].get("min_torso_px", 24)

        # перекрытый другим человеком: каску/жилет соседа легко отдать не тому, поэтому такие кадры
        # засчитываются только для текущего кадра, а в «память» СИЗ трека не пишутся
        boxes = np.array([t.box for t in persons], np.float32)
        area = np.maximum((boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1]), 1.0)
        iw = np.clip(np.minimum(boxes[:, None, 2], boxes[None, :, 2]) - np.maximum(boxes[:, None, 0], boxes[None, :, 0]), 0, None)
        ih = np.clip(np.minimum(boxes[:, None, 3], boxes[None, :, 3]) - np.maximum(boxes[:, None, 1], boxes[None, :, 1]), 0, None)
        overlap = iw * ih / area[:, None]
        np.fill_diagonal(overlap, 0.0)
        occluded = overlap.max(1) > self.p["vest"].get("occluded_overlap", 0.3) if len(persons) > 1 else np.zeros(1, bool)

        for i, t in enumerate(persons):
            en = enabled[i]
            subj = f"p{t.track_id}"
            hb, hs, reliable = heads[i]
            seen = t.extra.setdefault("ppe_seen", {})
            rec = seen if not occluded[i] else {}  # куда записывать «видели СИЗ»
            if "helmet" in en:
                if i in h_assign:
                    rec["helmet"] = now
                    obs.append(Observation("helmet", subj, False, float(helm.scores[h_assign[i]].max()), t.box))
                elif now - seen.get("helmet", -1e18) < self.p["helmet"].get("memory_s", 6.0):
                    obs.append(Observation("helmet", subj, False, 0.5, t.box, {"by": "memory"}))
                elif hs * 1.6 >= min_head and i in hd_assign:
                    # нарушение — только если детектор СИЗ сам нашёл голову/лицо без каски;
                    # одной позы мало (у человека спиной она «видит» нос — ложные тревоги)
                    j = hd_assign[i][int(np.argmax(head_det.scores[hd_assign[i]]))]
                    c = float(head_det.scores[j])
                    p_no = helmet_verifier(head_det.boxes[j]) if helmet_verifier is not None else None
                    if p_no is not None and p_no < self.p["helmet"].get("verify_no_helmet", 0.85):
                        # классификатор вырезки головы видит каску (тёмная/повёрнутая, детектор пропустил)
                        rec["helmet"] = now
                        obs.append(Observation("helmet", subj, False, 1 - p_no, t.box, {"by": "classifier"}))
                    else:
                        conf = c if p_no is None else min(c, p_no)
                        obs.append(Observation("helmet", subj, True, conf, t.box,
                                               {"head_px": round(hs * 1.6, 1),
                                                "p_no_helmet": None if p_no is None else round(p_no, 3)}))
                elif (reliable and helmet_verifier is not None
                      and hs >= self.p["helmet"].get("min_head_px_pose", 28)
                      and len(_any_vis(t.kpts, HEAD, 0.6)) >= 2):
                    # детектор СИЗ голову не нашёл (часто человек спиной): решает классификатор по вырезке
                    # головы из позы, с более строгим порогом — поза одна не даёт тревоги.
                    # Вырезка за краем кадра (голова обрезана, закрыта ношей) не проверяется — verifier вернёт None
                    p_no = helmet_verifier(pose_head_crop_box(t.kpts, hs), inside=True)
                    thr = self.p["helmet"].get("verify_no_helmet_pose", 0.97)
                    if p_no is not None and p_no >= thr:
                        obs.append(Observation("helmet", subj, True, 0.9 * p_no, t.box,
                                               {"head_px": round(hs, 1), "p_no_helmet": round(p_no, 3),
                                                "by": "pose+classifier"}))
                    elif p_no is not None and p_no < 0.2:
                        rec["helmet"] = now
                        obs.append(Observation("helmet", subj, False, 1 - p_no, t.box, {"by": "classifier"}))
                    else:
                        obs.append(Observation("helmet", subj, None, 0.0, t.box))
                else:
                    obs.append(Observation("helmet", subj, None, 0.0, t.box))
            if "vest" in en:
                tb, th = torsos[i]
                if i in v_assign:
                    # в память — только уверенный жилет по центру корпуса: край жилета соседа, выглядывающего
                    # из-за спины (его самого детектор ещё не нашёл), даёт слабую узкую рамку сбоку
                    vb, vs = vest.boxes[v_assign[i]], vest.scores[v_assign[i]]
                    vcx = (vb[:, 0] + vb[:, 2]) / 2
                    sure = vs >= self.p["vest"].get("memory_min_conf", 0.5)
                    if tb is not None:
                        sure &= np.abs(vcx - (tb[0] + tb[2]) / 2) <= 0.25 * (tb[2] - tb[0])
                    if sure.any():
                        rec["vest"] = now
                    obs.append(Observation("vest", subj, False, float(vest.scores[v_assign[i]].max()), t.box))
                elif now - seen.get("vest", -1e18) < self.p["vest"].get("memory_s", 6.0):
                    obs.append(Observation("vest", subj, False, 0.5, t.box, {"by": "memory"}))
                elif tb is not None and th >= min_torso:
                    # жилеты цвета, принятого на площадке (vest_colors), детектор может не знать (SH17 — жёлтые
                    # и оранжевые); доля такого цвета на корпусе засчитывается как жилет
                    # Цвет — слабый признак, поэтому исходов три: цвета жилета много — жилет есть; его почти нет —
                    # нарушение; промежуточная доля (расстёгнутый жилет, тень, человек за препятствием) — «не видно»,
                    # без тревоги
                    frac = vest_color(tb) if vest_color is not None else None
                    pv = self.p["vest"]
                    if frac is not None and frac >= pv.get("vest_color_min_frac", 0.35):
                        rec["vest"] = now
                        obs.append(Observation("vest", subj, False, 0.6, t.box, {"by": "color", "frac": round(frac, 2)}))
                    elif frac is not None and frac >= pv.get("vest_color_unsure_frac", 0.15):
                        obs.append(Observation("vest", subj, None, 0.0, t.box, {"by": "color", "frac": round(frac, 2)}))
                    else:
                        obs.append(Observation("vest", subj, True, 0.6, t.box, {"torso_px": round(th, 1)}))
                else:
                    obs.append(Observation("vest", subj, None, 0.0, t.box))
            if "gloves" in en:
                hp = hand_points(t.kpts)
                if hp:
                    r = max(0.6 * hs, 8.0)
                    near = lambda bx: [j for j in range(len(bx)) if min(  # noqa: E731
                        np.linalg.norm(_center(bx[j]) - p) for p in hp) < r + 0.5 * (bx[j][2] - bx[j][0])]
                    g = near(glove.boxes)
                    bare = near(hands.boxes)
                    if g:
                        rec["gloves"] = now
                        obs.append(Observation("gloves", subj, False, float(glove.scores[g].max()), t.box))
                    elif now - seen.get("gloves", -1e18) < self.p["gloves"].get("memory_s", 4.0):
                        obs.append(Observation("gloves", subj, False, 0.5, t.box, {"by": "memory"}))
                    elif bare:
                        obs.append(Observation("gloves", subj, True, float(hands.scores[bare].max()), t.box))
            if "goggles" in en:
                if i in g_assign:
                    rec["goggles"] = now
                    obs.append(Observation("goggles", subj, False, float(glass.scores[g_assign[i]].max()), t.box))
                elif now - seen.get("goggles", -1e18) < self.p["goggles"].get("memory_s", 4.0):
                    obs.append(Observation("goggles", subj, False, 0.5, t.box, {"by": "memory"}))
                elif i in f_assign and _vis(t.kpts, [L_EYE, R_EYE], 0.6) and hs >= 10:
                    obs.append(Observation("goggles", subj, True, float(face.scores[f_assign[i]].max()), t.box))
        return obs

    # ---------------------------------------------------------------- предметы в руках / у лица
    def handheld(self, persons: list[Track], objs: ObjectSet, enabled: list[set[str]]) -> list[Observation]:
        obs: list[Observation] = []
        phones, ps = objs.of("phone")
        cigs, cs = objs.of("cigarette")
        for i, t in enumerate(persons):
            en = enabled[i]
            k = t.kpts
            bh = float(t.box[3] - t.box[1])
            subj = f"p{t.track_id}"
            hands = hand_points(k)
            face = k[NOSE, :2] if k is not None and k[NOSE, 2] >= 0.4 else None
            anchors = hands + ([face] if face is not None else [])
            if "phone" in en:
                j = self._near(phones, anchors, 0.18 * bh, t.box)
                if j is not None:
                    obs.append(Observation("phone", subj, True, float(ps[j]), t.box,
                                           {"by": "detector", "obj_box": phones[j]}))
                elif self._hand_at_ear(k, bh):
                    obs.append(Observation("phone", subj, True, 0.35, t.box, {"by": "pose"}))
                elif hands:
                    obs.append(Observation("phone", subj, False, 0.3, t.box))
            if "smoking" in en:
                # сигарета ~9×1 см при ширине плеч ~40 см: крупная «сигарета» — бутылка, маркер, фонарик
                ps_ = self.p["smoking"]
                sw = 0.15 * bh
                if k is not None and min(k[L_SH, 2], k[R_SH, 2]) >= 0.4:
                    sw = max(sw, float(np.linalg.norm(k[L_SH, :2] - k[R_SH, :2])))
                side = np.sort(np.stack([cigs[:, 2] - cigs[:, 0], cigs[:, 3] - cigs[:, 1]], 1), 1)
                idx = np.flatnonzero((side[:, 1] <= ps_["cig_max_len"] * sw) & (side[:, 0] <= ps_["cig_max_width"] * sw))
                j = self._near(cigs[idx], anchors, 0.15 * bh, t.box)
                if j is not None:
                    j = idx[j]
                    obs.append(Observation("smoking", subj, True, float(cs[j]), t.box, {"obj_box": cigs[j]}))
                elif face is not None:
                    obs.append(Observation("smoking", subj, False, 0.3, t.box))
        return obs

    @staticmethod
    def _near(boxes: np.ndarray, anchors: list[np.ndarray], r: float, pbox: np.ndarray) -> int | None:
        if len(boxes) == 0 or not anchors:
            return None
        best, bj = 1e9, None
        for j, b in enumerate(boxes):
            c = _center(b)
            if not (pbox[0] - 0.15 * (pbox[2] - pbox[0]) <= c[0] <= pbox[2] + 0.15 * (pbox[2] - pbox[0])
                    and pbox[1] - 0.05 * (pbox[3] - pbox[1]) <= c[1] <= pbox[3]):
                continue
            d = min(float(np.linalg.norm(c - a)) for a in anchors)
            if d < r + 0.5 * max(b[2] - b[0], b[3] - b[1]) and d < best:
                best, bj = d, j
        return bj

    @staticmethod
    def _hand_at_ear(k: np.ndarray | None, bh: float) -> bool:
        """Кисть у уха при согнутом локте — характерная поза разговора по телефону."""
        if k is None:
            return False
        for wr, el, ear in ((L_WR, L_EL, L_EAR), (R_WR, R_EL, R_EAR)):
            if min(k[wr, 2], k[el, 2], k[ear, 2]) < 0.5:
                continue
            if np.linalg.norm(k[wr, :2] - k[ear, :2]) < 0.07 * bh and k[el, 1] > k[wr, 1]:
                return True
        return False

    # ---------------------------------------------------------------- движение и поза
    def motion(self, persons: list[Track], speeds: dict[int, float | None], postures: dict[int, str],
               enabled: list[set[str]], calibrated: bool) -> list[Observation]:
        obs: list[Observation] = []
        vmax = self.p["running"]["speed_mps"]
        for i, t in enumerate(persons):
            en = enabled[i]
            subj = f"p{t.track_id}"
            v = speeds.get(t.track_id)
            post = postures.get(t.track_id, "unknown")
            if "running" in en and v is not None and post == "upright":
                obs.append(Observation("running", subj, v > vmax, min(1.0, v / vmax / 1.5), t.box,
                                       {"speed_mps": round(v, 2), "calibrated": calibrated}))
            if "fall" in en and post != "unknown":
                lying = post == "lying"
                obs.append(Observation("fall", subj, lying, 0.7 if lying else 0.5, t.box,
                                       {"posture": post, "speed_mps": None if v is None else round(v, 2)}))
        return obs

    @staticmethod
    def posture(t: Track, frame_hw: tuple[int, int] | None = None) -> str:
        """upright / lying / unknown по наклону корпуса и пропорциям рамки."""
        k = t.kpts
        x1, y1, x2, y2 = t.box
        ar = (x2 - x1) / max(y2 - y1, 1)
        if frame_hw is not None and (y2 - y1) > 0.55 * frame_hw[0]:
            # крупный план (сварщик вплотную к камере): лежащий на полу человек не бывает выше половины кадра
            return "unknown"
        if _vis(k, [L_SH, R_SH, L_HIP, R_HIP], 0.4):
            sh = k[[L_SH, R_SH], :2].mean(0)
            hp = k[[L_HIP, R_HIP], :2].mean(0)
            d = hp - sh
            ang = math.degrees(math.atan2(abs(d[0]), abs(d[1]) + 1e-6))  # 0 = вертикально
            if ang > 60 and ar > 0.9:
                return "lying"
            if ang < 35:
                return "upright"
            return "unknown"
        if ar > 1.6:
            return "lying"
        if ar < 0.75:
            return "upright"
        return "unknown"

    # ---------------------------------------------------------------- зоны и техника
    def zones(self, persons: list[Track], person_zones: list[list], enabled: list[set[str]]) -> list[Observation]:
        obs = []
        for i, t in enumerate(persons):
            if "danger_zone" not in enabled[i]:
                continue
            dz = [z for z in person_zones[i] if z.kind in ("danger", "dynamic")]
            if dz:
                obs.append(Observation("danger_zone", f"p{t.track_id}", True, 0.9, t.box,
                                       {"zone_ids": [z.id for z in dz], "zone_names": [z.name for z in dz]}))
        return obs

    def vehicles(self, persons: list[Track], person_map: list[np.ndarray | None], vehicles: list[dict],
                 enabled: list[set[str]]) -> list[Observation]:
        """vehicles: [{box, kind, map_seg (2,2)|None, speed_mps|None, track_id}]"""
        obs = []
        pr = self.p["vehicle_proximity"]
        for i, t in enumerate(persons):
            if "vehicle_proximity" not in enabled[i] or not vehicles:
                continue
            best = None
            foot = np.array(t.foot)
            bh = float(t.box[3] - t.box[1])
            for v in vehicles:
                if intersection_over_b(np.asarray(v["box"])[None], t.box[None])[0, 0] > 0.6:
                    continue  # человек внутри рамки техники — это её водитель
                if pr["min_vehicle_speed_mps"] > 0 and (v.get("speed_mps") is None
                                                        or v["speed_mps"] < pr["min_vehicle_speed_mps"]):
                    continue  # стоящая техника (или скорость ещё не оценена) не опасна
                if person_map[i] is not None and v.get("map_seg") is not None:
                    d = distance_to_segment(person_map[i], v["map_seg"][0], v["map_seg"][1])
                else:  # без калибровки: масштаб по росту человека
                    b = v["box"]
                    d = distance_to_segment(foot, np.array([b[0], b[3]]), np.array([b[2], b[3]]))
                    d = d / max(bh, 1) * PERSON_HEIGHT_M
                if best is None or d < best[0]:
                    best = (d, v)
            if best is None:
                continue
            d, v = best
            obs.append(Observation("vehicle_proximity", f"p{t.track_id}", d < pr["distance_m"],
                                   float(np.clip(1 - d / (2 * pr["distance_m"]), 0, 1)), t.box,
                                   {"distance_m": round(d, 2), "vehicle": v["kind"],
                                    "vehicle_track": v.get("track_id"),
                                    "vehicle_speed_mps": None if v.get("speed_mps") is None else round(v["speed_mps"], 2)}))
        return obs

    # ---------------------------------------------------------------- огонь / дым
    def fire(self, objs: ObjectSet, frame_hw: tuple[int, int], enabled_at) -> list[Observation]:
        """enabled_at(point_px) -> set правил в точке. Один субъект на камеру: очаг из нескольких рамок
        (пламя + дым, языки пламени) — это один инцидент, а не тревога на каждую рамку или часть кадра."""
        b, s = objs.of("fire", "smoke")
        kinds = [k for k in objs.kinds if k in ("fire", "smoke")]
        h, w = frame_hw
        pf = self.p["fire"]
        keep = []
        for j in range(len(b)):
            if "fire" not in enabled_at(_center(b[j])):
                continue
            # дым — менее надёжный признак: учитываем только уверенный и крупный (задымление — это облако,
            # а маленькая «дымка» — почти всегда блик лампы или прожектора)
            if kinds[j] == "smoke" and (s[j] < pf.get("smoke_min_conf", 0.5) or
                                        (b[j][2] - b[j][0]) * (b[j][3] - b[j][1]) < pf.get("smoke_min_area", 0.01) * h * w):
                continue
            keep.append(j)
        if not keep:
            # явное «огня нет»: без отрицательных наблюдений доля кадров с огнём (ratio) всегда была бы 1,
            # и редкие ложные вспышки (искры сварки) складывались бы в тревогу
            return [Observation("fire", "fire", False, 0.0, np.array([0, 0, w, h], np.float32))]
        bb = b[keep]
        union = np.array([bb[:, 0].min(), bb[:, 1].min(), bb[:, 2].max(), bb[:, 3].max()], dtype=np.float32)
        top = max(keep, key=lambda j: s[j])
        return [Observation("fire", "fire", True, float(s[top]), union,
                            {"kind": "fire" if any(kinds[j] == "fire" for j in keep) else "smoke", "boxes": len(keep)})]
