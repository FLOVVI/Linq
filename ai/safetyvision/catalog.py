"""Каталог правил ТБ.

Порядок правил фиксирован: индекс правила = позиция в векторе правил,
который подаётся вместе с видеопотоком (камерой) или зоной, например
``[0, 0, 1, 0, 0, 0, 0, 0, 0]`` — «каску и форму можно не носить, курить нельзя».

Новые правила добавляются только в конец списка, чтобы старые векторы
оставались валидными.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RuleInfo:
    index: int
    code: str
    title: str
    description: str
    severity: str  # low | medium | high | critical
    scope: str  # person | object
    models: tuple[str, ...]  # какие нейросети нужны для правила
    defaults: dict[str, Any] = field(default_factory=dict)


# Общие параметры подтверждения/завершения события (переопределяются в конфиге):
#   confirm_s   — сколько секунд нарушение должно длиться, чтобы стать событием
#   ratio       — доля кадров с нарушением в окне confirm_s
#   clear_s     — сколько секунд без нарушения нужно, чтобы событие закрылось
#   merge_s     — повтор того же нарушения тем же человеком в пределах merge_s продолжает старое событие
#   min_coverage — доля кадров серии, где правило могло что-то сказать (а не «не видно»)
RULES: tuple[RuleInfo, ...] = (
    RuleInfo(0, "helmet", "Нет защитной каски",
             "Голова человека видна, но каска не обнаружена.",
             "medium", "person", ("pose", "ppe"),
             {"confirm_s": 2.0, "ratio": 0.7, "clear_s": 3.0, "merge_s": 20.0, "min_head_px": 14,
              "min_head_conf": 0.55, "memory_s": 6.0, "verify_no_helmet": 0.85, "min_coverage": 0.5,
              "min_head_px_pose": 28, "verify_no_helmet_pose": 0.97}),
    RuleInfo(1, "vest", "Нет спецодежды (жилет/комбинезон)",
             "Корпус человека виден, но сигнальный жилет или спецкостюм не обнаружен.",
             "medium", "person", ("pose", "ppe"),
             {"confirm_s": 2.5, "ratio": 0.7, "clear_s": 3.0, "merge_s": 20.0, "min_torso_px": 24, "memory_s": 6.0,
              "min_coverage": 0.5, "vest_color_min_frac": 0.35, "vest_color_unsure_frac": 0.15,
              # цвета сигнальной одежды (ГОСТ 12.4.281: флуоресцентные жёлто-зелёный, оранжевый) — запасной признак
              # жилета, когда детектор его не видит (оранжевый жилет поверх оранжевой куртки); [] — отключить
              "vest_colors": ["yellow", "orange", "lime"], "occluded_overlap": 0.3}),
    RuleInfo(2, "smoking", "Курение",
             "Сигарета у лица или в руке человека.",
             "high", "person", ("pose", "objects"),
             {"confirm_s": 1.5, "ratio": 0.5, "clear_s": 5.0, "merge_s": 30.0,
              # предельный размер рамки сигареты в ширинах плеч (длинная и короткая сторона)
              "cig_max_len": 0.45, "cig_max_width": 0.25}),
    RuleInfo(3, "phone", "Использование телефона",
             "Телефон у уха или в руках перед лицом.",
             "medium", "person", ("pose", "objects"),
             {"confirm_s": 2.0, "ratio": 0.6, "clear_s": 3.0, "merge_s": 20.0}),
    RuleInfo(4, "running", "Бег по цеху",
             "Скорость перемещения выше допустимой.",
             "medium", "person", ("pose",),
             {"confirm_s": 0.8, "ratio": 0.7, "clear_s": 2.0, "merge_s": 10.0, "speed_mps": 2.3}),
    RuleInfo(5, "danger_zone", "Нахождение в опасной зоне",
             "Человек вошёл в запретную/опасную зону.",
             "high", "person", ("pose",),
             {"confirm_s": 1.0, "ratio": 0.7, "clear_s": 2.0, "merge_s": 15.0}),
    RuleInfo(6, "vehicle_proximity", "Опасное сближение с техникой",
             "Человек слишком близко к движущемуся погрузчику/транспорту.",
             "high", "person", ("pose", "objects"),
             {"confirm_s": 0.6, "ratio": 0.6, "clear_s": 2.0, "merge_s": 10.0,
              "distance_m": 2.5, "min_vehicle_speed_mps": 0.3}),
    RuleInfo(7, "fall", "Падение / человек лежит",
             "Человек упал или неподвижно лежит на полу.",
             "critical", "person", ("pose",),
             {"confirm_s": 3.0, "ratio": 0.7, "clear_s": 4.0, "merge_s": 60.0}),
    RuleInfo(8, "fire", "Открытый огонь / дым",
             "Пламя или задымление вне отведённых мест.",
             "critical", "object", ("objects",),
             {"confirm_s": 2.0, "ratio": 0.6, "clear_s": 5.0, "merge_s": 60.0,
              "smoke_min_conf": 0.5, "smoke_min_area": 0.01}),
    RuleInfo(9, "gloves", "Нет перчаток",
             "Кисти рук видны, перчатки не обнаружены.",
             "low", "person", ("pose", "ppe"),
             {"confirm_s": 3.0, "ratio": 0.8, "clear_s": 3.0, "merge_s": 30.0}),
    RuleInfo(10, "goggles", "Нет защитных очков/щитка",
             "Лицо видно, защитные очки или щиток не обнаружены.",
             "low", "person", ("pose", "ppe"),
             {"confirm_s": 3.0, "ratio": 0.8, "clear_s": 3.0, "merge_s": 30.0}),
)

RULE_BY_CODE: dict[str, RuleInfo] = {r.code: r for r in RULES}
NUM_RULES = len(RULES)


def rules_to_vector(enabled: set[str]) -> list[int]:
    return [1 if r.code in enabled else 0 for r in RULES]


def parse_rules(spec: Any) -> dict[str, int]:
    """Разбирает описание правил в словарь {code: 0/1}.

    Поддерживаются:
      * вектор ``[0, 1, 1, ...]`` (позиции по каталогу; короче каталога — недостающие не меняются),
      * словарь ``{"helmet": 1, "smoking": 0}``,
      * список кодов ``["helmet", "smoking"]`` (перечисленные включены).
    """
    if spec is None:
        return {}
    if isinstance(spec, dict):
        out = {}
        for k, v in spec.items():
            if k not in RULE_BY_CODE:
                raise ValueError(f"Неизвестное правило: {k}")
            out[k] = int(bool(v))
        return out
    if isinstance(spec, (list, tuple)):
        if all(isinstance(x, str) for x in spec):
            for k in spec:
                if k not in RULE_BY_CODE:
                    raise ValueError(f"Неизвестное правило: {k}")
            return {k: 1 for k in spec}
        if len(spec) > NUM_RULES:
            raise ValueError(f"Вектор правил длиннее каталога ({len(spec)} > {NUM_RULES})")
        return {RULES[i].code: int(bool(v)) for i, v in enumerate(spec)}
    raise TypeError(f"Неподдерживаемый формат правил: {spec!r}")


def catalog_as_json() -> list[dict[str, Any]]:
    return [
        {
            "index": r.index, "code": r.code, "title": r.title, "description": r.description,
            "severity": r.severity, "scope": r.scope, "models": list(r.models), "defaults": r.defaults,
        }
        for r in RULES
    ]
