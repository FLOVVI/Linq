from safetyvision.catalog import RULE_BY_CODE
from safetyvision.events.aggregator import EventAggregator, TaggedObservation


def make():
    log = []
    agg = EventAggregator(lambda c: RULE_BY_CODE[c].defaults,
                          on_start=lambda e, o: log.append(("start", e.id)),
                          on_end=lambda e: log.append(("end", e.id)),
                          on_update=lambda e: log.append(("reopen", e.id)))
    return agg, log


def feed(agg, rule, subj, t0, t1, value=True, fps=8, xy=(1.0, 1.0)):
    t = t0
    while t <= t1:
        agg.observe(TaggedObservation(rule, subj, value, 0.8, t, "cam1", [0, 0, 10, 40], list(xy), 40.0))
        agg.tick(t)
        t += 1 / fps


def test_one_alert_per_incident():
    agg, log = make()
    feed(agg, "danger_zone", "g1", 0, 30)  # 30 секунд в опасной зоне = 240 кадров с нарушением
    feed(agg, "danger_zone", "g1", 30.1, 40, value=False)
    assert [k for k, _ in log] == ["start", "end"]
    ev = next(iter(agg.events.values()))
    assert ev.start_ts == 0 and 29.8 < ev.end_ts <= 30


def test_short_glitch_is_not_an_event():
    agg, log = make()
    feed(agg, "helmet", "g1", 0, 1.0)  # меньше confirm_s = 2 c
    feed(agg, "helmet", "g1", 1.1, 10, value=False)
    assert log == []


def test_reopen_within_merge_window_keeps_same_event():
    agg, log = make()
    feed(agg, "danger_zone", "g1", 0, 5)
    feed(agg, "danger_zone", "g1", 5.1, 9, value=False)  # вышел из зоны (событие закрылось)
    feed(agg, "danger_zone", "g1", 9.1, 15)  # вернулся через 4 с (< merge_s = 15)
    assert [k for k, _ in log] == ["start", "end", "reopen"]
    assert len(agg.events) == 1


def test_track_id_switch_is_relinked_by_position():
    agg, log = make()
    feed(agg, "helmet", "g1", 0, 6, xy=(5.0, 5.0))
    # трекер потерял человека и выдал новый ID рядом с тем же местом
    feed(agg, "helmet", "g7", 6.6, 12, xy=(5.3, 5.1))
    assert [k for k, _ in log].count("start") == 1
    assert len(agg.events) == 1


def test_different_people_get_different_events():
    agg, log = make()
    feed(agg, "helmet", "g1", 0, 6, xy=(1.0, 1.0))
    feed(agg, "helmet", "g2", 0, 6, xy=(9.0, 9.0))
    assert [k for k, _ in log].count("start") == 2


def test_sparse_hits_among_unknown_frames_are_not_an_event():
    # голова закрыта ношей: изредка «нет каски», в остальных кадрах «не видно» (None)
    agg, log = make()
    t = 0.0
    while t <= 6:
        k = round(t * 8)
        feed(agg, "helmet", "g1", t, t, value=True if k % 4 == 0 else None)
        t += 1 / 8
    assert log == []


def test_mostly_visible_violation_with_gaps_is_an_event():
    agg, log = make()
    t = 0.0
    while t <= 6:
        k = round(t * 8)
        feed(agg, "helmet", "g1", t, t, value=None if k % 4 == 0 else True)
        t += 1 / 8
    assert [k for k, _ in log] == ["start"]


def test_subject_rename_keeps_one_event():
    """Камера откалибровалась посреди нарушения: cam1:p1 стал g1 — событие то же, новой тревоги нет."""
    agg, log = make()
    feed(agg, "helmet", "cam1:p1", 0, 5)
    agg.rename("cam1:p1", "g1")
    feed(agg, "helmet", "g1", 5.1, 12)
    feed(agg, "helmet", "g1", 12.1, 25, value=False)
    assert [k for k, _ in log] == ["start", "end"]
    ev = next(iter(agg.events.values()))
    assert ev.subject == "g1" and ev.start_ts == 0 and ev.end_ts > 11


def test_rename_merges_two_active_events():
    """Две камеры подняли тревогу на одного человека до слияния глобальных ID: остаётся одно событие."""
    agg, log = make()
    feed(agg, "danger_zone", "g1", 0, 4)
    feed(agg, "danger_zone", "g2", 1, 4)
    agg.rename("g2", "g1")
    feed(agg, "danger_zone", "g1", 4.1, 8)
    ended = [e for e in agg.events.values() if e.status == "ended"]
    assert len(ended) == 1 and ended[0].details.get("merged_into")
    assert len(agg.active()) == 1 and agg.active()[0].start_ts == 0


def test_next_person_at_same_spot_is_a_new_event_while_first_still_visible():
    # первый вышел из зоны, но ещё в кадре; второй входит в зону в том же месте — это другой человек
    agg, log = make()
    feed(agg, "danger_zone", "cam1:p1", 0, 5, xy=(5.0, 5.0))
    for t in range(51, 200):
        ts = t / 10
        agg.observe(TaggedObservation("danger_zone", "cam1:p1", False, 0.8, ts, "cam1", [0, 0, 10, 40], [9.0, 9.0], 40.0))
        if ts >= 8:
            agg.observe(TaggedObservation("danger_zone", "cam1:p2", True, 0.8, ts, "cam1", [0, 0, 10, 40], [5.1, 5.0],
                                          40.0, track_start=7.0))
        agg.tick(ts)
    assert [k for k, _ in log].count("start") == 2
    assert len(agg.events) == 2


def test_next_person_after_first_left_is_a_new_event():
    # первый ушёл из кадра; второй появился через 6 с на том же месте — это не смена ID трека
    agg, log = make()
    feed(agg, "danger_zone", "cam1:p1", 0, 5, xy=(5.0, 5.0))
    t = 11.0
    while t <= 20:
        agg.observe(TaggedObservation("danger_zone", "cam1:p2", True, 0.8, t, "cam1", [0, 0, 10, 40], [5.1, 5.0],
                                      40.0, track_start=11.0))
        agg.tick(t)
        t += 1 / 8
    assert [k for k, _ in log].count("start") == 2
