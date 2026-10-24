import math
from types import SimpleNamespace

from safetyvision.site_bridge import Bridge, plan_pos


def _bridge_and_site(loops=0, duration=10.0):
    b = Bridge.__new__(Bridge)  # без сайта и моделей: нужны только счётчики повторов
    b.spots = {}
    src = SimpleNamespace(duration=duration, loop=True, loops=loops, t0=1000.0, offset=0.0)
    sp = SimpleNamespace(pipe=SimpleNamespace(cams={"c1": SimpleNamespace(source=src)}), sizes={"c1": (1000, 500)})
    return b, sp, src


def _ev(t, x=500, rule="helmet"):
    return {"camera_id": "c1", "rule": rule, "start_ts": t, "bbox": [x - 50, 100, x + 50, 400]}


def test_loop_repeat_is_skipped_but_missed_violation_is_sent():
    b, sp, src = _bridge_and_site()
    assert not b._is_repeat(sp, _ev(1004.0))            # 1-й проход: 4-я секунда ролика
    src.loops = 1
    assert b._is_repeat(sp, _ev(1014.5))                # 2-й проход, то же место ролика и кадра — повтор
    assert not b._is_repeat(sp, _ev(1014.5, x=100))     # другой человек в другой части кадра
    assert not b._is_repeat(sp, _ev(1018.0))            # пропущенное в 1-м проходе (8-я секунда) — новое
    assert not b._is_repeat(sp, _ev(1014.5, rule="vest"))
    src.loops = 2
    assert b._is_repeat(sp, _ev(1028.2))                # 3-й проход, 8-я секунда — уже отправляли


def test_first_pass_never_deduplicates():
    b, sp, _ = _bridge_and_site()
    assert not b._is_repeat(sp, _ev(1004.0))
    assert not b._is_repeat(sp, _ev(1004.5))            # два нарушения рядом в первом проходе — оба в журнал


def test_plan_pos_lies_in_camera_view_direction():
    cam = {"mapPos": {"x": 50, "y": 50}, "mapDirection": 90, "panAngle": 0}   # камера смотрит вправо
    far, near = plan_pos(cam, 50, 10), plan_pos(cam, 50, 95)
    assert far["x"] > near["x"] > 50 and math.isclose(far["y"], 50, abs_tol=0.5)
    assert plan_pos(cam, None, None) == {"x": 50, "y": 50}
