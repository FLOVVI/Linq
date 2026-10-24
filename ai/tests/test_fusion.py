import numpy as np

from safetyvision.fusion import GlobalTracker


def run(walk_a, walk_b, fps=8, noise=0.0, seed=0):
    """Две камеры видят по одному человеку; walk_* — функция t -> (x, y) в метрах."""
    rnd = np.random.default_rng(seed)
    g = GlobalTracker()
    ids = []
    for i in range(int(6 * fps)):
        t = i / fps
        a = g.update("cam1", t, [(1, np.add(walk_a(t), rnd.normal(0, noise, 2)))])
        b = g.update("cam2", t + 0.01, [(1, np.add(walk_b(t), rnd.normal(0, noise, 2)))])
        ids.append((a[1], b[1]))
    return ids


def test_same_person_two_cameras_one_id_despite_noise():
    # одна траектория, у второй камеры шум положения ~0.5 м (далеко от камеры)
    ids = run(lambda t: (1.2 * t, 3.0), lambda t: (1.2 * t + 0.3, 3.2), noise=0.5)
    assert ids[-1][0] == ids[-1][1]


def test_two_people_far_apart_stay_separate():
    ids = run(lambda t: (1.2 * t, 0.0), lambda t: (1.2 * t, 4.0), noise=0.1)
    assert all(a != b for a, b in ids)
