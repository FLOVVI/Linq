import math

import numpy as np

from safetyvision.geometry.autocalib import SyncedPositions, align_cameras, fit_camera
from safetyvision.geometry.homography import CameraModel, GroundMapping, apply_h, rigid2d


def synth_obs(cam, n=120, seed=0, noise=1.5):
    rng = np.random.default_rng(seed)
    pts = np.c_[rng.uniform(-5, 5, n), rng.uniform(3, 18, n)]
    foot = cam.project(np.c_[pts, np.zeros(n)])
    head = cam.project(np.c_[pts, np.full(n, 1.7 + rng.normal(0, 0.06, n))])
    obs = np.c_[foot, head] + rng.normal(0, noise, (n, 4))
    keep = (foot[:, 0] > 0) & (foot[:, 0] < 1280) & (foot[:, 1] < 720) & (head[:, 1] > 0)
    return obs[keep], pts[keep]


def test_fit_camera_recovers_parameters():
    cam = CameraModel(f=950, tilt=math.radians(28), roll=math.radians(2), height=4.2, cx=640, cy=360)
    obs, pts = synth_obs(cam)
    r = fit_camera(obs, (720, 1280))
    assert r.ok, r
    assert abs(r.camera.height - 4.2) < 0.5
    assert abs(math.degrees(r.camera.tilt) - 28) < 3
    gm = GroundMapping.from_camera(r.camera)
    err = np.linalg.norm(gm.to_map(obs[:, :2]) - pts, axis=1)
    assert np.median(err) < 0.35, np.median(err)


def test_align_two_cameras():
    rng = np.random.default_rng(1)
    M_true = rigid2d(math.radians(70), 6.0, -2.0)  # cam B -> cam A
    Minv = np.linalg.inv(M_true)
    A, B = SyncedPositions(), SyncedPositions()
    people = rng.uniform(0, 10, (4, 2))
    vel = rng.normal(0, 0.8, (4, 2))
    for k in range(200):
        t = k * 0.25
        p = people + vel * t * 0.2 + rng.normal(0, 0.1, (4, 2))
        A.add(t, p[:3] + rng.normal(0, 0.1, (3, 2)))  # камера A видит троих
        B.add(t, apply_h(Minv, p[1:]) + rng.normal(0, 0.1, (3, 2)))  # B — других троих
    M, info = align_cameras(A, B)
    assert info["ok"], info
    assert abs(info["yaw_deg"] - 70) < 3
    assert np.abs(M[:2, 2] - [6, -2]).max() < 0.4
