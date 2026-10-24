"""Отрисовка: кадр камеры с разметкой и миникарта помещения."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from .events.text import put_text, put_text_center, text_size

GREEN, ORANGE, RED, YELLOW, GREY = (60, 180, 75), (0, 150, 255), (40, 40, 230), (0, 215, 255), (150, 150, 150)
SKELETON = [(5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14),
            (14, 16), (0, 1), (0, 2), (1, 3), (2, 4)]
ZONE_COLORS = {"danger": (40, 40, 220), "dynamic": (0, 120, 255), "area": (200, 140, 40)}


def _hex(c: str | None, default):
    if not c:
        return default
    c = c.lstrip("#")
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return (b, g, r)


def draw_polygon(img, pts, color, alpha=0.25, thickness=2, label: str | None = None):
    pts = np.round(np.asarray(pts)).astype(np.int32)
    if len(pts) < 3:
        return
    over = img.copy()
    cv2.fillPoly(over, [pts], color)
    cv2.addWeighted(over, alpha, img, 1 - alpha, 0, dst=img)
    cv2.polylines(img, [pts], True, color, thickness, cv2.LINE_AA)
    if label:
        # у верхней вершины самой зоны (левый верхний угол описывающего прямоугольника у косой зоны —
        # вне её, подпись висела над людьми рядом)
        top = pts[pts[:, 1] <= pts[:, 1].min() + 5]
        x, y = top[:, 0].min(), pts[:, 1].min()
        put_text(img, label, (int(x) + 2, int(y) + 2), (255, 255, 255), size=14, bg=color)


def draw_camera(frame: np.ndarray, state: dict[str, Any]) -> np.ndarray:
    """state: persons [{box, kpts, label, status}], vehicles [{box, kind}], objects [{box, kind, score}],
    zones [{pts, kind, name, color}], header str."""
    img = frame.copy()
    h, w = img.shape[:2]
    lw = max(2, int(round(w / 640)))
    for z in state.get("zones", []):
        draw_polygon(img, z["pts"], _hex(z.get("color"), ZONE_COLORS.get(z["kind"], GREY)), 0.18, lw, z["name"])
    for v in state.get("vehicles", []):
        x1, y1, x2, y2 = map(int, v["box"])
        cv2.rectangle(img, (x1, y1), (x2, y2), YELLOW, lw)
        put_text(img, f"{v['kind']} {v.get('speed', '')}", (x1, y1 - 20), (0, 0, 0), size=14, bg=YELLOW)
    for o in state.get("objects", []):
        x1, y1, x2, y2 = map(int, o["box"])
        cv2.rectangle(img, (x1, y1), (x2, y2), (255, 0, 255), lw)
        # у рамки от верхнего края кадра (облако дыма) подпись — внутри справа, иначе она ложится на заголовок
        txt = f"{o['kind']} {o['score']:.2f}"
        org = (x1, y1 - 20) if y1 >= 40 else (x2 - text_size(txt, 14)[0] - 8 - lw, y1 + lw + 2)
        put_text(img, txt, org, (255, 255, 255), size=14, bg=(160, 0, 160))
    for p in state.get("persons", []):
        color = {"violation": RED, "pending": ORANGE}.get(p.get("status"), GREEN)
        x1, y1, x2, y2 = map(int, p["box"])
        k = p.get("kpts")
        if k is not None:
            for a, b in SKELETON:
                if k[a, 2] > 0.5 and k[b, 2] > 0.5:
                    cv2.line(img, tuple(map(int, k[a, :2])), tuple(map(int, k[b, :2])), color, 1, cv2.LINE_AA)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, lw)
        if p.get("label"):
            put_text(img, p["label"], (x1, y1 - 22), (255, 255, 255), size=15, bg=color)
    if state.get("header"):
        put_text(img, state["header"], (6, 6), (255, 255, 255), size=16, bg=(30, 30, 30))
    return img


# --- миникарта: плоская схема помещения (как план эвакуации), а не мозаика из кадров -------------------
MAP_BG = (255, 255, 255)
ROOM_FILL, ROOM_EDGE = (214, 214, 214), (95, 95, 95)
COVER_FILL = (236, 236, 236)
BLIND_HATCH = (172, 172, 172)
CAM_FILL, CAM_EDGE = (204, 208, 248), (70, 70, 170)
PERSON_FILL = {"ok": (255, 255, 255), "pending": (0, 165, 255), "violation": (50, 50, 215)}
DANGER_FILL, DYN_FILL, VEHICLE_FILL = (60, 60, 200), (190, 190, 245), (35, 35, 35)
INK = (40, 40, 40)


def _rounded_rect(x1: float, y1: float, x2: float, y2: float, r: float, n: int = 8) -> np.ndarray:
    r = max(0.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = []
    for cx, cy, a0 in ((x2 - r, y1 + r, -90), (x2 - r, y2 - r, 0), (x1 + r, y2 - r, 90), (x1 + r, y1 + r, 180)):
        for a in np.linspace(a0, a0 + 90, n):
            pts.append((cx + r * np.cos(np.radians(a)), cy + r * np.sin(np.radians(a))))
    return np.round(np.array(pts)).astype(np.int32)


def _hatch(img: np.ndarray, mask: np.ndarray, color, step: int = 9) -> None:
    lines = np.zeros_like(mask)
    h, w = mask.shape
    for c in range(-h, w, step):
        cv2.line(lines, (c, h), (c + h, 0), 255, 1, cv2.LINE_AA)
    sel = (lines > 0) & (mask > 0)
    img[sel] = color


def _camera_glyph(img, xy: np.ndarray, toward: np.ndarray | None, size: float, number: str) -> None:
    """Треугольник с номером: вершина — место камеры, основание — в сторону обзора."""
    d = np.array([0.0, 1.0]) if toward is None else toward - xy
    n = np.linalg.norm(d)
    d = d / n if n > 1e-6 else np.array([0.0, 1.0])
    perp = np.array([-d[1], d[0]])
    base = xy + d * size * 1.15
    tri = np.array([xy, base + perp * size * 0.75, base - perp * size * 0.75])
    cv2.fillPoly(img, [np.round(tri).astype(np.int32)], CAM_FILL, cv2.LINE_AA)
    cv2.polylines(img, [np.round(tri).astype(np.int32)], True, CAM_EDGE, 2, cv2.LINE_AA)
    c = tri.mean(0)
    put_text_center(img, number, c + d * size * 0.12, CAM_EDGE, size=max(12, int(size * 0.62)))


def _person_glyph(img, xy, r: int, status: str, number: str) -> None:
    fill = PERSON_FILL.get(status, PERSON_FILL["ok"])
    c = tuple(int(v) for v in xy)
    cv2.circle(img, c, r, fill, -1, cv2.LINE_AA)
    cv2.circle(img, c, r, INK if status == "ok" else (255, 255, 255), 2, cv2.LINE_AA)
    put_text_center(img, number, c, INK if status == "ok" else (255, 255, 255), size=max(11, int(r * 1.05)))


def _legend(width: int, items: list[tuple[str, str]], cams: list[str], u: int,
            scale: tuple[float, str] | None = None) -> np.ndarray:
    """Легенда под картой: значок + подпись, затем список камер «1 — Коридор»."""
    row_h = int(u * 2.2)
    col_w = max(int(u * 11), 1)
    per_row = max(1, width // col_w)
    rows = (len(items) + per_row - 1) // per_row + (1 if cams or scale else 0)
    img = np.full((rows * row_h + u, width, 3), 255, np.uint8)
    cv2.line(img, (u, 2), (width - u, 2), (200, 200, 200), 1)
    for i, (kind, label) in enumerate(items):
        x = u + (i % per_row) * col_w
        y = u + (i // per_row) * row_h + row_h // 2
        c = np.array([x + u * 0.8, y], float)
        if kind == "camera":
            _camera_glyph(img, c - [0, u * 0.7], c + [0, u], u * 0.9, "1")
        elif kind in PERSON_FILL:
            _person_glyph(img, c, int(u * 0.7), kind, "2")
        elif kind == "blind":
            m = np.zeros(img.shape[:2], np.uint8)
            cv2.rectangle(img, (int(c[0] - u * 0.7), int(y - u * 0.6)), (int(c[0] + u * 0.7), int(y + u * 0.6)), ROOM_FILL, -1)
            cv2.rectangle(m, (int(c[0] - u * 0.7), int(y - u * 0.6)), (int(c[0] + u * 0.7), int(y + u * 0.6)), 255, -1)
            _hatch(img, m, BLIND_HATCH, max(5, u // 3))
        else:
            fill = {"danger": DANGER_FILL, "dynamic": DYN_FILL, "vehicle": VEHICLE_FILL}[kind]
            cv2.rectangle(img, (int(c[0] - u * 0.7), int(y - u * 0.6)), (int(c[0] + u * 0.7), int(y + u * 0.6)), fill, -1)
        put_text(img, label, (int(c[0] + u * 1.3), int(y - u * 0.55)), INK, size=max(12, int(u * 0.8)))
    if cams or scale:
        y = u + (rows - 1) * row_h + row_h // 2
        x = u
        if scale:  # линейка масштаба
            L, label = scale
            cv2.line(img, (x, y), (int(x + L), y), INK, 3)
            for xx in (x, int(x + L)):
                cv2.line(img, (xx, int(y - u * 0.4)), (xx, int(y + u * 0.4)), INK, 2)
            put_text(img, label, (int(x + L + u * 0.4), int(y - u * 0.55)), INK, size=max(12, int(u * 0.8)))
            x = int(x + L + u * 4)
        if cams:
            put_text(img, "   ".join(f"{i + 1} — {n}" for i, n in enumerate(cams)), (x, int(y - u * 0.55)), INK,
                     size=max(12, int(u * 0.8)))
    return img


def draw_minimap(canvas, background: np.ndarray | None, state: dict[str, Any], long_side: int = 900) -> np.ndarray:
    """Плоская схема: помещение, зоны обзора и слепые зоны, камеры-треугольники с номерами,
    люди-кружки с номерами (цвет — статус), опасные зоны и техника — квадраты, легенда и масштаб.

    state: zones [{polygon(м), kind, name, color}], footprints {cam: poly}, cameras {cam: xy|None},
    camera_names [str] (порядок нумерации), room poly|None, blind [poly], people [{xy, status, label}],
    vehicles [{xy, kind, radius_m}]."""
    u = max(12, int(round(long_side / 38)))  # базовый размер значков
    pad = 2 * u  # камеры часто висят на самом краю помещения — оставляем им место
    k = (long_side - 2 * pad) / max(canvas.W, canvas.H)
    W, H = int(round(canvas.W * k)) + 2 * pad, int(round(canvas.H * k)) + 2 * pad

    def px(xy) -> np.ndarray:
        return canvas.to_px(xy) * k + pad

    img = np.full((H, W, 3), MAP_BG, np.uint8)
    fps = {c: np.asarray(fp) for c, fp in state.get("footprints", {}).items() if fp is not None and len(fp) >= 3}
    cams_xy = {c: np.asarray(v) for c, v in state.get("cameras", {}).items() if v is not None}
    room = state.get("room")
    room_mask = np.zeros((H, W), np.uint8)
    if background is not None:  # свой план помещения
        img[pad:H - pad, pad:W - pad] = cv2.resize(background, (W - 2 * pad, H - 2 * pad))
        room_mask[pad:H - pad, pad:W - pad] = 255
    elif room is not None and len(room) >= 3:
        rp = np.round(px(room)).astype(np.int32)
        cv2.fillPoly(img, [rp], ROOM_FILL, cv2.LINE_AA)
        cv2.fillPoly(room_mask, [rp], 255)
    else:  # контур не задан: прямоугольник со скруглёнными углами вокруг зон обзора и камер
        pts = [px(fp) for fp in fps.values()] + [px(v) for v in cams_xy.values()]
        if pts:
            p = np.concatenate(pts)
            m = 0.6 * canvas.s * k
            lo, hi = np.maximum(p.min(0) - m, pad // 2), np.minimum(p.max(0) + m, [W - pad // 2, H - pad // 2])
            rr = _rounded_rect(lo[0], lo[1], hi[0], hi[1], 1.2 * canvas.s * k)
            cv2.fillPoly(img, [rr], ROOM_FILL, cv2.LINE_AA)
            cv2.fillPoly(room_mask, [rr], 255)
    if not room_mask.any():  # ни одна камера ещё не откалибрована
        for i, line in enumerate(("Карта строится:", "камеры калибруются", "по проходящим людям")):
            put_text_center(img, line, (W / 2, H / 2 + (i - 1) * u * 1.6), (120, 120, 120), size=max(14, u))
    # зоны обзора светлее пола, непросматриваемое — штриховка (слепые зоны)
    cover = np.zeros((H, W), np.uint8)
    for fp in fps.values():
        cv2.fillPoly(cover, [np.round(px(fp)).astype(np.int32)], 255)
    if background is None:
        img[(cover > 0) & (room_mask > 0)] = COVER_FILL
    blind = np.zeros((H, W), np.uint8)
    for poly in state.get("blind", []):
        cv2.fillPoly(blind, [np.round(px(poly)).astype(np.int32)], 255)
    _hatch(img, blind & room_mask & ~cover, BLIND_HATCH, max(8, int(u * 0.9)))
    for fp in fps.values():
        cv2.polylines(img, [np.round(px(fp)).astype(np.int32)], True, (190, 190, 190), 1, cv2.LINE_AA)
    if background is None:
        if room is not None and len(room) >= 3:
            cv2.polylines(img, [np.round(px(room)).astype(np.int32)], True, ROOM_EDGE, 3, cv2.LINE_AA)
        else:
            cnts, _ = cv2.findContours(room_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            cv2.drawContours(img, cnts, -1, ROOM_EDGE, 3, cv2.LINE_AA)
    # зоны
    labels: list[tuple[str, tuple[int, int]]] = []
    for z in state.get("zones", []):
        if not z.get("polygon"):
            continue
        zp = np.round(px(z["polygon"])).astype(np.int32)
        fill = _hex(z.get("color"), DANGER_FILL if z["kind"] == "danger" else ZONE_COLORS.get(z["kind"], GREY))
        if z["kind"] == "danger":
            cv2.fillPoly(img, [zp], fill, cv2.LINE_AA)
        else:
            over = img.copy()
            cv2.fillPoly(over, [zp], fill, cv2.LINE_AA)
            cv2.addWeighted(over, 0.35, img, 0.65, 0, dst=img)
        cv2.polylines(img, [zp], True, fill, 2, cv2.LINE_AA)
        if z.get("name"):
            labels.append((z["name"], (int(zp[:, 0].min()), int(zp[:, 1].max()) + 3)))
    # техника: чёрный квадрат, вокруг — розовая опасная зона
    for v in state.get("vehicles", []):
        c = px(v["xy"])[0]
        if v.get("radius_m"):
            r = v["radius_m"] * canvas.s * k
            cv2.rectangle(img, tuple(np.round(c - r).astype(int)), tuple(np.round(c + r).astype(int)), DYN_FILL, -1)
        h = u * 0.8
        cv2.rectangle(img, tuple(np.round(c - h).astype(int)), tuple(np.round(c + h).astype(int)), VEHICLE_FILL, -1)
    # камеры
    names = list(state.get("camera_names") or list(state.get("cameras", {})))
    for i, cam in enumerate(state.get("cameras", {})):
        if cam not in cams_xy:
            continue
        toward = px(fps[cam].mean(0))[0] if cam in fps else None
        num = str(names.index(cam) + 1) if cam in names else str(i + 1)
        _camera_glyph(img, px(cams_xy[cam])[0], toward, u * 1.5, num)
    # люди
    for p in state.get("people", []):
        num = str(p.get("label", "")).lstrip("#")
        _person_glyph(img, px(p["xy"])[0], int(u * 0.85), p.get("status", "ok"), num)
    for text, org in labels:  # подписи зон — поверх значков, чтобы их не закрывали люди
        put_text(img, text, org, INK, size=max(12, int(u * 0.8)), bg=(255, 255, 255))
    m5 = 5 if canvas.W / canvas.s > 8 else 1
    scale = (m5 * canvas.s * k, f"{m5} м")
    items = [("camera", "камера"), ("ok", "человек"), ("pending", "проверка"), ("violation", "нарушение"),
             ("blind", "слепая зона")]
    if any(z.get("kind") == "danger" for z in state.get("zones", [])):
        items.append(("danger", "опасная зона"))
    if state.get("vehicles"):
        items += [("vehicle", "техника"), ("dynamic", "зона у техники")]
    return np.vstack([img, _legend(W, items, list(state.get("camera_titles", [])), u, scale)])
