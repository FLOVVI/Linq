import cv2
import numpy as np

from safetyvision.analytics.evaluators import ObjectSet, RuleEvaluator
from safetyvision.catalog import RULES
from safetyvision.inference.yolo import Detections
from safetyvision.pipeline import _color_fraction
from safetyvision.tracking.bytetrack import Track

PARAMS = {r.code: dict(r.defaults) for r in RULES}


def hsv_patch(h, w, hsv):
    return cv2.cvtColor(np.full((h, w, 3), hsv, np.uint8), cv2.COLOR_HSV2BGR)


def test_open_vest_counts_by_both_sides():
    # расстёгнутый синий жилет в тени поверх чёрной куртки: синие только полы слева и справа
    img = hsv_patch(90, 60, (0, 0, 40))
    img[:, :18] = hsv_patch(90, 18, (110, 90, 85))
    img[:, -18:] = hsv_patch(90, 18, (110, 70, 60))
    assert _color_fraction(img, [0, 0, 60, 90], ["blue"]) >= 0.35
    # тёмная куртка без жилета и коричневая куртка при синих жилетах площадки — не жилет
    assert _color_fraction(hsv_patch(90, 60, (0, 0, 40)), [0, 0, 60, 90], ["blue"]) < 0.15
    assert _color_fraction(hsv_patch(90, 60, (12, 140, 48)), [0, 0, 60, 90], ["blue"]) < 0.15


def _person():
    k = np.zeros((17, 3), np.float32)
    k[:, 2] = 0.9
    k[5], k[6] = (60, 60, 0.9), (100, 60, 0.9)  # плечи
    k[11], k[12] = (65, 140, 0.9), (95, 140, 0.9)  # бёдра
    box = np.array([40, 20, 120, 240], np.float32)
    return Track(1, box, 0.9, 0, 0.0, 0.0, np.zeros(8), np.eye(8), kpts=k)


def _vest_value(frac):
    ev = RuleEvaluator(PARAMS)
    empty = Detections(np.zeros((0, 4), np.float32), np.zeros(0, np.float32), np.zeros(0, int), ["helmet"], None)
    obs = ev.ppe([_person()], empty, [{"vest"}], 0.0, vest_color=lambda box: frac)
    return [o.value for o in obs if o.rule == "vest"][0]


def test_vest_color_three_outcomes():
    assert _vest_value(0.6) is False  # жилет виден
    assert _vest_value(0.25) is None  # не уверен — без тревоги
    assert _vest_value(0.05) is True  # нарушение


def test_small_smoke_is_ignored():
    ev = RuleEvaluator(PARAMS)
    everywhere = lambda pt: {"fire"}  # noqa: E731
    lamp = ObjectSet(np.array([[1140, 160, 1190, 210]], np.float32), np.array([0.8], np.float32), ["smoke"])
    cloud = ObjectSet(np.array([[0, 0, 900, 550]], np.float32), np.array([0.7], np.float32), ["smoke"])
    assert ev.fire(lamp, (720, 1280), everywhere)[0].value is False
    o = ev.fire(cloud, (720, 1280), everywhere)[0]
    assert o.value is True and o.details["kind"] == "smoke"


def _person_at(tid, x0):
    t = _person()
    t.track_id = tid
    t.box = t.box + np.array([x0, 0, x0, 0], np.float32)
    t.kpts = t.kpts.copy()
    t.kpts[:, 0] += x0
    return t


def test_occluded_person_does_not_remember_neighbours_vest():
    # двое идут вплотную: жилет соседа попал в корпус второго — в «память» СИЗ это не пишется
    params = {k: dict(v) for k, v in PARAMS.items()}
    ev = RuleEvaluator(params)
    a, b = _person_at(1, 0), _person_at(2, 20)
    vest = Detections(np.array([[80, 70, 130, 150]], np.float32), np.array([0.8], np.float32),
                      np.array([0]), ["safety-vest"], None)
    obs = ev.ppe([a, b], vest, [{"vest"}, {"vest"}], 0.0, vest_color=lambda box: 0.0)
    assert any(o.rule == "vest" and o.value is False for o in obs)
    assert "vest" not in a.extra["ppe_seen"] and "vest" not in b.extra["ppe_seen"]
    # разошлись, жилета больше не видно: нарушение сразу, без «памяти» о чужом жилете
    b.box = b.box + np.array([300, 0, 300, 0], np.float32)
    b.kpts[:, 0] += 300
    empty = Detections(np.zeros((0, 4), np.float32), np.zeros(0, np.float32), np.zeros(0, int), ["safety-vest"], None)
    obs = ev.ppe([b], empty, [{"vest"}], 1.0, vest_color=lambda box: 0.0)
    assert [o.value for o in obs if o.rule == "vest"] == [True]


def test_bottle_is_not_a_cigarette():
    # плечи 40 px: сигарета 12×4 у рта — курение, рамка 30×60 (бутылка в руке) — нет
    p = _person()
    p.kpts[0] = (80, 40, 0.9)  # нос
    p.kpts[10] = (85, 50, 0.9)  # кисть
    ev = RuleEvaluator(PARAMS)

    def smoking(box):
        objs = ObjectSet(np.array([box], np.float32), np.array([0.7], np.float32), ["cigarette"])
        return [o.value for o in ev.handheld([p], objs, [{"smoking"}]) if o.rule == "smoking"][0]

    assert smoking([80, 45, 92, 49]) is True
    assert smoking([70, 30, 100, 90]) is False
    empty = ObjectSet(np.zeros((0, 4), np.float32), np.zeros(0, np.float32), [])
    assert [o.value for o in ev.handheld([p], empty, [{"smoking"}])] == [False]
