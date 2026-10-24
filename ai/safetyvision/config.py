"""Конфигурация площадки: камеры, карта, зоны, векторы правил.

Правила применяются слоями (каждый следующий перекрывает предыдущий):
    каталог (всё выключено) -> site.rules -> camera.rules -> зоны (по возрастанию priority)
Так «вектор ТБ», поданный вместе с видеопотоком камеры, задаёт правила для всего её кадра,
а зоны на карте уточняют правила локально (опасная зона у котла, курилка и т.п.).
"""

from __future__ import annotations

import copy
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .catalog import RULE_BY_CODE, RULES, parse_rules


@dataclass
class Calibration:
    image_points: list[list[float]] | None = None  # пиксели кадра
    map_points: list[list[float]] | None = None  # метры на карте
    homography: list[list[float]] | None = None  # готовая матрица image->map (метры)
    auto: dict[str, Any] | None = None  # авто-калибровка по людям: {person_height_m: 1.7, ...}
    camera: dict[str, Any] | None = None  # готовая модель камеры (результат авто-калибровки)
    placement: dict[str, float] | None = None  # где камера на карте: {x, y, yaw_deg}
    align_to: str | None = None  # авто-совмещение с другой камерой по общим людям


@dataclass
class CameraConfig:
    id: str
    source: Any
    name: str = ""
    process_fps: float = 8.0
    rules: dict[str, int] = field(default_factory=dict)
    calibration: Calibration | None = None
    loop: bool = False  # зацикливать видеофайл (демо)
    realtime: bool = False  # для файлов: имитировать реальное время
    start_offset_s: float = 0.0  # сдвиг видеофайла по времени (синхронизация записей разных камер)


@dataclass
class ZoneConfig:
    id: str
    name: str
    kind: str = "area"  # area | danger | dynamic
    polygon: list[list[float]] | None = None  # метры на карте
    camera: str | None = None  # если зона задана в пикселях конкретной камеры
    polygon_px: list[list[float]] | None = None
    attach_to: str | None = None  # dynamic: класс объекта (forklift / vehicle)
    radius_m: float = 3.0
    rules: dict[str, int] = field(default_factory=dict)
    priority: int = 0
    schedule: list[str] = field(default_factory=list)  # ["07:55-12:00", ...] — пусто = всегда
    color: str | None = None

    def active_at(self, ts: float) -> bool:
        if not self.schedule:
            return True
        t = dt.datetime.fromtimestamp(ts).time()
        for span in self.schedule:
            a, b = (dt.time.fromisoformat(s.strip()) for s in span.split("-"))
            if a <= b and a <= t <= b:
                return True
            if a > b and (t >= a or t <= b):  # интервал через полночь
                return True
        return False


@dataclass
class MapConfig:
    size_m: tuple[float, float] = (30.0, 20.0)
    px_per_m: float = 25.0
    origin_m: tuple[float, float] = (0.0, 0.0)  # координата левого верхнего угла карты
    background: str | None = None  # план помещения; None -> строится мозаикой с камер
    room: list[list[float]] | None = None  # контур помещения (метры) — для поиска слепых зон
    auto_fit: bool = False  # подогнать границы карты под зоны обзора камер
    max_range_m: float = 25.0  # дальность зоны обзора камеры на карте (дальше люди слишком мелкие)


@dataclass
class ModelConfig:
    spec: str  # путь к json-описанию модели (создаётся tools/export_onnx.py)
    every_n: int = 1  # запускать на каждом n-м обрабатываемом кадре
    conf: float = 0.35
    iou: float = 0.5
    role: str = "objects"  # pose | ppe | objects
    classes: list[str] | None = None  # оставить только эти классы (остальные не декодируются)
    class_conf: dict[str, float] = field(default_factory=dict)  # пороги для отдельных классов
    backend: str | None = None  # свой бэкенд модели (например, cpu), иначе общий models.backend


@dataclass
class EventsConfig:
    output_dir: str = "runs/events"
    pre_roll_s: float = 4.0
    post_roll_s: float = 2.0
    max_clip_s: float = 60.0
    clip_fps: float = 10.0
    clip_width: int = 960
    webhooks: list[str] = field(default_factory=list)
    jsonl: bool = True


@dataclass
class SiteConfig:
    id: str
    name: str
    map: MapConfig
    rules: dict[str, int]
    rule_params: dict[str, dict[str, Any]]
    cameras: list[CameraConfig]
    zones: list[ZoneConfig]
    models: dict[str, ModelConfig]
    backend: str = "onnx"  # onnx | tpu
    backend_options: dict[str, Any] = field(default_factory=dict)
    events: EventsConfig = field(default_factory=EventsConfig)
    base_dir: Path = Path(".")

    def params(self, code: str) -> dict[str, Any]:
        p = dict(RULE_BY_CODE[code].defaults)
        p.update(self.rule_params.get(code, {}))
        return p

    def camera(self, cam_id: str) -> CameraConfig:
        for c in self.cameras:
            if c.id == cam_id:
                return c
        raise KeyError(cam_id)

    def resolve(self, rel: str | None) -> str | None:
        if rel is None:
            return None
        p = Path(rel)
        return str(p if p.is_absolute() else (self.base_dir / p))

    def effective_rules(self, cam_id: str, zones: list[ZoneConfig]) -> dict[str, int]:
        """Итоговые правила для точки: site -> camera -> зоны по приоритету."""
        eff = {r.code: 0 for r in RULES}
        eff.update(self.rules)
        eff.update(self.camera(cam_id).rules)
        for z in sorted(zones, key=lambda z: z.priority):
            if z.kind == "danger" and "danger_zone" not in z.rules:
                eff["danger_zone"] = 1
            eff.update(z.rules)
        return eff

    def to_dict(self) -> dict[str, Any]:
        """Сериализация для API (веб-интерфейс команды)."""
        def cam(c: CameraConfig):
            d = {"id": c.id, "name": c.name, "source": str(c.source), "process_fps": c.process_fps,
                 "rules": c.rules}
            if c.calibration:
                d["calibration"] = {k: v for k, v in vars(c.calibration).items() if v is not None}
            return d

        return {
            "id": self.id, "name": self.name,
            "map": {"size_m": list(self.map.size_m), "px_per_m": self.map.px_per_m,
                    "origin_m": list(self.map.origin_m), "background": self.map.background,
                    "room": self.map.room},
            "rules": self.rules, "rule_params": self.rule_params,
            "cameras": [cam(c) for c in self.cameras],
            "zones": [{k: v for k, v in vars(z).items() if v not in (None, [], {})} for z in self.zones],
            "backend": self.backend,
        }


def _calibration(d: dict | None) -> Calibration | None:
    if not d:
        return None
    return Calibration(
        image_points=d.get("image_points"), map_points=d.get("map_points"),
        homography=d.get("homography"), auto=d.get("auto"), camera=d.get("camera"),
        placement=d.get("placement"), align_to=d.get("align_to"),
    )


def parse_zone(z: dict[str, Any]) -> ZoneConfig:
    return ZoneConfig(
        id=str(z["id"]), name=z.get("name", str(z["id"])), kind=z.get("kind", "area"),
        polygon=z.get("polygon"), camera=z.get("camera"), polygon_px=z.get("polygon_px"),
        attach_to=z.get("attach_to"), radius_m=float(z.get("radius_m", 3.0)),
        rules=parse_rules(z.get("rules")), priority=int(z.get("priority", 0)),
        schedule=list(z.get("schedule", [])), color=z.get("color"),
    )


def load_site(path: str | Path, overrides: dict[str, Any] | None = None) -> SiteConfig:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if overrides:
        raw = _deep_merge(raw, overrides)
    return parse_site(raw, base_dir=path.parent)


def parse_site(raw: dict[str, Any], base_dir: Path = Path(".")) -> SiteConfig:
    site = raw["site"]
    m = site.get("map", {})
    map_cfg = MapConfig(
        size_m=tuple(m.get("size_m", (30.0, 20.0))), px_per_m=float(m.get("px_per_m", 25.0)),
        origin_m=tuple(m.get("origin_m", (0.0, 0.0))), background=m.get("background"),
        room=m.get("room"), auto_fit=bool(m.get("auto_fit", False)), max_range_m=float(m.get("max_range_m", 25.0)),
    )
    cameras = [
        CameraConfig(
            id=str(c["id"]), source=c["source"], name=c.get("name", str(c["id"])),
            process_fps=float(c.get("process_fps", 8.0)), rules=parse_rules(c.get("rules")),
            calibration=_calibration(c.get("calibration")), loop=bool(c.get("loop", False)),
            realtime=bool(c.get("realtime", False)), start_offset_s=float(c.get("start_offset_s", 0.0)),
        )
        for c in raw.get("cameras", [])
    ]
    models = {
        name: ModelConfig(spec=v["spec"], every_n=int(v.get("every_n", 1)),
                          conf=float(v.get("conf", 0.35)), iou=float(v.get("iou", 0.5)),
                          role=v.get("role", name if name in ("pose", "ppe") else "objects"),
                          classes=v.get("classes"), class_conf=dict(v.get("class_conf", {})),
                          backend=v.get("backend"))
        for name, v in raw.get("models", {}).items() if name not in ("backend", "backend_options")
    }
    ev = raw.get("events", {})
    events = EventsConfig(**{k: v for k, v in ev.items() if k in EventsConfig.__dataclass_fields__})
    rule_params = site.get("rule_params", {}) or {}
    for code in rule_params:
        if code not in RULE_BY_CODE:
            raise ValueError(f"rule_params: неизвестное правило {code}")
    return SiteConfig(
        id=str(site["id"]), name=site.get("name", str(site["id"])), map=map_cfg,
        rules=parse_rules(site.get("rules")), rule_params=rule_params, cameras=cameras,
        zones=[parse_zone(z) for z in raw.get("zones", [])], models=models,
        backend=raw.get("models", {}).get("backend", raw.get("backend", "onnx")),
        backend_options=raw.get("models", {}).get("backend_options", {}),
        events=events, base_dir=base_dir,
    )


def _deep_merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out
