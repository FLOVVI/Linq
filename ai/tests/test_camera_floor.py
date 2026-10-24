import math
from types import SimpleNamespace

import numpy as np

from safetyvision.config import ZoneConfig
from safetyvision.geometry.homography import CameraModel, GroundMapping, clip_below, rigid2d
from safetyvision.pipeline import Pipeline


def _pipe_with_camera(zones=()):
    model = CameraModel(f=800, tilt=math.radians(25), roll=0.0, height=4.0, cx=640, cy=360)
    local = GroundMapping.from_camera(model, frame_hw=(720, 1280))
    P = rigid2d(math.radians(70), 12.0, -3.0)   # камера стоит где-то на карте участка, повёрнута
    mapping = GroundMapping(P @ local.H, camera=model, frame_hw=(720, 1280))
    foot = np.array([[900.0, 600.0]])
    cam = SimpleNamespace(local=local, mapping=mapping, frame_hw=(720, 1280), calib_info={}, last_pkt=None, vehicles=[],
                          last_state={"persons": [{"map_xy": mapping.to_map(foot)[0], "status": "violation",
                                                   "label": "#3 Каска"}]})
    site = SimpleNamespace(map=SimpleNamespace(max_range_m=15.0), zones=list(zones))
    return SimpleNamespace(cams={"c1": cam}, site=site), local, foot


def test_people_come_back_in_camera_metres_regardless_of_placement():
    pipe, local, foot = _pipe_with_camera()
    out = Pipeline.camera_floor(pipe, "c1")
    assert out["mapped"] and out["range_m"] == 15.0
    np.testing.assert_allclose(out["people"][0]["xy"], local.to_map(foot)[0], atol=0.01)
    x, y = out["people"][0]["xy"]
    assert x > 0 and y > 0                                  # правее центра кадра и впереди камеры
    fp = np.asarray(out["footprint"])
    assert fp[:, 1].min() > 0 and fp[:, 1].max() <= 15.5    # обзор — впереди камеры, не дальше дальности


def test_zone_above_horizon_is_clipped_to_the_floor():
    z = ZoneConfig(id="c1:7", name="Пресс", kind="danger", camera="c1",
                   polygon_px=[[500, 0], [800, 0], [800, 700], [500, 700]])
    pipe, _, _ = _pipe_with_camera([z])
    zones = Pipeline.camera_floor(pipe, "c1")["zones"]
    assert len(zones) == 1 and zones[0]["id"] == "c1:7" and zones[0]["active"]
    poly = np.asarray(zones[0]["polygon"])
    assert poly[:, 1].min() > 0 and poly[:, 1].max() <= 15.5


def test_uncalibrated_camera_is_not_mapped():
    pipe, _, _ = _pipe_with_camera()
    pipe.cams["c1"].local = None
    assert Pipeline.camera_floor(pipe, "c1")["mapped"] is False


def test_clip_below_keeps_lower_part():
    sq = clip_below([[0, 0], [10, 0], [10, 10], [0, 10]], 4)
    assert len(sq) == 4 and sq[:, 1].min() == 4 and sq[:, 1].max() == 10
