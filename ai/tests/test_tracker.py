import numpy as np

from safetyvision.tracking.bytetrack import ByteTracker


def test_fall_keeps_track_id():
    """Стоял (высокая рамка, уверенно), упал: рамка широкая и низкая, детектор неуверен, кадр пропущен."""
    tr = ByteTracker()
    ids = set()
    t = 0.0
    for _ in range(16):  # 2 с стоит на месте
        out = tr.update(np.array([[100, 60, 140, 200]], float), np.array([0.85]), t)
        ids |= {o.track_id for o in out}
        t += 1 / 8
    tr.update(np.zeros((0, 4)), np.zeros(0), t)  # падение — детектор человека не нашёл
    t += 1 / 8
    lying = []
    for _ in range(16):
        out = tr.update(np.array([[60, 160, 185, 202]], float), np.array([0.42]), t)
        lying += [o.track_id for o in out]
        t += 1 / 8
    assert len(ids) == 1 and lying and set(lying) == ids


def test_far_detection_is_not_relinked():
    tr = ByteTracker()
    t = 0.0
    for _ in range(16):
        out = tr.update(np.array([[100, 60, 140, 200]], float), np.array([0.85]), t)
        t += 1 / 8
    first = out[0].track_id
    tr.update(np.zeros((0, 4)), np.zeros(0), t)
    t += 1 / 8
    for _ in range(4):  # другой человек в другом конце кадра
        out = tr.update(np.array([[500, 60, 540, 200]], float), np.array([0.9]), t)
        t += 1 / 8
    assert all(o.track_id != first for o in out)
