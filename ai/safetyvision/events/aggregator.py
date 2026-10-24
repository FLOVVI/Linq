"""Агрегатор: покадровые наблюдения -> события «одно нарушение = одно оповещение».

Для каждой пары (правило, субъект) — конечный автомат:

    idle --(первое True)--> pending --(нарушение держится confirm_s с долей >= ratio)--> active
    active --(clear_s без True)--> ended          pending --(clear_s без True)--> idle

* Тревога уходит один раз, при переходе в active (с кадром-снимком).
* При завершении уходит одно сообщение ended (время конца + клип).
* Если тот же человек снова нарушает то же правило в течение merge_s после конца —
  событие переоткрывается (тот же id), новой тревоги нет.
* Если трекер потерял человека и выдал новый ID (перекрытие), новое наблюдение привязывается
  к недавнему событию того же правила — но только при настоящей смене ID: прежний человек пропал
  из вида, новый трек родился не позже relink_gap_s после этого и рядом с местом, где прежнего
  видели последний раз (на карте — в метрах, без калибровки — в пикселях относительно роста).
  Люди, которые по очереди проходят через одну зону, — разные события.
* Субъект с нескольких камер — это один глобальный ID (fusion), поэтому две камеры,
  видящие одного человека, тоже дают одно событие.
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from ..catalog import RULE_BY_CODE


@dataclass
class Event:
    id: str
    rule: str
    subject: str
    camera_id: str
    start_ts: float
    status: str = "active"  # active | ended
    end_ts: float | None = None
    last_ts: float = 0.0
    confidence: float = 0.0
    cameras: set[str] = field(default_factory=set)
    zone_ids: set[str] = field(default_factory=set)
    zone_names: set[str] = field(default_factory=set)
    box: list[float] | None = None
    map_xy: list[float] | None = None
    track_ids: set[str] = field(default_factory=set)
    details: dict[str, Any] = field(default_factory=dict)
    snapshot: str | None = None
    clips: list[str] = field(default_factory=list)
    reopen_count: int = 0
    review: dict[str, Any] = field(default_factory=lambda: {"status": "pending"})
    created_wall: float = field(default_factory=time.time)
    detect_latency_s: float | None = None  # от начала нарушения до тревоги (вкл. confirm_s)
    processing_latency_s: float | None = None  # от захвата кадра до отправки тревоги
    # где и когда субъекта события видели последний раз (любое наблюдение) — для склейки при смене ID
    seen_ts: float = -1e18
    seen_box: Any = None
    seen_map_xy: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Только простые типы Python: словарь уходит в JSON (журнал, вебхук, API, WebSocket)."""
        return _plain(self._dict())

    def _dict(self) -> dict[str, Any]:
        info = RULE_BY_CODE[self.rule]
        iso = lambda ts: None if ts is None else time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts)) + (  # noqa: E731
            f".{int((ts % 1) * 1000):03d}")
        end = self.end_ts if self.end_ts is not None else self.last_ts
        return {
            "id": self.id, "rule": self.rule, "rule_index": info.index, "title": info.title,
            "severity": info.severity, "status": self.status,
            "camera_id": self.camera_id, "cameras": sorted(self.cameras),
            "zone_ids": sorted(self.zone_ids), "zone_names": sorted(self.zone_names),
            "subject": self.subject, "track_ids": sorted(self.track_ids),
            "start_ts": round(self.start_ts, 3), "end_ts": None if self.end_ts is None else round(self.end_ts, 3),
            "start_time": iso(self.start_ts), "end_time": iso(self.end_ts),
            "duration_s": round(max(0.0, end - self.start_ts), 2),
            "confidence": round(self.confidence, 3), "bbox": self.box, "map_xy": self.map_xy,
            "snapshot": self.snapshot, "clip": self.clips[-1] if self.clips else None, "clips": list(self.clips),
            "reopen_count": self.reopen_count, "details": self.details, "review": self.review,
            "detect_latency_s": self.detect_latency_s, "processing_latency_s": self.processing_latency_s,
        }


def _plain(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if isinstance(x, np.ndarray):
        return _plain(x.tolist())
    if isinstance(x, np.generic):
        return x.item()
    return x


@dataclass
class _State:
    rule: str
    subject: str
    window: deque = field(default_factory=lambda: deque(maxlen=400))  # (t, value, conf)
    streak_start: float | None = None
    last_pos: float = -1e18
    last_seen: float = -1e18
    event: Event | None = None
    camera_id: str = ""
    box: Any = None
    map_xy: Any = None
    px_scale: float = 0.0  # рост человека в px (для сравнения расстояний без калибровки)
    born: float = 0.0  # когда появился трек субъекта
    last_event: Event | None = None  # последнее событие субъекта, в т.ч. завершённое


@dataclass
class TaggedObservation:
    """Наблюдение правила, дополненное контекстом камеры и пайплайна."""

    rule: str
    subject: str  # глобальный ключ субъекта (g<ID> или cam:p<ID>)
    value: bool | None
    conf: float
    ts: float
    camera_id: str
    box: Any = None
    map_xy: Any = None
    px_scale: float = 0.0
    zones: list = field(default_factory=list)
    details: dict = field(default_factory=dict)
    capture_wall: float | None = None
    track_start: float | None = None  # время появления трека (None — считать первым наблюдением)


class EventAggregator:
    def __init__(self, params_for: Callable[[str], dict[str, Any]],
                 on_start: Callable[[Event, TaggedObservation], None] | None = None,
                 on_end: Callable[[Event], None] | None = None,
                 on_update: Callable[[Event], None] | None = None,
                 relink_m: float = 1.5, relink_rel: float = 0.6, relink_gap_s: float = 3.0):
        self.params_for = params_for
        self.on_start, self.on_end, self.on_update = on_start, on_end, on_update
        self.states: dict[tuple[str, str], _State] = {}
        self.recent: deque[Event] = deque(maxlen=500)  # завершённые, для склейки (merge_s)
        self.events: dict[str, Event] = {}
        self.relink_m, self.relink_rel, self.relink_gap_s = relink_m, relink_rel, relink_gap_s

    # ---------------------------------------------------------------- приём наблюдений
    def observe(self, o: TaggedObservation) -> None:
        key = (o.rule, o.subject)
        st = self.states.get(key)
        if st is None:
            if o.value is not True:
                return  # пока нарушений нет — субъект не отслеживаем
            st = self.states[key] = _State(o.rule, o.subject)
            st.born = o.ts if o.track_start is None else o.track_start
        p = self.params_for(o.rule)
        st.last_seen = o.ts
        st.camera_id = o.camera_id
        st.box, st.map_xy, st.px_scale = o.box, o.map_xy, o.px_scale
        seen = st.event or st.last_event
        if seen is not None:
            seen.seen_ts, seen.seen_box, seen.seen_map_xy = o.ts, o.box, o.map_xy
        if o.value is None:
            st.window.append((o.ts, None, 0.0))  # «не видно» — для доли определённых кадров (min_coverage)
            return
        st.window.append((o.ts, bool(o.value), o.conf))
        if o.value:
            if st.streak_start is None or o.ts - st.last_pos > p["clear_s"]:
                st.streak_start = o.ts
            st.last_pos = o.ts

        ev = st.event
        if ev is not None and ev.status == "active":
            if o.value:
                ev.last_ts = o.ts
                ev.confidence = max(ev.confidence, o.conf)
                ev.cameras.add(o.camera_id)
                ev.zone_ids.update(z.id for z in o.zones)
                ev.zone_names.update(z.name for z in o.zones)
                ev.map_xy = None if o.map_xy is None else [round(float(v), 2) for v in o.map_xy]
                ev.details.update({k: v for k, v in o.details.items() if k not in ("zone_ids", "zone_names")})
            return

        if not o.value or st.streak_start is None:
            return
        if o.ts - st.streak_start < p["confirm_s"]:
            return
        span = [(t, v, c) for t, v, c in st.window if t >= st.streak_start]
        win = [w for w in span if w[1] is not None]
        pos = sum(1 for _, v, _ in win if v)
        if pos < 2 or pos / len(win) < p["ratio"]:
            return
        # редкие срабатывания среди кадров «не видно» (голова закрыта ношей и т.п.) — не основание для тревоги
        if len(win) / len(span) < p.get("min_coverage", 0.0):
            return
        conf = float(np.mean([c for _, v, c in win if v]))
        self._activate(st, o, conf)

    def _activate(self, st: _State, o: TaggedObservation, conf: float) -> None:
        p = self.params_for(o.rule)
        prev = self._find_mergeable(o, p["merge_s"], st.born)
        if prev is not None:
            ev = prev
            ev.status, ev.end_ts = "active", None
            ev.reopen_count += 1
            ev.last_ts = o.ts
            ev.track_ids.add(o.subject)
            ev.seen_ts, ev.seen_box, ev.seen_map_xy = o.ts, o.box, o.map_xy
            st.event = st.last_event = ev
            for other in self.states.values():  # старое состояние больше не владеет событием
                if other is not st and other.event is ev:
                    other.event = None
            if self.on_update:
                self.on_update(ev)
            return
        ev = Event(id=uuid.uuid4().hex[:12], rule=o.rule, subject=o.subject, camera_id=o.camera_id,
                   start_ts=st.streak_start, last_ts=o.ts, confidence=conf)
        ev.cameras.add(o.camera_id)
        ev.track_ids.add(o.subject)
        ev.zone_ids.update(z.id for z in o.zones)
        ev.zone_names.update(z.name for z in o.zones)
        ev.box = None if o.box is None else [round(float(v), 1) for v in o.box]
        ev.map_xy = None if o.map_xy is None else [round(float(v), 2) for v in o.map_xy]
        ev.details = {k: v for k, v in o.details.items() if k not in ("zone_ids", "zone_names")}
        ev.detect_latency_s = round(o.ts - st.streak_start, 2)
        if o.capture_wall is not None:
            ev.processing_latency_s = round(time.time() - o.capture_wall, 3)
        ev.seen_ts, ev.seen_box, ev.seen_map_xy = o.ts, o.box, o.map_xy
        st.event = st.last_event = ev
        self.events[ev.id] = ev
        if self.on_start:
            self.on_start(ev, o)

    def _find_mergeable(self, o: TaggedObservation, merge_s: float, born: float) -> Event | None:
        """Недавнее событие того же правила: тот же субъект или смена ID трека (born — рождение нового трека)."""
        cands = [e for e in self.recent if e.rule == o.rule and e.status == "ended"
                 and o.ts - (e.end_ts or e.last_ts) <= merge_s]
        # активные события того же правила, чей субъект пропал (ID сменился во время события)
        for st in self.states.values():
            ev = st.event
            if ev is not None and ev.rule == o.rule and ev.status == "active" and st.subject != o.subject \
                    and o.ts - st.last_seen > 0.5:
                cands.append(ev)
        best, best_d = None, 1e9
        for e in cands:
            if o.subject in e.track_ids:
                return e
        for e in cands:
            # по месту — только смена ID: прежнего человека уже не видно, а новый трек появился сразу после
            # (а не был в кадре одновременно с ним и не пришёл позже — это другой человек)
            if o.ts - e.seen_ts <= 0.5 or not (e.seen_ts - 0.5 <= born <= e.seen_ts + self.relink_gap_s):
                continue
            d = self._distance(e, o)
            if d is not None and d < best_d:
                best, best_d = e, d
        return best

    def _distance(self, e: Event, o: TaggedObservation) -> float | None:
        """Расстояние от места, где субъекта события видели последний раз, до нового наблюдения."""
        if e.seen_map_xy is not None and o.map_xy is not None:
            d = float(np.linalg.norm(np.asarray(e.seen_map_xy) - np.asarray(o.map_xy)))
            return d if d <= self.relink_m else None
        if e.seen_box is not None and o.box is not None and o.camera_id in e.cameras and o.px_scale > 0:
            a, b = np.asarray(e.seen_box), np.asarray(o.box)
            ca = np.array([(a[0] + a[2]) / 2, a[3]])
            cb = np.array([(b[0] + b[2]) / 2, b[3]])
            d = float(np.linalg.norm(ca - cb)) / o.px_scale
            return d if d <= self.relink_rel else None
        if o.subject.startswith("fire") and e.subject == o.subject:
            return 0.0
        return None

    def rename(self, old: str, new: str) -> None:
        """Ключ субъекта сменился (камера откалибровалась и человек получил глобальный ID, два глобальных ID
        слились в один): переносим состояние, чтобы одно нарушение не распалось на два события."""
        for rule, subj in [k for k in self.states if k[1] == old]:
            st = self.states.pop((rule, old))
            st.subject = new
            cur = self.states.get((rule, new))
            if cur is not None:
                act = lambda x: x.event is not None and x.event.status == "active"  # noqa: E731
                keep, other = (st, cur) if act(st) and not act(cur) else (cur, st)
                if act(other):  # оба уже подняли тревогу (две камеры до слияния ID): ведём одно, второе закрываем
                    ev, ov = keep.event, other.event
                    if ov.start_ts < ev.start_ts:
                        ev.start_ts = ov.start_ts
                    ev.cameras |= ov.cameras
                    ev.track_ids |= ov.track_ids
                    ov.status, ov.end_ts = "ended", ov.last_ts
                    ov.details["merged_into"] = ev.id
                    if self.on_end:
                        self.on_end(ov)
                keep.window = deque(sorted(list(keep.window) + list(other.window), key=lambda w: w[0]),
                                    maxlen=keep.window.maxlen)
                starts = [x.streak_start for x in (keep, other) if x.streak_start is not None]
                keep.streak_start = min(starts) if starts else None
                keep.last_pos = max(keep.last_pos, other.last_pos)
                keep.last_seen = max(keep.last_seen, other.last_seen)
                st = keep
            self.states[(rule, new)] = st
            if st.event is not None:
                st.event.subject = new
                st.event.track_ids.add(new)

    # ---------------------------------------------------------------- таймауты
    def tick(self, now: float) -> None:
        """Закрывает события без подтверждений дольше clear_s и чистит устаревшие состояния."""
        drop = []
        for key, st in self.states.items():
            p = self.params_for(st.rule)
            ev = st.event
            if ev is not None and ev.status == "active" and now - st.last_pos > p["clear_s"]:
                ev.status = "ended"
                ev.end_ts = max(st.last_pos, ev.start_ts)
                ev.last_ts = ev.end_ts
                self.recent.append(ev)
                st.event = None
                st.last_event = ev
                if self.on_end:
                    self.on_end(ev)
            if st.event is None and now - st.last_pos > max(p["clear_s"], 1.0) and now - st.last_seen > 1.0:
                drop.append(key)
            elif st.event is None and now - st.last_pos > p["clear_s"]:
                st.streak_start = None
        for k in drop:
            del self.states[k]

    def close_all(self, now: float) -> None:
        for st in list(self.states.values()):
            ev = st.event
            if ev is not None and ev.status == "active":
                ev.status = "ended"
                ev.end_ts = max(st.last_pos, ev.start_ts)
                self.recent.append(ev)
                st.event = None
                if self.on_end:
                    self.on_end(ev)

    def active(self) -> list[Event]:
        return [st.event for st in self.states.values() if st.event is not None and st.event.status == "active"]
