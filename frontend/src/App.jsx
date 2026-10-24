import React, { useState, useEffect, useRef } from 'react';
import { api } from './api';
import {
  Video,
  CheckCircle2,
  XCircle,
  Send,
  Map,
  BarChart3,
  Plus,
  Eye,
  Sun,
  Moon,
  Database,
  Square,
  Pentagon,
  Trash2,
  Layers,
  Camera,
  Upload,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Volume2,
  Lock,
  FileDown,
  FileText,
  Maximize2,
  RefreshCw,
  FlipHorizontal,
  Flame,
  LayoutGrid,
  LogOut,
  Keyboard,
  Image as ImageIcon,
  Compass,
  Search,
  Download,
} from 'lucide-react';

// 13 типов нарушений
const VIOLATION_TYPES = [
  { id: 0, code: '01', enumKey: 'RUNNING', name: 'Бег по цеху / резкие перемещения', ai: true },
  { id: 1, code: '02', enumKey: 'DANGER_PROXIMITY', name: 'Опасное сближение с техникой', ai: true },
  { id: 2, code: '03', enumKey: 'PHONE_USAGE', name: 'Использование мобильного телефона', ai: true },
  { id: 3, code: '04', enumKey: 'SMOKING_FIRE', name: 'Курение / открытый огонь', ai: true },
  { id: 4, code: '05', enumKey: 'FENCE_CLIMBING', name: 'Перелезание через ограждения', ai: false },
  { id: 5, code: '06', enumKey: 'NO_HARNESS_HEIGHT', name: 'Работа на высоте без страховки', ai: false },
  { id: 6, code: '07', enumKey: 'PERSON_FALL', name: 'Падение человека / неподвижность', ai: true },
  { id: 7, code: '08', enumKey: 'CARGO_VIOLATION', name: 'Переноска груза с нарушением правил', ai: false },
  { id: 8, code: '09', enumKey: 'NO_HELMET', name: 'Нет защитной каски', ai: true },
  { id: 9, code: '10', enumKey: 'NO_VEST', name: 'Нет спецодежды (сигнальный жилет)', ai: true },
  { id: 10, code: '11', enumKey: 'DANGER_ZONE', name: 'Нахождение в опасной зоне', ai: true },
  { id: 11, code: '12', enumKey: 'NO_GLOVES', name: 'Нет перчаток', ai: true },
  { id: 12, code: '13', enumKey: 'NO_GOGGLES', name: 'Нет защитных очков / щитка', ai: true },
];

function cameraSummary(cameras, events) {
  return cameras.map((cam) => {
    const evs = events.filter((e) => e.camera_id === cam.id);
    const real = evs.filter((e) => e.status !== 'false_alarm');
    const confirmed = evs.filter((e) => e.status === 'confirmed').length;
    const reviewed = confirmed + evs.filter((e) => e.status === 'false_alarm').length;
    const counts = {};
    real.forEach((e) => (counts[e.violation] = (counts[e.violation] || 0) + 1));
    const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 2);
    const title = (k) => VIOLATION_TYPES.find((v) => v.enumKey === k);
    return {
      id: cam.id,
      site: cam.site_name,
      code: cam.code,
      type: cam.cameraType,
      total: real.length,
      confirmed,
      reviewed,
      top: top.map(([k, n]) => `[${title(k)?.code}] ${title(k)?.name} (${n})`).join(' / '),
    };
  });
}

function playSoftBeep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = 660;
    gain.gain.value = 0.04;
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.2);
    osc.onended = () => ctx.close();
  } catch {}
}

const DB_USERS = [
  { id: 1, login: 'mikhalyich_ot', full_name: 'Кузьмин М.П.', position: 'Специалист по ОТ', role_id: 1, role_name: 'Роль 1: Специалист по ОТ', canEditRules: true },
  { id: 2, login: 'disp_smena1', full_name: 'Соколов А.В.', position: 'Диспетчер ЦУП', role_id: 3, role_name: 'Роль 3: Диспетчер', canEditRules: false },
  { id: 3, login: 'master_ceh1', full_name: 'Громов И.С.', position: 'Мастер смены', role_id: 2, role_name: 'Роль 2: Мастер участка', canEditRules: false },
  { id: 4, login: 'it_linq_admin', full_name: 'Дехтерюк Д.К.', position: 'ИТ-Инженер LinQ', role_id: 7, role_name: 'Роль 7: ИТ-интегратор', canEditRules: true },
];

const DB_ROLES = [
  { id: 1, name: 'Специалист по охране труда' },
  { id: 2, name: 'Мастер производственного участка' },
  { id: 3, name: 'Оператор / Диспетчер ЦУП' },
  { id: 7, name: 'ИТ-интегратор LinQ TPU' },
];

function sortPolygonPoints(points) {
  if (!points || points.length < 3) return points || [];
  const cx = points.reduce((acc, p) => acc + p.x, 0) / points.length;
  const cy = points.reduce((acc, p) => acc + p.y, 0) / points.length;
  return [...points].sort(
    (a, b) => Math.atan2(a.y - cy, a.x - cx) - Math.atan2(b.y - cy, b.x - cx)
  );
}

function isPointInPolygon(pt, polygonPoints) {
  if (!polygonPoints || polygonPoints.length < 3) return false;
  let inside = false;
  for (let i = 0, j = polygonPoints.length - 1; i < polygonPoints.length; j = i++) {
    const xi = polygonPoints[i].x;
    const yi = polygonPoints[i].y;
    const xj = polygonPoints[j].x;
    const yj = polygonPoints[j].y;
    const intersect =
      yi > pt.y !== yj > pt.y &&
      pt.x < ((xj - xi) * (pt.y - yi)) / (yj - yi + 0.00001) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

function checkWorkerZoneCollision(worker, zones) {
  const center = { x: worker.x + worker.w / 2, y: worker.y + worker.h / 2 };
  for (const zone of zones) {
    if (zone.shape === 'rect' && zone.rect) {
      const r = zone.rect;
      const overlapped =
        center.x >= r.x &&
        center.x <= r.x + r.w &&
        center.y >= r.y &&
        center.y <= r.y + r.h;
      if (overlapped) return zone;
    } else if (zone.shape === 'polygon' && zone.points?.length >= 3) {
      if (isPointInPolygon(center, zone.points)) return zone;
    }
  }
  return null;
}

const HOURLY_STATS = [
  { hour: '08:00', count: 14, label: 'Пересменка' },
  { hour: '10:00', count: 9, label: 'Утро' },
  { hour: '12:00', count: 5, label: 'Обед' },
  { hour: '14:00', count: 7, label: 'День' },
  { hour: '16:00', count: 4, label: 'Вечер' },
  { hour: '18:00', count: 6, label: 'Сдача смены' },
  { hour: '20:00', count: 11, label: 'Ночь' },
];

// Кнопка с умным позиционированием подсказки (align="right" предотвращает обрезание текста у правого края)
function IconTipButton({ icon: Icon, label, active, onClick, badge, isDark, align = 'center' }) {
  const tooltipPosClass =
    align === 'right'
      ? 'right-0'
      : align === 'left'
      ? 'left-0'
      : 'left-1/2 -translate-x-1/2';

  return (
    <button
      type="button"
      onClick={onClick}
      className={`group relative flex items-center justify-center w-9 h-9 rounded-xl border transition-all cursor-pointer shrink-0 ${
        active
          ? 'bg-sky-600 text-white border-sky-500 shadow-xs'
          : isDark
          ? 'bg-slate-800/90 text-slate-300 border-slate-700 hover:border-slate-500 hover:text-white'
          : 'bg-white text-slate-700 border-slate-200 hover:border-slate-400 hover:text-slate-900 shadow-2xs'
      }`}
    >
      <Icon size={16} />
      {badge !== undefined && badge > 0 && (
        <span className="absolute -top-1 -right-1 px-1 min-w-[16px] h-4 rounded-full bg-amber-500 text-slate-950 text-[10px] font-bold flex items-center justify-center">
          {badge}
        </span>
      )}
      <span
        className={`pointer-events-none absolute -bottom-9 ${tooltipPosClass} px-2.5 py-1 rounded-md bg-slate-950 text-white text-[11px] font-medium whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-50 shadow-lg border border-slate-700`}
      >
        {label}
      </span>
    </button>
  );
}

function LinQExactLogo({ forceDarkText = false, isDark = false }) {
  const mainColor = forceDarkText ? '#1E242B' : isDark ? '#FFFFFF' : '#1E242B';
  const bluePixel = '#38BDF8';
  return (
    <svg
      width="88"
      height="48"
      viewBox="8 8 84 50"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      shapeRendering="crispEdges"
      className="select-none shrink-0"
    >
      <path d="M11 11H18V41H29V48H11V11Z" fill={mainColor} />
      <rect x="33" y="17" width="7" height="7" fill={bluePixel} />
      <rect x="33" y="27" width="7" height="21" fill={mainColor} />
      <path d="M44 27H53V34H51V48H44V27Z" fill={mainColor} />
      <rect x="53" y="34" width="7" height="14" fill={mainColor} />
      <path d="M63 11H75V18H70V41H75V18H82V48H63V11Z" fill={mainColor} />
      <rect x="82" y="48" width="7" height="7" fill={bluePixel} />
    </svg>
  );
}

function GostRostechnadzorReport({ cameras, events, currentUser, hourly }) {
  const confirmedEvents = events.filter((e) => e.status !== 'false_alarm');
  return (
    <div
      style={{ fontFamily: "'Times New Roman', Times, serif" }}
      className="bg-white text-black p-8 max-w-[210mm] mx-auto text-[12pt] leading-normal"
    >
      <div className="flex justify-between items-start border-b-2 border-black pb-4 mb-4 text-[10pt]">
        <div className="w-1/2 pr-4">
          <p className="font-bold uppercase">Форма представления сведений</p>
          <p>
            Утверждена Приказом Федеральной службы по экологическому, технологическому и атомному надзору (Ростехнадзор) от 11.12.2020 № 518
          </p>
          <p className="mt-1">Оформление по ГОСТ Р 7.0.97-2016</p>
        </div>
        <div className="w-1/2 pl-4 text-right">
          <p className="font-bold uppercase">УТВЕРЖДАЮ</p>
          <p>Главный инженер эксплуатирующей организации</p>
          <p className="mt-2">___________________ / И.О. Фамилия /</p>
          <p className="text-[9pt]">«{new Date().getDate()}» октября 2026 г. М.П.</p>
        </div>
      </div>

      <div className="text-center mb-5">
        <h1 className="text-[13pt] font-bold uppercase tracking-tight">
          СВЕДЕНИЯ ОБ ОРГАНИЗАЦИИ ПРОИЗВОДСТВЕННОГО КОНТРОЛЯ ЗА СОБЛЮДЕНИЕМ ТРЕБОВАНИЙ ПРОМЫШЛЕННОЙ БЕЗОПАСНОСТИ
        </h1>
        <p className="text-[10pt] mt-1">
          по данным автоматизированного аппаратно-программного комплекса видеоаналитики «LinQ Vision Guard» на базе ускорителей LinQ TPU
        </p>
      </div>

      <div className="mb-4 break-inside-avoid">
        <h2 className="text-[11pt] font-bold uppercase mb-1.5">
          1. Общие сведения об организации автоматизированного производственного контроля на ОПО
        </h2>
        <table className="w-full border-collapse border border-black text-[10pt]">
          <tbody>
            <tr>
              <td className="border border-black p-1.5 font-bold w-2/5">Наименование эксплуатирующей организации</td>
              <td className="border border-black p-1.5">Промышленное предприятие (АПК ООО «ХайТэк» • Платформа LinQ TPU)</td>
            </tr>
            <tr>
              <td className="border border-black p-1.5 font-bold">Ответственный за осуществление производственного контроля</td>
              <td className="border border-black p-1.5">{currentUser.full_name} ({currentUser.position})</td>
            </tr>
            <tr>
              <td className="border border-black p-1.5 font-bold">Количество контролируемых участков / видеопотоков</td>
              <td className="border border-black p-1.5">
                Активных видеопотоков: {cameras.length} шт.
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="mb-4 break-inside-avoid">
        <h2 className="text-[11pt] font-bold uppercase mb-1.5">
          2. Состояние оснащенности производственных участков средствами видеоаналитики
        </h2>
        <table className="w-full border-collapse border border-black text-[9.5pt]">
          <thead>
            <tr className="bg-slate-100 font-bold text-center">
              <th className="border border-black p-1.5">Код узла</th>
              <th className="border border-black p-1.5">Наименование производственного участка</th>
              <th className="border border-black p-1.5">Тип камеры</th>
              <th className="border border-black p-1.5">Вектор правил контроля</th>
              <th className="border border-black p-1.5">Выделенные зоны контроля</th>
              <th className="border border-black p-1.5">Статус LinQ TPU</th>
            </tr>
          </thead>
          <tbody>
            {cameras.map((cam) => (
              <tr key={cam.id}>
                <td className="border border-black p-1.5 text-center font-bold">{cam.code}</td>
                <td className="border border-black p-1.5">{cam.site_name}</td>
                <td className="border border-black p-1.5 text-center">
                  {cam.cameraType === 'dynamic' ? 'Поворотная PTZ' : 'Стационарная'}
                </td>
                <td className="border border-black p-1.5 text-center font-mono">
                  [{cam.rulesVector.join(', ')}]
                </td>
                <td className="border border-black p-1.5">
                  {cam.zones.length > 0
                    ? cam.zones.map((z) => `${z.label} (${z.schedule || '24/7'})`).join('; ')
                    : 'Общий периметр кадра (24/7)'}
                </td>
                <td className="border border-black p-1.5 text-center">
                  Активен ({cam.fps} FPS)
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mb-4 break-inside-avoid">
        <h2 className="text-[11pt] font-bold uppercase mb-1.5">
          3. Ведомость выявленных нарушений требований промышленной безопасности
        </h2>
        <table className="w-full border-collapse border border-black text-[9.5pt]">
          <thead>
            <tr className="bg-slate-100 font-bold text-center">
              <th className="border border-black p-1.5">№ акта (ID)</th>
              <th className="border border-black p-1.5">Время фиксации</th>
              <th className="border border-black p-1.5">Участок / Камера</th>
              <th className="border border-black p-1.5">Выявленный паттерн</th>
              <th className="border border-black p-1.5">Достоверность ИИ</th>
              <th className="border border-black p-1.5">Примечание и ответственный</th>
            </tr>
          </thead>
          <tbody>
            {confirmedEvents.map((ev) => (
              <tr key={ev.id}>
                <td className="border border-black p-1.5 text-center font-bold">#{ev.id}</td>
                <td className="border border-black p-1.5 text-center">{ev.timestamp}</td>
                <td className="border border-black p-1.5">{ev.camera_code} • {ev.site_name}</td>
                <td className="border border-black p-1.5 font-bold">
                  [{ev.pattern_code}] {ev.violation_title}
                </td>
                <td className="border border-black p-1.5 text-center">
                  {Math.round(ev.confidence * 100)}%
                </td>
                <td className="border border-black p-1.5">
                  {ev.description} (Отв.: {ev.processed_by_name})
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mb-6 break-inside-avoid">
        <h2 className="text-[11pt] font-bold uppercase mb-1.5">
          4. Анализ распределения инцидентов по часам рабочей смены
        </h2>
        <table className="w-full border-collapse border border-black text-[9.5pt] text-center">
          <thead>
            <tr className="bg-slate-100 font-bold">
              <th className="border border-black p-1.5 text-left">Показатель смены</th>
              {hourly.map((h, i) => (
                <th key={i} className="border border-black p-1.5">
                  {h.hour} ({h.label})
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="border border-black p-1.5 text-left font-bold">Количество выявленных нарушений</td>
              {hourly.map((h, i) => (
                <td key={i} className="border border-black p-1.5 font-bold">
                  {h.count} ед.
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <div className="grid grid-cols-2 gap-8 pt-4 border-t border-black text-[10pt] break-inside-avoid">
        <div>
          <p className="font-bold">Ответственный за осуществление производственного контроля:</p>
          <p className="mt-4">___________________ / {currentUser.full_name} /</p>
        </div>
        <div>
          <p className="font-bold">Представитель ИТ-службы эксплуатации LinQ TPU:</p>
          <p className="mt-4">___________________ / Дехтерюк Д.К. /</p>
        </div>
      </div>
    </div>
  );
}

// Интерактивная карта цеха: без рамок участков, с перемещением правой кнопкой мыши (ПКМ) и переходом к камере по двойному клику
function UnifiedWorkshopMap({
  cameras,
  selectedCamId,
  onSelectCam,
  onDoubleClickCam,
  onDragCamStart,
  events,
  activeEvent,
  onSelectEvent,
  showHeatmap,
  floorplanBgUrl,
  mapZoom = 1,
  mapPan = { x: 0, y: 0 },
  isPanningMap = false,
  onMapMouseDown,
  onWheelZoom,
  mapInnerRef,
  onMouseMove,
  onMouseUp,
  minHeightClass = 'min-h-[540px]',
}) {
  return (
    <div
      onContextMenu={(e) => e.preventDefault()}
      onMouseDown={onMapMouseDown}
      onWheel={onWheelZoom}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
      className={`relative bg-[#0B1120] rounded-2xl flex-1 ${minHeightClass} select-none overflow-hidden ${
        isPanningMap ? 'cursor-grabbing' : 'cursor-default'
      }`}
    >
      {/* Масштабируемый и перемещаемый (ПКМ) слой карты цеха */}
      <div
        ref={mapInnerRef}
        style={{
          transform: `translate(${mapPan.x}px, ${mapPan.y}px) scale(${mapZoom})`,
          transformOrigin: 'center center',
        }}
        className={`absolute inset-0 w-full h-full ${
          isPanningMap ? '' : 'transition-transform duration-150 ease-out'
        }`}
      >
        {floorplanBgUrl && (
          <img
            src={floorplanBgUrl}
            alt="Чертеж цеха"
            className="absolute inset-0 w-full h-full object-cover opacity-55 pointer-events-none"
          />
        )}

        {/* Бесконечная координатная сетка без ограничивающих рамок */}
        <div
          className="absolute -inset-[200%] w-[500%] h-[500%] opacity-15 pointer-events-none"
          style={{
            backgroundImage:
              'linear-gradient(to right, #64748b 1px, transparent 1px), linear-gradient(to bottom, #64748b 1px, transparent 1px)',
            backgroundSize: '36px 36px',
          }}
        />

        {showHeatmap && (
          <div
            className="absolute w-64 h-64 rounded-full blur-2xl opacity-55 pointer-events-none"
            style={{
              left: '24%',
              top: '28%',
              background:
                'radial-gradient(circle, rgba(245,158,11,0.75) 0%, rgba(56,189,248,0.35) 60%, transparent 80%)',
            }}
          />
        )}

        {/* ТОЧКИ ИИ-ЛОКАТОРА НА КАРТЕ ЦЕХА */}
        {events
          .filter((e) => e.status !== 'false_alarm' && e.ai_pos)
          .slice(0, 8)
          .map((ev) => {
            const isCurrent = activeEvent && ev.id === activeEvent.id;
            return (
              <div
                key={`evt-pin-${ev.id}`}
                style={{
                  left: `${ev.ai_pos.x}%`,
                  top: `${ev.ai_pos.y}%`,
                }}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectEvent?.(ev.id);
                }}
                title={`Инцидент #${ev.id}: ${ev.violation_title} (${ev.camera_code})`}
                className="absolute -translate-x-1/2 -translate-y-1/2 flex flex-col items-center cursor-pointer z-25"
              >
                {isCurrent && (
                  <span className="w-6 h-6 rounded-full bg-amber-500/70 animate-ping absolute" />
                )}
                <span
                  className={`w-3.5 h-3.5 rounded-full border-2 border-white relative z-10 transition-transform ${
                    isCurrent ? 'bg-amber-500 scale-125 shadow-md' : 'bg-rose-500/85 hover:scale-110'
                  }`}
                />
                {isCurrent && (
                  <span className="text-[10px] font-mono bg-slate-950/90 text-amber-300 border border-amber-500/40 px-2 py-0.5 rounded-md mt-1 whitespace-nowrap shadow">
                    #{ev.id} • {ev.camera_code} (X:{ev.ai_pos.x}%, Y:{ev.ai_pos.y}%)
                  </span>
                )}
              </div>
            );
          })}

        {/* КАМЕРЫ С ЛУЧОМ ОБЗОРА */}
        {cameras.map((cam) => {
          const isSelected = cam.id === selectedCamId;
          const totalAngle = (cam.mapDirection || 0) + (cam.panAngle || 0);
          return (
            <div
              key={cam.id}
              style={{
                left: `${cam.mapPos.x}%`,
                top: `${cam.mapPos.y}%`,
              }}
              onMouseDown={(e) => {
                if (e.button !== 0) return;
                e.stopPropagation();
                onSelectCam?.(cam.id);
                onDragCamStart?.(cam.id);
              }}
              onDoubleClick={(e) => {
                e.stopPropagation();
                onDoubleClickCam?.(cam.id);
              }}
              title="Двойной клик — перейти к видеопотоку камеры"
              className="group absolute -translate-x-1/2 -translate-y-1/2 w-8 h-8 flex items-center justify-center cursor-grab active:cursor-grabbing z-20"
            >
              <svg
                viewBox="-65 -65 130 130"
                className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-32 h-32 overflow-visible"
              >
                <defs>
                  <radialGradient id={`fov-grad-${cam.id}`} cx="0" cy="0" r="62" gradientUnits="userSpaceOnUse">
                    <stop
                      offset="0%"
                      stopColor={isSelected ? '#38bdf8' : '#94a3b8'}
                      stopOpacity={isSelected ? '0.45' : '0.25'}
                    />
                    <stop
                      offset="100%"
                      stopColor={isSelected ? '#0284c7' : '#64748b'}
                      stopOpacity="0.0"
                    />
                  </radialGradient>
                </defs>
                <g transform={`rotate(${totalAngle})`}>
                  <path
                    d="M 0 0 L -28 -56 A 62 62 0 0 1 28 -56 Z"
                    fill={`url(#fov-grad-${cam.id})`}
                    stroke={isSelected ? 'rgba(56, 189, 248, 0.5)' : 'rgba(148, 163, 184, 0.2)'}
                    strokeWidth="1"
                  />
                  <line
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="-54"
                    stroke={isSelected ? '#38bdf8' : '#94a3b8'}
                    strokeWidth="1"
                    strokeDasharray="3 3"
                    opacity="0.6"
                  />
                </g>
              </svg>

              <div
                className={`relative z-10 w-8 h-8 rounded-full flex items-center justify-center border-2 transition-transform ${
                  isSelected
                    ? 'bg-sky-600 text-white border-white shadow-lg scale-110'
                    : 'bg-slate-900 text-sky-400 border-sky-400/70 hover:scale-110'
                }`}
              >
                <Video size={13} />
                <span
                  className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-slate-950 ${
                    cam.cameraType === 'dynamic' ? 'bg-amber-400' : 'bg-teal-400'
                  }`}
                />
              </div>

              <span
                className={`absolute top-9 left-1/2 -translate-x-1/2 text-[10px] font-mono font-bold px-1.5 py-0.5 rounded whitespace-nowrap z-20 ${
                  isSelected
                    ? 'bg-sky-600 text-white shadow'
                    : 'bg-slate-900/95 text-slate-300 border border-slate-700'
                }`}
              >
                {cam.code}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const PERSIST = ['name', 'cameraType', 'panAngle', 'tiltAngle', 'zoomLevel', 'autoPatrol', 'rtsp_url', 'is_active', 'rulesVector', 'mapPos', 'zones'];
const snap = (c) => Object.fromEntries(PERSIST.map((k) => [k, JSON.stringify(c[k])]));

const NO_EVENT = { id: '—', violation_title: 'Событий пока нет', ai_pos: { x: 50, y: 50 }, camera_code: '—', description: '', confidence: 0, status: 'none' };

const INITIAL_CAMERAS_FALLBACK = [
  {
    id: 1,
    code: 'CAM-01',
    site_id: 10,
    site_name: 'Участок №1 — Сборочный цех (ОПО А-1)',
    name: 'Камера 01 • Линия конвейера',
    cameraType: 'dynamic',
    panAngle: 0,
    tiltAngle: 0,
    mapDirection: 125,
    zoomLevel: 1,
    autoPatrol: false,
    rtsp_url: 'rtsp://10.0.114.11:554/linq_stream_01',
    is_active: true,
    created_at: '2026-10-23 08:00:00',
    rulesVector: [0, 1, 1, 0, 1, 0, 1, 0, 1, 1, 1, 1, 1],
    fps: 96,
    latency: '11.2 мс',
    tpuProgram: 'yolov8m_safety_v2_int8.tpu',
    mapPos: { x: 24, y: 36 },
    workers: [
      { id: 'TRK-14', label: 'ID #14 • Сборщик', x: 32, y: 36, w: 12, h: 34, ppeOk: true },
      { id: 'TRK-22', label: 'ID #22 • Наладчик', x: 14, y: 46, w: 12, h: 34, ppeOk: true },
    ],
    zones: [
      {
        id: 'z-1',
        type: 'danger',
        shape: 'rect',
        label: 'Робот-манипулятор',
        schedule: 'Круглосуточно',
        rect: { x: 56, y: 34, w: 34, h: 48 },
      },
      {
        id: 'z-2',
        type: 'attention',
        shape: 'rect',
        label: 'Проход у конвейера',
        schedule: '08:00 – 20:00',
        rect: { x: 10, y: 42, w: 30, h: 42 },
      },
    ],
  },
  {
    id: 2,
    code: 'CAM-02',
    site_id: 20,
    site_name: 'Участок №2 — Склад и отгрузка (ОПО А-2)',
    name: 'Камера 02 • Зона погрузчиков',
    cameraType: 'static',
    panAngle: 0,
    tiltAngle: 0,
    mapDirection: -35,
    zoomLevel: 1,
    autoPatrol: false,
    rtsp_url: 'rtsp://10.0.114.12:554/linq_stream_02',
    is_active: true,
    created_at: '2026-10-23 08:05:00',
    rulesVector: [1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 1, 0, 0],
    fps: 94,
    latency: '11.8 мс',
    tpuProgram: 'yolov8m_safety_v2_int8.tpu',
    mapPos: { x: 52, y: 68 },
    workers: [
      { id: 'TRK-31', label: 'ID #31 • Кладовщик', x: 8, y: 42, w: 12, h: 34, ppeOk: true },
    ],
    zones: [
      {
        id: 'z-3',
        type: 'danger',
        shape: 'rect',
        label: 'Работа погрузчика',
        schedule: '07:55 – 12:00',
        rect: { x: 32, y: 38, w: 44, h: 46 },
      },
    ],
  },
  {
    id: 3,
    code: 'CAM-03',
    site_id: 30,
    site_name: 'Участок №3 — Окрасочная и ГСМ (ОПО Б-1)',
    name: 'Камера 03 • Хим. блок',
    cameraType: 'dynamic',
    panAngle: -15,
    tiltAngle: 0,
    mapDirection: 45,
    zoomLevel: 1,
    autoPatrol: false,
    rtsp_url: 'rtsp://10.0.114.13:554/linq_stream_03',
    is_active: true,
    created_at: '2026-10-23 08:10:00',
    rulesVector: [0, 0, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1],
    fps: 98,
    latency: '10.5 мс',
    tpuProgram: 'yolov8m_safety_v2_int8.tpu',
    mapPos: { x: 74, y: 46 },
    workers: [
      { id: 'TRK-08', label: 'ID #08 • Маляр', x: 40, y: 38, w: 12, h: 34, ppeOk: true },
    ],
    zones: [],
  },
];

const INITIAL_EVENTS_FALLBACK = [
  {
    id: 1042,
    camera_id: 1,
    camera_code: 'CAM-01',
    site_name: 'Участок №1 — Сборочный цех (ОПО А-1)',
    violation: 'PERSON_FALL',
    violation_title: 'Падение человека / неподвижность',
    pattern_code: '07',
    timestamp: '14:05:12',
    frame_url: '/archive/frames/evt_1042_crop.jpg',
    ai_map_url: '/archive/ai_maps/evt_1042_homography.png',
    ai_pos: { x: 28, y: 32 },
    status: 'new',
    processed_by_id: null,
    processed_by_name: 'Ожидает реакции',
    processed_at: null,
    confidence: 0.98,
    description: 'Сотрудник без движения у линии сборки',
    severity: 'critical',
  },
  {
    id: 1041,
    camera_id: 2,
    camera_code: 'CAM-02',
    site_name: 'Участок №2 — Склад и отгрузка (ОПО А-2)',
    violation: 'DANGER_PROXIMITY',
    violation_title: 'Опасное сближение с техникой',
    pattern_code: '02',
    timestamp: '13:52:40',
    frame_url: '/archive/frames/evt_1041_crop.jpg',
    ai_map_url: '/archive/ai_maps/evt_1041_homography.png',
    ai_pos: { x: 46, y: 64 },
    status: 'sent_to_master',
    processed_by_id: 2,
    processed_by_name: 'Соколов А.В.',
    processed_at: '13:52:55',
    confidence: 0.95,
    description: 'Передано мастеру смены Громову И.С., нарушение устранено',
    severity: 'warning',
  },
  {
    id: 1040,
    camera_id: 1,
    camera_code: 'CAM-01',
    site_name: 'Участок №1 — Сборочный цех (ОПО А-1)',
    violation: 'PHONE_USAGE',
    violation_title: 'Использование мобильного телефона',
    pattern_code: '03',
    timestamp: '13:18:05',
    frame_url: '/archive/frames/evt_1040_crop.jpg',
    ai_map_url: '/archive/ai_maps/evt_1040_homography.png',
    ai_pos: { x: 34, y: 44 },
    status: 'confirmed',
    processed_by_id: 1,
    processed_by_name: 'Кузьмин М.П.',
    processed_at: '13:20:10',
    confidence: 0.92,
    description: 'Зафиксировано в зоне особого внимания у конвейера',
    severity: 'warning',
  },
];

function Dashboard({ user: currentUser, initial, onLogout }) {
  const [isDark, setIsDark] = useState(true);
  const [eyeComfort, setEyeComfort] = useState(false);
  const [activeTab, setActiveTab] = useState('monitoring');
  const [showGostPreviewModal, setShowGostPreviewModal] = useState(false);
  const [inspectModalEvent, setInspectModalEvent] = useState(null);
  const [retrainStatus, setRetrainStatus] = useState(null);

  const [showHeatmap, setShowHeatmap] = useState(false);

  const [camMenuOpen, setCamMenuOpen] = useState(false);
  const [camSearchQuery, setCamSearchQuery] = useState('');

  const [mapZoom, setMapZoom] = useState(1);
  const [mapPan, setMapPan] = useState({ x: 0, y: 0 });
  const [isPanningMap, setIsPanningMap] = useState(false);
  const panStartRef = useRef(null);
  const [floorplanBgUrl, setFloorplanBgUrl] = useState(null);

  const [activeDbTable, setActiveDbTable] = useState('events');
  const [dbSearchQuery, setDbSearchQuery] = useState('');

  const [cameras, setCameras] = useState(
    (initial.cameras || INITIAL_CAMERAS_FALLBACK).map((c, idx) => ({
      ...c,
      mapDirection: c.mapDirection ?? [125, -35, 45][idx % 3],
    }))
  );
  const [selectedCamId, setSelectedCamId] = useState(initial.cameras?.[0]?.id || 1);
  const [events, setEvents] = useState(initial.events || INITIAL_EVENTS_FALLBACK);
  const [selectedEventId, setSelectedEventId] = useState(initial.events?.[0]?.id || 1042);
  const [filterStatus, setFilterStatus] = useState('all');

  const hasAiOnline = (initial.cameras || []).some((c) => c.ai?.online);
  const [videoSource, setVideoSource] = useState(hasAiOnline ? 'ai' : 'simulation');
  const [uploadState, setUploadState] = useState(null);
  const [webcamUnmirrored, setWebcamUnmirrored] = useState(true);
  const [uploadedVideoUrl, setUploadedVideoUrl] = useState(null);
  const webcamVideoRef = useRef(null);

  const [sirenEnabled, setSirenEnabled] = useState(initial.settings?.sirenEnabled ?? true);

  const [drawMode, setDrawMode] = useState('none');
  const [newZoneType, setNewZoneType] = useState('danger');
  const [newZoneLabel, setNewZoneLabel] = useState('Зона контроля');
  const [newZoneSchedule, setNewZoneSchedule] = useState('07:55 – 12:00');
  const [dragStart, setDragStart] = useState(null);
  const [dragCurrent, setDragCurrent] = useState(null);
  const [tempPolygon, setTempPolygon] = useState([]);

  const [activeZoneAction, setActiveZoneAction] = useState(null);
  const videoContainerRef = useRef(null);
  const worldSceneRef = useRef(null);

  const [draggingCamId, setDraggingCamId] = useState(null);
  const mapInnerRef = useRef(null);

  const [newSiteInput, setNewSiteInput] = useState('');
  const [newCamInput, setNewCamInput] = useState('');
  const [newCamTypeInput, setNewCamTypeInput] = useState('dynamic');
  const [newRtspInput, setNewRtspInput] = useState('');

  const activeCollisionKeyRef = useRef(null);

  const currentCamera = cameras.find((c) => c.id === selectedCamId) || cameras[0] || INITIAL_CAMERAS_FALLBACK[0];
  const activeEvent = events.find((e) => e.id === selectedEventId) || events[0] || NO_EVENT;
  const falseAlarmEvents = events.filter((e) => e.status === 'false_alarm');
  const confirmedEventsCount = events.filter((e) => e.status === 'confirmed' || e.status === 'sent_to_master').length;
  const aiMode = videoSource === 'ai';
  const camAi = currentCamera.ai || {};
  const aiOnlineCams = cameras.filter((c) => c.ai?.online);

  // Быстрые клавиши 1, 2, 3
  useEffect(() => {
    const onKeyDown = (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target?.tagName)) return;
      if (!activeEvent || activeEvent.id === '—') return;
      if (e.key === '1') handleProcessEvent(activeEvent.id, 'confirmed');
      if (e.key === '2') handleProcessEvent(activeEvent.id, 'sent_to_master');
      if (e.key === '3') handleProcessEvent(activeEvent.id, 'false_alarm');
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [activeEvent]);

  const collidingDangerWorker =
    aiMode && camAi.online
      ? null
      : (currentCamera.workers || []).find((w) => {
          const hitZone = checkWorkerZoneCollision(w, currentCamera.zones);
          return hitZone && hitZone.type === 'danger';
        });

  useEffect(() => {
    if (!collidingDangerWorker) {
      activeCollisionKeyRef.current = null;
      return;
    }
    const collisionKey = `${currentCamera.id}-${collidingDangerWorker.id}`;
    if (activeCollisionKeyRef.current === collisionKey) return;
    activeCollisionKeyRef.current = collisionKey;

    const vType = VIOLATION_TYPES[10];
    if (sirenEnabled) playSoftBeep();

    const posObj = {
      x: currentCamera.mapPos.x + Math.floor(Math.random() * 10 - 5),
      y: currentCamera.mapPos.y + Math.floor(Math.random() * 10 - 5),
    };

    api
      .createEvent({
        camera_id: currentCamera.id,
        violation: vType.enumKey,
        confidence: 0.96,
        ai_pos: posObj,
        description: `Пересечение опасной зоны объектом ${collidingDangerWorker.id} (${currentCamera.code})`,
      })
      .then((ev) => {
        setEvents((prev) => (prev.some((e) => e.id === ev.id) ? prev : [ev, ...prev]));
        setSelectedEventId(ev.id);
      })
      .catch(() => {
        const nextId = events.length > 0 ? Math.max(...events.map((e) => e.id)) + 1 : 1001;
        const localEvt = {
          id: nextId,
          camera_id: currentCamera.id,
          camera_code: currentCamera.code,
          site_name: currentCamera.site_name,
          violation: vType.enumKey,
          violation_title: vType.name,
          pattern_code: vType.code,
          timestamp: new Date().toLocaleTimeString(),
          frame_url: `/archive/frames/evt_${nextId}_crop.jpg`,
          ai_map_url: `/archive/ai_maps/evt_${nextId}_homography.png`,
          ai_pos: posObj,
          status: 'new',
          processed_by_id: null,
          processed_by_name: 'Ожидает реакции',
          processed_at: null,
          confidence: 0.96,
          description: `Пересечение опасной зоны объектом ${collidingDangerWorker.id} (${currentCamera.code})`,
          severity: 'warning',
        };
        setEvents((prev) => [localEvt, ...prev]);
        setSelectedEventId(nextId);
      });
  }, [collidingDangerWorker, currentCamera.id]);

  useEffect(() => {
    let stream = null;
    if (videoSource === 'webcam' && navigator.mediaDevices?.getUserMedia) {
      navigator.mediaDevices
        .getUserMedia({ video: true })
        .then((s) => {
          stream = s;
          if (webcamVideoRef.current) {
            webcamVideoRef.current.srcObject = s;
          }
        })
        .catch(() => {
          setVideoSource('simulation');
        });
    }
    return () => {
      if (stream) {
        stream.getTracks().forEach((t) => t.stop());
      }
    };
  }, [videoSource]);

  const getWorldCoords = (e) => {
    const targetEl = worldSceneRef.current || videoContainerRef.current;
    if (!targetEl) return { x: 0, y: 0 };
    const rect = targetEl.getBoundingClientRect();
    const x = Math.round(((e.clientX - rect.left) / rect.width) * 100);
    const y = Math.round(((e.clientY - rect.top) / rect.height) * 100);
    return { x, y };
  };

  const handleVideoMouseDown = (e) => {
    if (drawMode === 'rect') {
      const coords = getWorldCoords(e);
      setDragStart(coords);
      setDragCurrent(coords);
    } else if (drawMode === 'polygon') {
      const coords = getWorldCoords(e);
      setTempPolygon((prev) => sortPolygonPoints([...prev, coords]));
    }
  };

  const handleVideoMouseMove = (e) => {
    if (activeZoneAction) {
      const coords = getWorldCoords(e);
      const dx = coords.x - activeZoneAction.startX;
      const dy = coords.y - activeZoneAction.startY;

      setCameras((prev) =>
        prev.map((cam) => {
          if (cam.id !== selectedCamId) return cam;

          if (activeZoneAction.mode === 'move_worker') {
            return {
              ...cam,
              workers: (cam.workers || []).map((w) =>
                w.id === activeZoneAction.workerId
                  ? {
                      ...w,
                      x: Math.max(-35, Math.min(125, activeZoneAction.initialX + dx)),
                      y: Math.max(-35, Math.min(125, activeZoneAction.initialY + dy)),
                    }
                  : w
              ),
            };
          }

          return {
            ...cam,
            zones: cam.zones.map((z) => {
              if (z.id !== activeZoneAction.zoneId) return z;
              if (activeZoneAction.mode === 'move' && z.shape === 'rect') {
                const nextX = Math.max(-45, Math.min(135, activeZoneAction.initialRect.x + dx));
                const nextY = Math.max(-45, Math.min(135, activeZoneAction.initialRect.y + dy));
                return { ...z, rect: { ...z.rect, x: nextX, y: nextY } };
              }
              if (activeZoneAction.mode === 'resize' && z.shape === 'rect') {
                const nextW = Math.max(5, Math.min(130, activeZoneAction.initialRect.w + dx));
                const nextH = Math.max(5, Math.min(130, activeZoneAction.initialRect.h + dy));
                return { ...z, rect: { ...z.rect, w: nextW, h: nextH } };
              }
              if (activeZoneAction.mode === 'move_poly' && z.shape === 'polygon') {
                const movedPoints = activeZoneAction.initialPoints.map((pt) => ({
                  x: Math.max(-45, Math.min(145, pt.x + dx)),
                  y: Math.max(-45, Math.min(145, pt.y + dy)),
                }));
                return { ...z, points: movedPoints };
              }
              if (activeZoneAction.mode === 'move_vertex' && z.shape === 'polygon') {
                const updatedPts = z.points.map((pt, i) =>
                  i === activeZoneAction.vertexIdx
                    ? { x: Math.max(-40, Math.min(140, coords.x)), y: Math.max(-40, Math.min(140, coords.y)) }
                    : pt
                );
                return { ...z, points: sortPolygonPoints(updatedPts) };
              }
              return z;
            }),
          };
        })
      );
      return;
    }

    if (drawMode === 'rect' && dragStart) {
      setDragCurrent(getWorldCoords(e));
    }
  };

  const handleVideoMouseUp = () => {
    if (activeZoneAction) {
      setActiveZoneAction(null);
      return;
    }

    if (drawMode === 'rect' && dragStart && dragCurrent) {
      const x = Math.min(dragStart.x, dragCurrent.x);
      const y = Math.min(dragStart.y, dragCurrent.y);
      const w = Math.abs(dragCurrent.x - dragStart.x);
      const h = Math.abs(dragCurrent.y - dragStart.y);

      if (w > 3 && h > 3) {
        const defaultLabels = {
          danger: 'Опасная зона',
          attention: 'Особое внимание',
          blind: 'Слепая зона',
        };
        const newZone = {
          id: `z-${Date.now()}`,
          type: newZoneType,
          shape: 'rect',
          label: newZoneLabel.trim() || defaultLabels[newZoneType],
          schedule: newZoneSchedule,
          rect: { x, y, w, h },
        };
        setCameras((prev) =>
          prev.map((c) => (c.id === selectedCamId ? { ...c, zones: [...c.zones, newZone] } : c))
        );
      }
      setDragStart(null);
      setDragCurrent(null);
      setDrawMode('none');
    }
  };

  const finishPolygonZone = () => {
    if (tempPolygon.length >= 3) {
      const defaultLabels = {
        danger: 'Контур опасности',
        attention: 'Контур внимания',
        blind: 'Слепая зона',
      };
      const sortedPts = sortPolygonPoints(tempPolygon);
      const newZone = {
        id: `z-poly-${Date.now()}`,
        type: newZoneType,
        shape: 'polygon',
        label: newZoneLabel.trim() || defaultLabels[newZoneType],
        schedule: newZoneSchedule,
        points: sortedPts,
      };
      setCameras((prev) =>
        prev.map((c) => (c.id === selectedCamId ? { ...c, zones: [...c.zones, newZone] } : c))
      );
    }
    setTempPolygon([]);
    setDrawMode('none');
  };

  const removeZone = (zoneId) => {
    setCameras((prev) =>
      prev.map((c) =>
        c.id === selectedCamId ? { ...c, zones: c.zones.filter((z) => z.id !== zoneId) } : c
      )
    );
  };

  const toggleCameraType = (camId) => {
    setCameras((prev) =>
      prev.map((cam) =>
        cam.id === camId
          ? {
              ...cam,
              cameraType: cam.cameraType === 'static' ? 'dynamic' : 'static',
              autoPatrol: false,
            }
          : cam
      )
    );
  };

  const adjustCameraMapDirection = (newDir) => {
    setCameras((prev) =>
      prev.map((cam) =>
        cam.id === selectedCamId ? { ...cam, mapDirection: Number(newDir) } : cam
      )
    );
  };

  const handleAdjustMapZoom = (delta) => {
    setMapZoom((prev) => Number(Math.max(0.6, Math.min(3.0, prev + delta)).toFixed(2)));
  };

  const handleWheelMapZoom = (e) => {
    if (e.ctrlKey || e.metaKey || Math.abs(e.deltaY) > 0) {
      e.preventDefault();
      const delta = e.deltaY < 0 ? 0.15 : -0.15;
      handleAdjustMapZoom(delta);
    }
  };

  const handleMapContainerMouseDown = (e) => {
    if (e.button === 2) {
      e.preventDefault();
      setIsPanningMap(true);
      panStartRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        origX: mapPan.x,
        origY: mapPan.y,
      };
    }
  };

  const handleMapMouseMove = (e) => {
    if (panStartRef.current) {
      const dx = e.clientX - panStartRef.current.startX;
      const dy = e.clientY - panStartRef.current.startY;
      setMapPan({
        x: panStartRef.current.origX + dx,
        y: panStartRef.current.origY + dy,
      });
      return;
    }

    if (!draggingCamId || !mapInnerRef.current) return;
    const rect = mapInnerRef.current.getBoundingClientRect();
    const x = Math.round(((e.clientX - rect.left) / rect.width) * 100);
    const y = Math.round(((e.clientY - rect.top) / rect.height) * 100);

    setCameras((prev) =>
      prev.map((cam) => (cam.id === draggingCamId ? { ...cam, mapPos: { x, y } } : cam))
    );
  };

  const handleMapMouseUp = () => {
    panStartRef.current = null;
    setIsPanningMap(false);
    setDraggingCamId(null);
  };

  const commentTimer = useRef(null);
  const syncedRef = useRef(Object.fromEntries((initial.cameras || INITIAL_CAMERAS_FALLBACK).map((c) => [c.id, snap(c)])));
  const [statsHourly, setStatsHourly] = useState({});
  const firstSettingsRun = useRef(true);

  useEffect(() => {
    const t = setTimeout(() => {
      cameras.forEach((c) => {
        const prev = syncedRef.current[c.id];
        const cur = snap(c);
        const changed = PERSIST.filter((k) => !prev || prev[k] !== cur[k]);
        if (!prev || changed.length === 0) return;
        syncedRef.current[c.id] = cur;
        api.patchCamera(c.id, Object.fromEntries(changed.map((k) => [k, c[k]]))).catch(() => {});
      });
    }, 600);
    return () => clearTimeout(t);
  }, [cameras]);

  useEffect(() => {
    const t = setInterval(() => {
      api
        .events(0)
        .then((fresh) => {
          setEvents((prev) => {
            const local = Object.fromEntries(prev.map((e) => [e.id, e]));
            const maxId = prev.reduce((m, e) => Math.max(m, e.id), 0);
            const newest = fresh.find((f) => f.id > maxId);
            if (newest && sirenEnabled) {
              playSoftBeep();
            }
            const merged = fresh.map((f) => (local[f.id] ? { ...f, description: local[f.id].description } : f));
            const ids = new Set(merged.map((e) => e.id));
            return [...merged, ...prev.filter((e) => !ids.has(e.id))];
          });
        })
        .catch(() => {});
    }, 4000);
    return () => clearInterval(t);
  }, [sirenEnabled]);

  useEffect(() => {
    const LIVE = ['fps', 'latency', 'tpuProgram', 'ai'];
    const t = setInterval(() => {
      api
        .cameras()
        .then((list) => {
          const byId = Object.fromEntries(list.map((c) => [c.id, c]));
          setCameras((prev) => {
            const known = new Set(prev.map((c) => c.id));
            const next = prev.map((c) =>
              byId[c.id] ? { ...c, ...Object.fromEntries(LIVE.map((k) => [k, byId[c.id][k]])) } : c
            );
            const added = list.filter((c) => !known.has(c.id));
            added.forEach((c) => (syncedRef.current[c.id] = snap(c)));
            return [...next, ...added];
          });
        })
        .catch(() => {});
    }, 3000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    api
      .stats()
      .then((st) => setStatsHourly(Object.fromEntries(st.hourly.map((h) => [h.hour, h.count]))))
      .catch(() => {});
  }, [events.length]);
  const hourlyStats = HOURLY_STATS.map((h) => ({ ...h, count: statsHourly[h.hour] ?? h.count }));

  useEffect(() => {
    if (firstSettingsRun.current) {
      firstSettingsRun.current = false;
      return;
    }
    if (currentUser.canEditRules) {
      api.putSettings({ sirenEnabled }).catch(() => {});
    }
  }, [sirenEnabled, currentUser.canEditRules]);

  const handleAddCamera = (e) => {
    e.preventDefault();
    if (!currentUser.canEditRules) return;
    if (!newSiteInput.trim() || !newCamInput.trim()) return;
    const nextNum = cameras.length + 1;
    const offsetX = 22 + ((nextNum * 15) % 58);
    const offsetY = 26 + ((nextNum * 19) % 52);

    api
      .addCamera({
        name: newCamInput,
        site_name: newSiteInput,
        cameraType: newCamTypeInput,
        rtsp_url: newRtspInput.trim() || null,
        mapPos: { x: offsetX, y: offsetY },
        tpuProgram: 'yolov8m_safety_v2_int8.tpu',
        workers: [{ id: `TRK-${nextNum}1`, label: `ID #${nextNum}1 • Сотрудник`, x: 35, y: 40, w: 12, h: 34, ppeOk: true }],
      })
      .then((createdCam) => {
        syncedRef.current[createdCam.id] = snap(createdCam);
        setCameras((prev) => [...prev, { ...createdCam, mapDirection: 0 }]);
        setSelectedCamId(createdCam.id);
      })
      .catch(() => {
        const localCreatedCam = {
          id: Date.now(),
          code: `CAM-0${nextNum}`,
          site_id: nextNum * 10,
          site_name: newSiteInput,
          name: newCamInput,
          cameraType: newCamTypeInput,
          panAngle: 0,
          tiltAngle: 0,
          mapDirection: 0,
          zoomLevel: 1,
          autoPatrol: false,
          rtsp_url: newRtspInput.trim() || null,
          is_active: true,
          created_at: new Date().toISOString().slice(0, 19).replace('T', ' '),
          rulesVector: [0, 1, 1, 0, 1, 0, 1, 0, 1, 1, 1, 1, 1],
          fps: 96,
          latency: '11.0 мс',
          tpuProgram: 'yolov8m_safety_v2_int8.tpu',
          mapPos: { x: offsetX, y: offsetY },
          workers: [
            { id: `TRK-${nextNum}1`, label: `ID #${nextNum}1 • Сотрудник`, x: 35, y: 40, w: 12, h: 34, ppeOk: true },
          ],
          zones: [],
        };
        syncedRef.current[localCreatedCam.id] = snap(localCreatedCam);
        setCameras((prev) => [...prev, localCreatedCam]);
        setSelectedCamId(localCreatedCam.id);
      });

    setNewSiteInput('');
    setNewCamInput('');
    setNewRtspInput('');
  };

  const handleProcessEvent = (eventId, newStatus) => {
    const nowTime = new Date().toLocaleTimeString();
    api
      .processEvent(eventId, newStatus)
      .then((ev) => setEvents((prev) => prev.map((e) => (e.id === eventId ? ev : e))))
      .catch(() => {
        setEvents((prev) =>
          prev.map((e) =>
            e.id === eventId
              ? {
                  ...e,
                  status: newStatus,
                  processed_by_id: currentUser.id,
                  processed_by_name: currentUser.full_name,
                  processed_at: nowTime,
                }
              : e
          )
        );
      });
  };

  const toggleRule = (idx) => {
    if (!currentUser.canEditRules) return;
    setCameras((prev) =>
      prev.map((cam) => {
        if (cam.id !== selectedCamId) return cam;
        const nextVec = [...cam.rulesVector];
        nextVec[idx] = nextVec[idx] === 1 ? 0 : 1;
        return { ...cam, rulesVector: nextVec };
      })
    );
  };

  const applyRulesPreset = (presetType) => {
    if (!currentUser.canEditRules) return;
    const presets = {
      all: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
      ppe_only: [0, 0, 0, 0, 0, 0, 1, 0, 1, 1, 1, 1, 1],
      warehouse: [1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 0, 0],
    };
    const nextVec = presets[presetType] || presets.all;
    setCameras((prev) =>
      prev.map((cam) => (cam.id === selectedCamId ? { ...cam, rulesVector: nextVec } : cam))
    );
  };

  const handleExportEventsCsv = () => {
    const headers = ['id', 'camera_code', 'site_name', 'violation', 'timestamp', 'status', 'processed_by_name', 'confidence', 'description'];
    const rows = events.map((ev) =>
      headers.map((h) => `"${String(ev[h] ?? '').replace(/"/g, '""')}"`).join(';')
    );
    const csvContent = '\uFEFF' + [headers.join(';'), ...rows].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `linq_events_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleVideoFileUpload = (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (!currentUser.canEditRules) {
      setUploadedVideoUrl(URL.createObjectURL(file));
      setVideoSource('file');
      return;
    }
    setUploadState('uploading');
    api
      .uploadVideo(currentCamera.id, file)
      .then((cam) => {
        syncedRef.current[cam.id] = snap(cam);
        setCameras((prev) => prev.map((c) => (c.id === cam.id ? { ...c, rtsp_url: cam.rtsp_url } : c)));
        setVideoSource('ai');
        setUploadState(null);
      })
      .catch(() => {
        setUploadedVideoUrl(URL.createObjectURL(file));
        setVideoSource('file');
        setUploadState(null);
      });
  };

  const handleFloorplanUpload = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setFloorplanBgUrl(URL.createObjectURL(file));
    }
  };

  const handleTriggerRetrain = () => {
    setRetrainStatus('running');
    api
      .downloadFalseAlarms()
      .then(() => setRetrainStatus('done'))
      .catch(() => {
        setTimeout(() => setRetrainStatus('done'), 1000);
      });
  };

  const filteredEvents = events.filter((e) =>
    filterStatus === 'all' ? true : e.status === filterStatus
  );

  // Спокойная цветовая палитра
  const themePage = isDark
    ? 'bg-[#0D131F] text-slate-100'
    : 'bg-[#F5F7FA] text-slate-800';
  const themeCard = isDark
    ? 'bg-[#151E2E] border-slate-800/90 text-slate-100'
    : 'bg-white border-slate-200/90 text-slate-800 shadow-2xs';
  const themeSubCard = isDark
    ? 'bg-[#0F1726] border-slate-800 text-slate-200'
    : 'bg-slate-50 border-slate-200/90 text-slate-800';
  const themeTableHead = isDark
    ? 'bg-slate-800/75 text-slate-200 border-b border-slate-700'
    : 'bg-slate-100 text-slate-700 border-b border-slate-200';
  const themeTableWrap = isDark
    ? 'border-slate-800 divide-slate-800/80'
    : 'border-slate-200 divide-slate-200';
  const textMuted = isDark ? 'text-slate-400' : 'text-slate-500';

  const zoneColors = {
    danger: {
      border: '#F43F5E',
      bg: 'rgba(244, 63, 94, 0.18)',
      badge: 'bg-rose-600 text-white',
      name: 'Опасная зона',
    },
    attention: {
      border: '#F59E0B',
      bg: 'rgba(245, 158, 11, 0.18)',
      badge: 'bg-amber-500 text-slate-950',
      name: 'Особое внимание',
    },
    blind: {
      border: '#64748B',
      bg: 'rgba(100, 116, 139, 0.25)',
      badge: 'bg-slate-600 text-white',
      name: 'Слепая зона',
    },
  };

  const currentCamIdx = cameras.findIndex((c) => c.id === currentCamera.id);
  const goPrevCam = () => {
    const prevIdx = (currentCamIdx - 1 + cameras.length) % cameras.length;
    setSelectedCamId(cameras[prevIdx].id);
  };
  const goNextCam = () => {
    const nextIdx = (currentCamIdx + 1) % cameras.length;
    setSelectedCamId(cameras[nextIdx].id);
  };

  return (
    <>
      <div className="hidden print:block bg-white text-black">
        <GostRostechnadzorReport
          hourly={hourlyStats}
          cameras={cameras}
          events={events}
          currentUser={currentUser}
        />
      </div>

      {/* МОДАЛЬНОЕ ОКНО: ПРЕДПРОСМОТР ОТЧЕТА РОСТЕХНАДЗОРА № 518 */}
      {showGostPreviewModal && (
        <div className="print:hidden fixed inset-0 bg-black/75 backdrop-blur-xs z-50 flex flex-col items-center justify-start overflow-y-auto p-6">
          <div className="max-w-[210mm] w-full bg-slate-900 text-white px-5 py-3 rounded-t-2xl flex items-center justify-between border-b border-slate-700">
            <div className="flex items-center gap-2 text-xs font-semibold">
              <FileText size={16} className="text-sky-400" />
              <span>
                Форма Ростехнадзора (Приказ от 11.12.2020 № 518 • ГОСТ Р 7.0.97-2016)
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => window.print()}
                className="px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold cursor-pointer flex items-center gap-1.5"
              >
                <FileDown size={14} /> Печать / PDF
              </button>
              <button
                onClick={() => setShowGostPreviewModal(false)}
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold cursor-pointer"
              >
                Закрыть
              </button>
            </div>
          </div>
          <div className="max-w-[210mm] w-full shadow-2xl rounded-b-2xl overflow-hidden">
            <GostRostechnadzorReport
              hourly={hourlyStats}
              cameras={cameras}
              events={events}
              currentUser={currentUser}
            />
          </div>
        </div>
      )}

      {/* МОДАЛЬНОЕ ОКНО: РАЗБОР СТОП-КАДРА И ВИДЕОКЛИПА */}
      {inspectModalEvent && (
        <div className="print:hidden fixed inset-0 bg-black/75 backdrop-blur-xs z-50 flex items-center justify-center p-4 overflow-y-auto">
          <div className={`max-w-4xl w-full rounded-2xl border p-6 shadow-2xl ${themeCard}`}>
            <div className="flex items-center justify-between pb-3 border-b border-inherit">
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-0.5 rounded bg-slate-700 text-white text-xs font-bold">
                  Акт фиксации #{inspectModalEvent.id}
                </span>
                <span className="text-sm font-bold">{inspectModalEvent.violation_title}</span>
              </div>
              <button
                onClick={() => setInspectModalEvent(null)}
                className="px-2.5 py-1 rounded-lg bg-slate-500/20 hover:bg-slate-500/30 text-xs font-semibold cursor-pointer"
              >
                Закрыть
              </button>
            </div>

            {(inspectModalEvent.frame_url || inspectModalEvent.clip_url) && (
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <p className={`text-[11px] font-semibold ${textMuted}`}>Стоп-кадр с разметкой ИИ</p>
                  {inspectModalEvent.frame_url ? (
                    <a href={inspectModalEvent.frame_url} target="_blank" rel="noreferrer">
                      <img src={inspectModalEvent.frame_url} alt="Кадр нарушения" className="w-full rounded-xl border border-slate-700" />
                    </a>
                  ) : (
                    <div className="h-40 rounded-xl border border-slate-700 bg-slate-950" />
                  )}
                </div>
                <div className="space-y-1">
                  <p className={`text-[11px] font-semibold ${textMuted}`}>
                    Видеоклип {inspectModalEvent.clip_url ? '' : '— формируется по окончании события'}
                  </p>
                  {inspectModalEvent.clip_url ? (
                    <video src={inspectModalEvent.clip_url} controls autoPlay muted loop className="w-full rounded-xl border border-slate-700 bg-black" />
                  ) : (
                    <div className="h-40 rounded-xl border border-dashed border-slate-600 bg-slate-950 flex items-center justify-center text-[11px] text-slate-400">
                      Запись фрагмента…
                    </div>
                  )}
                </div>
              </div>
            )}

            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
              {inspectModalEvent.ai_map_url ? (
                <div className="space-y-1">
                  <p className={`text-[11px] font-semibold ${textMuted}`}>ИИ-карта участка в момент нарушения</p>
                  <img src={inspectModalEvent.ai_map_url} alt="Миникарта" className="w-full max-h-64 object-contain rounded-xl border border-slate-700 bg-white" />
                </div>
              ) : (
                <div className="bg-slate-950 rounded-xl h-52 relative overflow-hidden border border-slate-700 flex items-center justify-center">
                  <div
                    className="absolute inset-0 opacity-20"
                    style={{
                      backgroundImage:
                        'linear-gradient(to right, #38bdf8 1px, transparent 1px), linear-gradient(to bottom, #38bdf8 1px, transparent 1px)',
                      backgroundSize: '28px 28px',
                    }}
                  />
                  <div className="w-28 h-36 border-2 border-amber-500 bg-amber-500/15 rounded relative">
                    <span className="absolute -top-5 left-0 bg-amber-500 text-slate-950 text-[10px] font-bold px-1.5 py-0.5 rounded whitespace-nowrap">
                      {inspectModalEvent.violation} ({Math.round(inspectModalEvent.confidence * 100)}%)
                    </span>
                  </div>
                </div>
              )}

              <div className="space-y-2 text-xs flex flex-col justify-between">
                <div className={`p-3 rounded-xl border space-y-1.5 ${themeSubCard}`}>
                  <p><span className={textMuted}>Участок:</span> <strong>{inspectModalEvent.site_name}</strong></p>
                  <p><span className={textMuted}>Камера:</span> <strong>{inspectModalEvent.camera_code}</strong></p>
                  <p><span className={textMuted}>Время:</span> <strong>{inspectModalEvent.timestamp}</strong></p>
                  <p><span className={textMuted}>Достоверность LinQ TPU:</span> <strong>{Math.round(inspectModalEvent.confidence * 100)}%</strong></p>
                  <p><span className={textMuted}>Ответственный:</span> <strong>{inspectModalEvent.processed_by_name}</strong></p>
                </div>

                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      handleProcessEvent(inspectModalEvent.id, 'confirmed');
                      setInspectModalEvent(null);
                    }}
                    className="flex-1 py-2 rounded-xl bg-teal-600 hover:bg-teal-500 text-white font-semibold cursor-pointer"
                  >
                    Подтвердить
                  </button>
                  <button
                    onClick={() => {
                      handleProcessEvent(inspectModalEvent.id, 'false_alarm');
                      setInspectModalEvent(null);
                    }}
                    className="flex-1 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-semibold cursor-pointer"
                  >
                    Ложное (В дообучение)
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ================= ПОЛНОЭКРАННЫЙ КАРКАС САЙТА ================= */}
      <div
        className={`print:hidden min-h-screen flex flex-col transition-colors duration-300 ${themePage} ${
          eyeComfort ? 'sepia-[.18] saturate-[.85] contrast-[.96]' : ''
        }`}
      >
        {/* ШАПКА НА 5 ВКЛАДОК */}
        <header
          className={`border-b px-5 py-2.5 flex flex-wrap items-center justify-between gap-4 sticky top-0 z-40 backdrop-blur-md ${themeCard}`}
        >
          <div className="flex items-center gap-3.5">
            <LinQExactLogo isDark={isDark} />
            <div className={`h-8 w-[1px] hidden sm:block ${isDark ? 'bg-slate-700' : 'bg-slate-300'}`} />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold tracking-tight">Vision Guard</span>
                <span
                  className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${
                    aiOnlineCams.length > 0
                      ? 'bg-teal-500/15 text-teal-400 border-teal-500/30'
                      : 'bg-sky-500/15 text-sky-400 border-sky-500/30'
                  }`}
                >
                  {aiOnlineCams.length > 0
                    ? `LinQ TPU • ${aiOnlineCams.length}/${cameras.length} онлайн`
                    : `LinQ TPU • ${currentCamera.fps} FPS`}
                </span>
              </div>
              <p className={`text-[11px] ${textMuted}`}>
                {currentUser.full_name} ({currentUser.position})
              </p>
            </div>
          </div>

          <nav className="flex flex-wrap items-center gap-1.5">
            {[
              { id: 'monitoring', label: 'Видеоконтроль', icon: Video },
              { id: 'multiview', label: 'Мультиэкран', icon: LayoutGrid, badge: cameras.length },
              { id: 'map_rules', label: 'Карта и Правила', icon: Map },
              { id: 'analytics', label: 'Аналитика и ГОСТ', icon: BarChart3 },
              { id: 'db_inspector', label: 'СУБД', icon: Database },
            ].map((tab) => {
              const Icon = tab.icon;
              const active = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition cursor-pointer ${
                    active
                      ? 'bg-sky-600 text-white shadow-xs'
                      : `${themeSubCard} border hover:border-slate-500`
                  }`}
                >
                  <Icon size={15} />
                  <span>{tab.label}</span>
                  {tab.badge && (
                    <span
                      className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                        active ? 'bg-white/20 text-white' : 'bg-slate-500/15 text-slate-400'
                      }`}
                    >
                      {tab.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          <div className="flex items-center gap-2">
            <IconTipButton
              icon={Eye}
              label={eyeComfort ? 'Защита зрения: ВКЛ' : 'Защита зрения 24/7'}
              active={eyeComfort}
              onClick={() => setEyeComfort(!eyeComfort)}
              isDark={isDark}
              align="right"
            />

            <IconTipButton
              icon={isDark ? Sun : Moon}
              label={isDark ? 'Светлая тема' : 'Темная тема'}
              active={false}
              onClick={() => setIsDark(!isDark)}
              isDark={isDark}
              align="right"
            />

            <IconTipButton
              icon={LogOut}
              label="Сменить пользователя / Выйти"
              active={false}
              onClick={onLogout}
              isDark={isDark}
              align="right"
            />
          </div>
        </header>

        <main className="flex-1 flex flex-col p-5">
          {/* ================= ВКЛАДКА 1: ВИДЕОКОНТРОЛЬ ================= */}
          {activeTab === 'monitoring' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 lg:h-[calc(100vh-105px)] min-h-[580px] items-stretch">
              {/* ЛЕВАЯ ЧАСТЬ (8 из 12): Убрано overflow-hidden с внешней карточки, чтобы всплывающие подсказки у правого края никогда не обрезались! */}
              <div className={`lg:col-span-8 border rounded-2xl flex flex-col h-full min-h-0 ${themeCard}`}>
                <div className="p-3 border-b border-inherit flex flex-wrap items-center justify-between gap-3 shrink-0">
                  <div className="flex items-center gap-2 relative">
                    <button
                      type="button"
                      onClick={goPrevCam}
                      className={`p-2 rounded-xl border cursor-pointer ${themeSubCard} hover:border-slate-500`}
                      title="Предыдущая камера"
                    >
                      <ChevronLeft size={15} />
                    </button>

                    {/* Выпадающее меню выбора камеры */}
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setCamMenuOpen(!camMenuOpen)}
                        className={`px-3.5 py-2 rounded-xl text-xs font-bold border flex items-center gap-2.5 cursor-pointer ${themeSubCard} hover:border-sky-500/60`}
                      >
                        <span className="w-2 h-2 rounded-full bg-teal-400" />
                        <span>{currentCamera.code}</span>
                        <span className={`font-normal truncate max-w-[200px] ${textMuted}`}>
                          {currentCamera.site_name}
                        </span>
                        <span className="px-1.5 py-0.5 rounded bg-slate-500/15 text-[10px] font-mono">
                          {currentCamIdx + 1}/{cameras.length}
                        </span>
                        <ChevronDown size={14} className={textMuted} />
                      </button>

                      {camMenuOpen && (
                        <div
                          className={`absolute left-0 top-11 w-80 rounded-2xl border p-2.5 shadow-2xl z-50 ${themeCard}`}
                        >
                          <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl border text-xs mb-2 ${themeSubCard}`}>
                            <Search size={13} className={textMuted} />
                            <input
                              type="text"
                              value={camSearchQuery}
                              onChange={(e) => setCamSearchQuery(e.target.value)}
                              placeholder="Поиск камеры или участка..."
                              className="bg-transparent focus:outline-none w-full"
                            />
                          </div>
                          <div className="max-h-64 overflow-y-auto space-y-1">
                            {cameras
                              .filter((c) =>
                                !camSearchQuery.trim()
                                  ? true
                                  : `${c.code} ${c.name} ${c.site_name}`
                                      .toLowerCase()
                                      .includes(camSearchQuery.toLowerCase())
                              )
                              .map((cam) => {
                                const active = cam.id === selectedCamId;
                                return (
                                  <button
                                    key={cam.id}
                                    type="button"
                                    onClick={() => {
                                      setSelectedCamId(cam.id);
                                      setCamMenuOpen(false);
                                    }}
                                    className={`w-full text-left px-3 py-2 rounded-xl text-xs flex items-center justify-between cursor-pointer transition ${
                                      active
                                        ? 'bg-sky-600 text-white font-bold'
                                        : 'hover:bg-slate-500/10'
                                    }`}
                                  >
                                    <div className="truncate pr-2">
                                      <span className="font-mono font-bold mr-2">{cam.code}</span>
                                      <span className={active ? 'text-white/90' : textMuted}>
                                        {cam.site_name}
                                      </span>
                                    </div>
                                    <span className="text-[10px] font-mono shrink-0">
                                      {cam.fps} FPS
                                    </span>
                                  </button>
                                );
                              })}
                          </div>
                        </div>
                      )}
                    </div>

                    <button
                      type="button"
                      onClick={goNextCam}
                      className={`p-2 rounded-xl border cursor-pointer ${themeSubCard} hover:border-slate-500`}
                      title="Следующая камера"
                    >
                      <ChevronRight size={15} />
                    </button>
                  </div>

                  {/* Панель инструментов (Подсказки выровнены по правому краю align="right", чтобы не пропадать за границей карточки!) */}
                  <div className="flex items-center gap-1.5">
                    <IconTipButton
                      icon={Square}
                      label="Выделить прямоугольную зону"
                      active={drawMode === 'rect'}
                      onClick={() => {
                        setTempPolygon([]);
                        setDrawMode(drawMode === 'rect' ? 'none' : 'rect');
                      }}
                      isDark={isDark}
                    />
                    <IconTipButton
                      icon={Pentagon}
                      label={
                        drawMode === 'polygon'
                          ? `Сохранить контур (${tempPolygon.length} тчк)`
                          : 'Нарисовать контур по точкам'
                      }
                      active={drawMode === 'polygon'}
                      badge={drawMode === 'polygon' ? tempPolygon.length : 0}
                      onClick={() => {
                        if (drawMode === 'polygon') {
                          finishPolygonZone();
                        } else {
                          setTempPolygon([]);
                          setDrawMode('polygon');
                        }
                      }}
                      isDark={isDark}
                    />
                    <IconTipButton
                      icon={Flame}
                      label="Тепловая карта рисков"
                      active={showHeatmap}
                      onClick={() => setShowHeatmap(!showHeatmap)}
                      isDark={isDark}
                      align="right"
                    />
                    <IconTipButton
                      icon={Camera}
                      label="Веб-камера"
                      active={videoSource === 'webcam'}
                      onClick={() =>
                        setVideoSource(videoSource === 'webcam' ? 'simulation' : 'webcam')
                      }
                      isDark={isDark}
                      align="right"
                    />
                    {videoSource === 'webcam' && (
                      <IconTipButton
                        icon={FlipHorizontal}
                        label={webcamUnmirrored ? 'Прямой вид камеры' : 'Зеркальный вид'}
                        active={webcamUnmirrored}
                        onClick={() => setWebcamUnmirrored(!webcamUnmirrored)}
                        isDark={isDark}
                        align="right"
                      />
                    )}
                    <label
                      className={`group relative flex items-center justify-center w-9 h-9 rounded-xl border transition-all cursor-pointer shrink-0 ${
                        isDark
                          ? 'bg-slate-800/90 text-slate-300 border-slate-700 hover:border-slate-500 hover:text-white'
                          : 'bg-white text-slate-700 border-slate-200 hover:border-slate-400 hover:text-slate-900 shadow-2xs'
                      }`}
                    >
                      <Upload size={16} />
                      <input
                        type="file"
                        accept="video/*"
                        onChange={handleVideoFileUpload}
                        className="hidden"
                      />
                      <span className="pointer-events-none absolute -bottom-9 right-0 px-2.5 py-1 rounded-md bg-slate-950 text-white text-[11px] font-medium whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-50 shadow-lg border border-slate-700">
                        Загрузить видеофайл (.mp4)
                      </span>
                    </label>
                  </div>
                </div>

                {drawMode !== 'none' && (
                  <div className="px-4 py-2 bg-sky-500/10 border-b border-sky-500/30 flex flex-wrap items-center justify-between gap-2 text-xs shrink-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-bold text-sky-400">Новая зона:</span>
                      <select
                        value={newZoneType}
                        onChange={(e) => setNewZoneType(e.target.value)}
                        className={`rounded-lg px-2.5 py-1 border font-medium ${themeCard}`}
                      >
                        <option value="danger">🔴 Опасная зона</option>
                        <option value="attention">🟡 Особое внимание</option>
                        <option value="blind">⚪ Слепая зона</option>
                      </select>
                      <input
                        type="text"
                        value={newZoneLabel}
                        onChange={(e) => setNewZoneLabel(e.target.value)}
                        placeholder="Название зоны..."
                        className={`rounded-lg px-2.5 py-1 border w-40 ${themeCard}`}
                      />
                      <select
                        value={newZoneSchedule}
                        onChange={(e) => setNewZoneSchedule(e.target.value)}
                        className={`rounded-lg px-2 py-1 border ${themeCard}`}
                      >
                        <option value="Круглосуточно">24/7 Постоянно</option>
                        <option value="07:55 – 12:00">07:55 – 12:00</option>
                        <option value="08:00 – 20:00">08:00 – 20:00</option>
                      </select>
                    </div>
                    <div className="flex items-center gap-2">
                      {drawMode === 'polygon' && tempPolygon.length >= 3 && (
                        <button
                          onClick={finishPolygonZone}
                          className="px-3 py-1 rounded-lg bg-teal-600 text-white font-semibold cursor-pointer"
                        >
                          Готово ({tempPolygon.length} тчк)
                        </button>
                      )}
                      <button
                        onClick={() => {
                          setDrawMode('none');
                          setTempPolygon([]);
                        }}
                        className="px-2.5 py-1 rounded-lg bg-slate-500/20 font-medium cursor-pointer"
                      >
                        Отмена
                      </button>
                    </div>
                  </div>
                )}

                {/* ВИДЕОЭКРАН */}
                <div
                  ref={videoContainerRef}
                  onMouseDown={handleVideoMouseDown}
                  onMouseMove={handleVideoMouseMove}
                  onMouseUp={handleVideoMouseUp}
                  onMouseLeave={handleVideoMouseUp}
                  className={`relative bg-[#090D16] overflow-hidden select-none flex-1 min-h-0 ${
                    drawMode !== 'none' ? 'cursor-crosshair ring-2 ring-sky-500' : ''
                  }`}
                >
                  <div ref={worldSceneRef} className="absolute inset-0 w-full h-full">
                    {aiMode && camAi.online && camAi.stream_url && (
                      <img
                        key={`${currentCamera.id}-${currentCamera.rtsp_url}`}
                        src={camAi.stream_url}
                        alt="Видеопоток ИИ"
                        draggable={false}
                        className="absolute inset-0 w-full h-full object-fill pointer-events-none"
                      />
                    )}

                    {videoSource === 'webcam' && (
                      <video
                        ref={webcamVideoRef}
                        autoPlay
                        playsInline
                        muted
                        style={{
                          transform: webcamUnmirrored ? 'scaleX(-1)' : 'scaleX(1)',
                        }}
                        className="absolute inset-0 w-full h-full object-cover"
                      />
                    )}

                    {videoSource === 'file' && uploadedVideoUrl && (
                      <video
                        src={uploadedVideoUrl}
                        autoPlay
                        loop
                        muted
                        className="absolute inset-0 w-full h-full object-cover"
                      />
                    )}

                    <div
                      className={`absolute -inset-[100%] w-[300%] h-[300%] pointer-events-none ${
                        aiMode && camAi.online ? 'opacity-0' : 'opacity-15'
                      }`}
                      style={{
                        backgroundImage:
                          'linear-gradient(to right, #94a3b8 1px, transparent 1px), linear-gradient(to bottom, #94a3b8 1px, transparent 1px)',
                        backgroundSize: '48px 48px',
                      }}
                    />

                    {showHeatmap && (
                      <div className="absolute inset-0 pointer-events-none z-15">
                        <div
                          className="absolute w-72 h-72 rounded-full blur-2xl opacity-60"
                          style={{
                            left: '50%',
                            top: '30%',
                            background:
                              'radial-gradient(circle, rgba(244,63,94,0.75) 0%, rgba(245,158,11,0.45) 45%, transparent 75%)',
                          }}
                        />
                      </div>
                    )}

                    {currentCamera.zones
                      .filter((z) => z.shape === 'rect')
                      .map((zone) => {
                        const st = zoneColors[zone.type] || zoneColors.danger;
                        const badgePositionClass =
                          zone.rect.y < 9 ? '-bottom-6 left-0' : '-top-6 left-0';

                        return (
                          <div
                            key={zone.id}
                            style={{
                              left: `${zone.rect.x}%`,
                              top: `${zone.rect.y}%`,
                              width: `${zone.rect.w}%`,
                              height: `${zone.rect.h}%`,
                              borderColor: st.border,
                              backgroundColor: st.bg,
                            }}
                            onMouseDown={(e) => {
                              if (drawMode !== 'none') return;
                              e.stopPropagation();
                              const coords = getWorldCoords(e);
                              setActiveZoneAction({
                                mode: 'move',
                                zoneId: zone.id,
                                startX: coords.x,
                                startY: coords.y,
                                initialRect: { ...zone.rect },
                              });
                            }}
                            className="absolute border-2 rounded-md cursor-move group hover:ring-1 hover:ring-white/70 z-20"
                          >
                            <div
                              className={`absolute ${badgePositionClass} flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-950/90 border border-white/20 shadow-md whitespace-nowrap z-30`}
                            >
                              <span
                                className="w-2 h-2 rounded-full shrink-0"
                                style={{ backgroundColor: st.border }}
                              />
                              <span className="text-[10px] font-semibold text-white">
                                {zone.label}
                              </span>
                              <button
                                onMouseDown={(e) => e.stopPropagation()}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  removeZone(zone.id);
                                }}
                                className="text-slate-300 hover:text-rose-400 ml-0.5 cursor-pointer"
                              >
                                <Trash2 size={10} />
                              </button>
                            </div>

                            <div
                              onMouseDown={(e) => {
                                e.stopPropagation();
                                const coords = getWorldCoords(e);
                                setActiveZoneAction({
                                  mode: 'resize',
                                  zoneId: zone.id,
                                  startX: coords.x,
                                  startY: coords.y,
                                  initialRect: { ...zone.rect },
                                });
                              }}
                              className="absolute -bottom-1.5 -right-1.5 w-3 h-3 bg-white border-2 border-sky-600 rounded-xs cursor-nwse-resize pointer-events-auto shadow hover:scale-125 transition-transform"
                            />
                          </div>
                        );
                      })}

                    {drawMode === 'rect' && dragStart && dragCurrent && (
                      <div
                        style={{
                          left: `${Math.min(dragStart.x, dragCurrent.x)}%`,
                          top: `${Math.min(dragStart.y, dragCurrent.y)}%`,
                          width: `${Math.abs(dragCurrent.x - dragStart.x)}%`,
                          height: `${Math.abs(dragCurrent.y - dragStart.y)}%`,
                          borderColor: zoneColors[newZoneType].border,
                          backgroundColor: zoneColors[newZoneType].bg,
                        }}
                        className="absolute border-2 border-dashed rounded-md pointer-events-none z-20"
                      />
                    )}

                    <svg
                      viewBox="0 0 100 100"
                      preserveAspectRatio="none"
                      className="absolute inset-0 w-full h-full overflow-visible pointer-events-none z-10"
                    >
                      {currentCamera.zones
                        .filter((z) => z.shape === 'polygon' && z.points?.length >= 3)
                        .map((zone) => {
                          const st = zoneColors[zone.type] || zoneColors.danger;
                          const orderedPts = sortPolygonPoints(zone.points);
                          const ptsString = orderedPts
                            .map((p) => `${p.x},${p.y}`)
                            .join(' ');
                          return (
                            <polygon
                              key={zone.id}
                              points={ptsString}
                              fill={st.bg}
                              stroke={st.border}
                              strokeWidth="2"
                              vectorEffect="non-scaling-stroke"
                            />
                          );
                        })}

                      {tempPolygon.length >= 2 && (
                        <polygon
                          points={sortPolygonPoints(tempPolygon)
                            .map((p) => `${p.x},${p.y}`)
                            .join(' ')}
                          fill={zoneColors[newZoneType].bg}
                          stroke="#38bdf8"
                          strokeWidth="2"
                          strokeDasharray="5 4"
                          vectorEffect="non-scaling-stroke"
                        />
                      )}
                    </svg>

                    {tempPolygon.map((p, i) => (
                      <div
                        key={i}
                        style={{ left: `${p.x}%`, top: `${p.y}%` }}
                        className="absolute -translate-x-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-sky-400 border-2 border-slate-950 pointer-events-none z-20 shadow"
                      />
                    ))}

                    {currentCamera.zones
                      .filter((z) => z.shape === 'polygon' && z.points?.length >= 3)
                      .map((zone) => {
                        const st = zoneColors[zone.type] || zoneColors.danger;
                        const topVertex = zone.points.reduce(
                          (minPt, pt) => (pt.y < minPt.y ? pt : minPt),
                          zone.points[0]
                        );

                        return (
                          <React.Fragment key={`poly-ui-${zone.id}`}>
                            {zone.points.map((pt, idx) => (
                              <div
                                key={idx}
                                style={{
                                  left: `${pt.x}%`,
                                  top: `${pt.y}%`,
                                  borderColor: st.border,
                                }}
                                onMouseDown={(e) => {
                                  if (drawMode !== 'none') return;
                                  e.stopPropagation();
                                  const coords = getWorldCoords(e);
                                  setActiveZoneAction({
                                    mode: 'move_vertex',
                                    zoneId: zone.id,
                                    vertexIdx: idx,
                                    startX: coords.x,
                                    startY: coords.y,
                                  });
                                }}
                                className="absolute -translate-x-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-white border-2 cursor-pointer hover:scale-125 transition-transform z-30 shadow"
                              />
                            ))}

                            <div
                              style={{
                                left: `${topVertex.x}%`,
                                top: `${topVertex.y}%`,
                              }}
                              onMouseDown={(e) => {
                                if (drawMode !== 'none') return;
                                e.stopPropagation();
                                const coords = getWorldCoords(e);
                                setActiveZoneAction({
                                  mode: 'move_poly',
                                  zoneId: zone.id,
                                  startX: coords.x,
                                  startY: coords.y,
                                  initialPoints: zone.points.map((pt) => ({ ...pt })),
                                });
                              }}
                              className="absolute -translate-x-1/2 -translate-y-full -mt-1.5 flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-950/90 border border-white/25 cursor-move z-30 shadow-md whitespace-nowrap"
                            >
                              <span
                                className="w-2 h-2 rounded-full shrink-0"
                                style={{ backgroundColor: st.border }}
                              />
                              <span className="text-[10px] font-semibold text-white">
                                {zone.label}
                              </span>
                              <button
                                onMouseDown={(e) => e.stopPropagation()}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  removeZone(zone.id);
                                }}
                                className="text-slate-300 hover:text-rose-400 ml-0.5 cursor-pointer"
                              >
                                <Trash2 size={10} />
                              </button>
                            </div>
                          </React.Fragment>
                        );
                      })}

                    {(!aiMode || !camAi.online) &&
                      (currentCamera.workers || []).map((worker) => {
                        const hitZone = checkWorkerZoneCollision(worker, currentCamera.zones);
                        const isDanger = hitZone?.type === 'danger';
                        const isAttention = hitZone?.type === 'attention';

                        return (
                          <div
                            key={worker.id}
                            style={{
                              left: `${worker.x}%`,
                              top: `${worker.y}%`,
                              width: `${worker.w}%`,
                              height: `${worker.h}%`,
                            }}
                            onMouseDown={(e) => {
                              if (drawMode !== 'none') return;
                              e.stopPropagation();
                              const coords = getWorldCoords(e);
                              setActiveZoneAction({
                                mode: 'move_worker',
                                workerId: worker.id,
                                startX: coords.x,
                                startY: coords.y,
                                initialX: worker.x,
                                initialY: worker.y,
                              });
                            }}
                            className={`absolute border-2 rounded-md cursor-grab active:cursor-grabbing z-25 transition-colors ${
                              isDanger
                                ? 'border-rose-500 bg-rose-500/20'
                                : isAttention
                                ? 'border-amber-400 bg-amber-400/15'
                                : 'border-teal-400 bg-teal-500/10'
                            }`}
                          >
                            <div
                              className={`absolute -top-5 left-0 text-white text-[10px] font-semibold px-1.5 py-0.5 rounded whitespace-nowrap shadow ${
                                isDanger
                                  ? 'bg-rose-600'
                                  : isAttention
                                  ? 'bg-amber-500 text-slate-950'
                                  : 'bg-teal-600'
                              }`}
                            >
                              {isDanger
                                ? `${worker.id} • Опасная зона`
                                : isAttention
                                ? `${worker.id} • Контроль СИЗ`
                                : `${worker.label} • Норма`}
                            </div>
                          </div>
                        );
                      })}
                  </div>

                  <div className="absolute bottom-3 left-3 flex flex-wrap items-center gap-2 pointer-events-none z-30">
                    <span className="px-2.5 py-1 rounded-lg bg-slate-950/85 border border-slate-700 text-[11px] font-mono text-slate-200">
                      {currentCamera.code} • {currentCamera.fps} FPS • {currentCamera.latency}
                    </span>
                  </div>
                </div>

                {/* Нижняя полоса под камерой */}
                <div className="px-4 py-2.5 border-t border-inherit flex flex-wrap items-center justify-between gap-3 text-xs shrink-0 rounded-b-2xl">
                  <label className="flex items-center gap-1.5 cursor-pointer font-medium">
                    <input
                      type="checkbox"
                      checked={sirenEnabled}
                      onChange={(e) => setSirenEnabled(e.target.checked)}
                    />
                    <Volume2 size={14} className="text-amber-500" />
                    <span>Сирена в цеху</span>
                  </label>

                  <div className="flex items-center gap-2 flex-1 max-w-md mx-2">
                    <span className={`text-[10px] font-mono ${textMuted}`}>08:00</span>
                    <div className={`relative flex-1 h-2 rounded-full flex items-center ${isDark ? 'bg-slate-800' : 'bg-slate-200'}`}>
                      {events.slice(0, 8).map((ev, idx) => {
                        const pos = 15 + ((idx * 17) % 75);
                        return (
                          <button
                            key={ev.id}
                            onClick={() => setSelectedEventId(ev.id)}
                            style={{ left: `${pos}%` }}
                            title={`${ev.timestamp} — ${ev.violation_title}`}
                            className={`absolute -translate-x-1/2 w-2.5 h-2.5 rounded-full border border-white cursor-pointer transition-transform hover:scale-125 ${
                              ev.severity === 'critical' ? 'bg-rose-500' : 'bg-amber-400'
                            }`}
                          />
                        );
                      })}
                    </div>
                    <span className={`text-[10px] font-mono ${textMuted}`}>LIVE</span>
                  </div>

                  <button
                    onClick={() => toggleCameraType(currentCamera.id)}
                    className={`text-[11px] font-semibold px-2.5 py-1 rounded-lg border cursor-pointer ${themeSubCard}`}
                  >
                    Привод: {currentCamera.cameraType === 'dynamic' ? 'Динамичная PTZ' : 'Статичная'}
                  </button>
                </div>
              </div>

              {/* ПРАВАЯ ЧАСТЬ (4 из 12): Лента событий с внутренним скроллом */}
              <div
                className={`lg:col-span-4 border rounded-2xl flex flex-col h-full min-h-0 overflow-hidden ${themeCard}`}
              >
                <div className="p-3.5 border-b border-inherit flex items-center justify-between gap-2 shrink-0">
                  <div>
                    <h2 className="text-sm font-bold flex items-center gap-2">
                      <span>Лента событий</span>
                      <span className="text-[11px] px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-500 font-semibold">
                        {events.filter((e) => e.status === 'new').length} новых
                      </span>
                    </h2>
                    <p className={`text-[11px] flex items-center gap-1 mt-0.5 ${textMuted}`}>
                      <Keyboard size={11} /> Клавиши: [1] Подтв. [2] Мастеру [3] Ложное
                    </p>
                  </div>
                  <select
                    value={filterStatus}
                    onChange={(e) => setFilterStatus(e.target.value)}
                    className={`text-xs rounded-xl px-2.5 py-1.5 border font-medium ${themeSubCard}`}
                  >
                    <option value="all">Все ({events.length})</option>
                    <option value="new">Новые</option>
                    <option value="confirmed">Подтверждено</option>
                    <option value="sent_to_master">У мастера</option>
                    <option value="false_alarm">Ложные ({falseAlarmEvents.length})</option>
                  </select>
                </div>

                <div className="p-3 space-y-2.5 overflow-y-auto flex-1 min-h-0">
                  {filteredEvents.map((ev) => {
                    const isSelected = ev.id === selectedEventId;
                    const isCritical = ev.severity === 'critical' || ev.violation === 'PERSON_FALL';
                    return (
                      <div
                        key={ev.id}
                        onClick={() => setSelectedEventId(ev.id)}
                        className={`p-3 rounded-xl border transition cursor-pointer ${
                          isSelected
                            ? 'ring-1 ring-sky-500/80 border-sky-500/80'
                            : `${themeSubCard} hover:border-slate-500`
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <div className="flex items-center gap-1.5">
                              <span
                                className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                                  isCritical
                                    ? 'bg-rose-500/20 text-rose-500 border border-rose-500/30'
                                    : 'bg-amber-500/20 text-amber-600 dark:text-amber-300 border border-amber-500/30'
                                }`}
                              >
                                Паттерн {ev.pattern_code}
                              </span>
                              <span className={`text-xs font-mono ${textMuted}`}>
                                #{ev.id} • {ev.camera_code}
                              </span>
                            </div>
                            <h3 className="text-xs font-bold mt-1">{ev.violation_title}</h3>
                          </div>
                          <span className={`text-xs font-mono font-semibold ${textMuted}`}>
                            {ev.timestamp}
                          </span>
                        </div>

                        <p className={`text-[11px] mt-1 ${textMuted}`}>{ev.description}</p>

                        <div
                          className={`mt-2.5 pt-2 border-t flex items-center justify-between gap-1 ${
                            isDark ? 'border-slate-800' : 'border-slate-200'
                          }`}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => handleProcessEvent(ev.id, 'confirmed')}
                              className={`px-2.5 py-1 rounded-lg text-[11px] font-medium border flex items-center gap-1 cursor-pointer transition ${
                                ev.status === 'confirmed'
                                  ? 'bg-teal-600 text-white border-teal-600'
                                  : `${themeCard} hover:border-teal-500/60`
                              }`}
                            >
                              <CheckCircle2 size={12} />
                              <span>Подтв.</span>
                            </button>
                            <button
                              onClick={() => handleProcessEvent(ev.id, 'sent_to_master')}
                              className={`px-2.5 py-1 rounded-lg text-[11px] font-medium border flex items-center gap-1 cursor-pointer transition ${
                                ev.status === 'sent_to_master'
                                  ? 'bg-sky-600 text-white border-sky-600'
                                  : `${themeCard} hover:border-sky-500/60`
                              }`}
                            >
                              <Send size={12} />
                              <span>Мастеру</span>
                            </button>
                            <button
                              onClick={() => handleProcessEvent(ev.id, 'false_alarm')}
                              className={`px-2.5 py-1 rounded-lg text-[11px] font-medium border flex items-center gap-1 cursor-pointer transition ${
                                ev.status === 'false_alarm'
                                  ? 'bg-rose-600 text-white border-rose-600'
                                  : `${themeCard} text-rose-500 hover:border-rose-500/60`
                              }`}
                            >
                              <XCircle size={12} />
                              <span>Ложное</span>
                            </button>
                          </div>

                          <button
                            onClick={() => setInspectModalEvent(ev)}
                            title="Открыть стоп-кадр и видеоклип"
                            className="p-1.5 rounded-lg text-sky-500 hover:bg-sky-500/10 cursor-pointer"
                          >
                            <Maximize2 size={13} />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* ================= ВКЛАДКА 2: МУЛЬТИЭКРАН ================= */}
          {activeTab === 'multiview' && (
            <div className={`flex-1 border rounded-2xl p-5 flex flex-col min-h-[calc(100vh-110px)] ${themeCard}`}>
              <div className="flex items-center justify-between mb-4 shrink-0">
                <h2 className="text-sm font-bold flex items-center gap-2">
                  <Layers size={16} className="text-sky-400" />
                  Видеостена мониторинга ({cameras.length})
                </h2>
                <span className="text-xs font-mono px-2.5 py-1 rounded-lg bg-slate-500/15 font-semibold">
                  Суммарно: {cameras.reduce((a, c) => a + (c.fps || 95), 0)} FPS
                </span>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 flex-1">
                {cameras.map((cam) => (
                  <div
                    key={cam.id}
                    onClick={() => {
                      setSelectedCamId(cam.id);
                      setActiveTab('monitoring');
                    }}
                    className={`p-5 rounded-2xl border cursor-pointer transition flex flex-col justify-between aspect-video min-h-[380px] relative overflow-hidden bg-[#090D16] text-white ${
                      selectedCamId === cam.id ? 'ring-2 ring-sky-500 border-sky-500' : 'border-slate-800 hover:border-slate-600'
                    }`}
                  >
                    {cam.ai?.online && cam.ai?.stream_url && (
                      <img
                        src={cam.ai.stream_url}
                        alt={cam.name}
                        className="absolute inset-0 w-full h-full object-contain pointer-events-none"
                      />
                    )}

                    <div
                      className="absolute inset-0 opacity-15 pointer-events-none"
                      style={{
                        backgroundImage:
                          'linear-gradient(to right, #64748b 1px, transparent 1px), linear-gradient(to bottom, #64748b 1px, transparent 1px)',
                        backgroundSize: '36px 36px',
                      }}
                    />

                    <div className="relative z-10 flex items-center justify-between">
                      <span className="text-xs font-bold px-3 py-1 rounded-lg bg-slate-900/90 border border-slate-700">
                        {cam.code}
                      </span>
                      <span className="text-xs font-mono px-2.5 py-1 rounded-lg bg-slate-900/90 text-teal-400 border border-slate-800">
                        {cam.fps} FPS • {cam.cameraType === 'dynamic' ? 'PTZ' : 'Стат.'}
                      </span>
                    </div>

                    {!(cam.ai?.online && cam.ai?.stream_url) && (
                      <div className="relative z-10 my-auto text-center">
                        <Video size={36} className="mx-auto text-slate-500 mb-2.5" />
                        <p className="text-base font-bold">{cam.name}</p>
                        <p className="text-xs text-slate-400 mt-1">{cam.site_name}</p>
                      </div>
                    )}

                    <div className="relative z-10 flex items-center justify-between text-xs text-slate-300 bg-slate-950/80 backdrop-blur-xs px-3.5 py-2 rounded-xl border border-slate-800/90">
                      <span>Зон контроля: {cam.zones.length} • Правил активно: {cam.rulesVector.filter(Boolean).length}</span>
                      <span className="text-sky-400 font-semibold">Открыть камеру →</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ================= ВКЛАДКА 3: КАРТА И ПРАВИЛА ================= */}
          {activeTab === 'map_rules' && (
            <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch min-h-[calc(100vh-110px)]">
              <div className={`lg:col-span-7 border rounded-2xl p-5 flex flex-col justify-between ${themeCard}`}>
                <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-inherit shrink-0">
                  <h2 className="text-sm font-bold flex items-center gap-2">
                    <Map size={16} className="text-sky-400" />
                    Интерактивная карта цеха
                  </h2>

                  <div className="flex flex-wrap items-center gap-2">
                    <div className={`flex items-center gap-1 px-2 py-1 rounded-xl border text-xs ${themeSubCard}`}>
                      <button
                        type="button"
                        onClick={() => handleAdjustMapZoom(-0.2)}
                        className="p-1 hover:text-sky-400 cursor-pointer"
                        title="Отдалить карту"
                      >
                        <ZoomOut size={14} />
                      </button>
                      <span className="font-mono font-bold px-1.5 min-w-[44px] text-center">
                        {Math.round(mapZoom * 100)}%
                      </span>
                      <button
                        type="button"
                        onClick={() => handleAdjustMapZoom(0.2)}
                        className="p-1 hover:text-sky-400 cursor-pointer"
                        title="Приблизить карту"
                      >
                        <ZoomIn size={14} />
                      </button>
                      {(mapZoom !== 1 || mapPan.x !== 0 || mapPan.y !== 0) && (
                        <button
                          type="button"
                          onClick={() => {
                            setMapZoom(1);
                            setMapPan({ x: 0, y: 0 });
                          }}
                          className="p-1 hover:text-amber-400 cursor-pointer"
                          title="Сбросить масштаб и позицию"
                        >
                          <RotateCcw size={13} />
                        </button>
                      )}
                    </div>

                    <div className={`flex items-center gap-2 px-3 py-1 rounded-xl border text-xs ${themeSubCard}`}>
                      <Compass size={14} className="text-sky-400" />
                      <span>Азимут {currentCamera.code}:</span>
                      <input
                        type="range"
                        min="-180"
                        max="180"
                        value={currentCamera.mapDirection || 0}
                        onChange={(e) => adjustCameraMapDirection(e.target.value)}
                        className="w-20 accent-sky-500 cursor-pointer"
                      />
                      <span className="font-mono font-bold w-9 text-right">
                        {(currentCamera.mapDirection || 0) + (currentCamera.panAngle || 0)}°
                      </span>
                    </div>

                    <label className={`px-3 py-1 rounded-xl text-xs font-semibold border flex items-center gap-1.5 cursor-pointer ${themeSubCard}`}>
                      <ImageIcon size={13} className="text-sky-400" />
                      <span>Чертеж</span>
                      <input
                        type="file"
                        accept="image/*"
                        onChange={handleFloorplanUpload}
                        className="hidden"
                      />
                    </label>

                    <button
                      onClick={() => setShowHeatmap(!showHeatmap)}
                      className={`px-3 py-1 rounded-xl text-xs font-semibold border flex items-center gap-1.5 cursor-pointer ${
                        showHeatmap ? 'bg-amber-600 text-white border-amber-600' : themeSubCard
                      }`}
                    >
                      <Flame size={13} /> Тепловая карта
                    </button>
                  </div>
                </div>

                <div className="mt-4 flex-1 flex flex-col">
                  <UnifiedWorkshopMap
                    cameras={cameras}
                    selectedCamId={selectedCamId}
                    onSelectCam={setSelectedCamId}
                    onDoubleClickCam={(camId) => {
                      setSelectedCamId(camId);
                      setActiveTab('monitoring');
                    }}
                    onDragCamStart={setDraggingCamId}
                    events={events}
                    activeEvent={activeEvent}
                    onSelectEvent={setSelectedEventId}
                    showHeatmap={showHeatmap}
                    floorplanBgUrl={floorplanBgUrl}
                    mapZoom={mapZoom}
                    mapPan={mapPan}
                    isPanningMap={isPanningMap}
                    onMapMouseDown={handleMapContainerMouseDown}
                    onWheelZoom={handleWheelMapZoom}
                    mapInnerRef={mapInnerRef}
                    onMouseMove={handleMapMouseMove}
                    onMouseUp={handleMapMouseUp}
                    minHeightClass="min-h-[560px]"
                  />
                </div>
              </div>

              {/* ПРАВАЯ КОЛОНКА (5 из 12): Правила контроля + Регистрация новой камеры и участка */}
              <div
                className={`lg:col-span-5 border rounded-2xl p-5 flex flex-col justify-between gap-5 ${themeCard}`}
              >
                <div>
                  <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-inherit">
                    <h2 className="text-sm font-bold">
                      Правила контроля: {currentCamera.code}
                    </h2>
                    <span className="text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-slate-500/15 text-sky-500">
                      Активно: {currentCamera.rulesVector.filter(Boolean).length}/{VIOLATION_TYPES.length}
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5 mt-3">
                    <span className={`text-[11px] mr-1 ${textMuted}`}>Пресеты:</span>
                    <button
                      onClick={() => applyRulesPreset('all')}
                      className={`text-[11px] px-2.5 py-1 rounded-lg border font-medium cursor-pointer ${themeSubCard} hover:border-slate-500`}
                    >
                      Все детекторы
                    </button>
                    <button
                      onClick={() => applyRulesPreset('ppe_only')}
                      className={`text-[11px] px-2.5 py-1 rounded-lg border font-medium cursor-pointer ${themeSubCard} hover:border-slate-500`}
                    >
                      СИЗ и падения
                    </button>
                    <button
                      onClick={() => applyRulesPreset('warehouse')}
                      className={`text-[11px] px-2.5 py-1 rounded-lg border font-medium cursor-pointer ${themeSubCard} hover:border-slate-500`}
                    >
                      Склад и техника
                    </button>
                  </div>

                  <div className="mt-3 grid grid-cols-1 xl:grid-cols-2 gap-2">
                    {VIOLATION_TYPES.map((v, idx) => {
                      const active = currentCamera.rulesVector[idx] === 1;
                      return (
                        <div
                          key={v.id}
                          onClick={() => toggleRule(idx)}
                          className={`px-2.5 py-2 rounded-xl border flex items-center justify-between gap-2 cursor-pointer transition ${
                            active
                              ? 'border-sky-500/60 bg-sky-500/10'
                              : `${themeSubCard} opacity-60 hover:opacity-90`
                          }`}
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-slate-700 text-slate-200 shrink-0">
                              {v.code}
                            </span>
                            <span className="text-[11px] font-medium truncate" title={v.name}>
                              {v.name}
                            </span>
                          </div>
                          <span
                            className={`text-[10px] font-bold px-2 py-0.5 rounded-md shrink-0 ${
                              active
                                ? 'bg-teal-600 text-white'
                                : isDark
                                ? 'bg-slate-800 text-slate-400'
                                : 'bg-slate-200 text-slate-600'
                            }`}
                          >
                            {active ? 'ВКЛ' : 'ВЫКЛ'}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="pt-4 border-t border-inherit">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-xs font-bold uppercase tracking-wider flex items-center gap-1.5">
                      <Plus size={14} className="text-sky-400" />
                      Регистрация новой камеры и участка
                    </h3>
                    {!currentUser.canEditRules && (
                      <span className="text-xs text-rose-500 font-medium flex items-center gap-1">
                        <Lock size={12} /> Только для ОТ / ИТ
                      </span>
                    )}
                  </div>

                  <form
                    onSubmit={handleAddCamera}
                    className="grid grid-cols-1 sm:grid-cols-2 gap-3"
                  >
                    <input
                      type="text"
                      disabled={!currentUser.canEditRules}
                      placeholder="Наименование участка"
                      value={newSiteInput}
                      onChange={(e) => setNewSiteInput(e.target.value)}
                      className={`text-xs rounded-xl px-3.5 py-2.5 border ${themeSubCard}`}
                    />
                    <input
                      type="text"
                      disabled={!currentUser.canEditRules}
                      placeholder="Наименование камеры"
                      value={newCamInput}
                      onChange={(e) => setNewCamInput(e.target.value)}
                      className={`text-xs rounded-xl px-3.5 py-2.5 border ${themeSubCard}`}
                    />
                    <input
                      type="text"
                      disabled={!currentUser.canEditRules}
                      placeholder="Адрес потока (rtsp://…)"
                      value={newRtspInput}
                      onChange={(e) => setNewRtspInput(e.target.value)}
                      className={`text-xs rounded-xl px-3.5 py-2.5 border ${themeSubCard}`}
                    />
                    <select
                      disabled={!currentUser.canEditRules}
                      value={newCamTypeInput}
                      onChange={(e) => setNewCamTypeInput(e.target.value)}
                      className={`text-xs rounded-xl px-3.5 py-2.5 border font-medium ${themeSubCard}`}
                    >
                      <option value="dynamic">Динамичная PTZ</option>
                      <option value="static">Статичная</option>
                    </select>
                    <button
                      type="submit"
                      disabled={!currentUser.canEditRules}
                      className="sm:col-span-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white font-semibold text-xs rounded-xl py-2.5 px-4 cursor-pointer transition"
                    >
                      + Добавить камеру на карту цеха
                    </button>
                  </form>
                </div>
              </div>
            </div>
          )}

          {/* ================= ВКЛАДКА 4: АНАЛИТИКА И ГОСТ ================= */}
          {activeTab === 'analytics' && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className={`border rounded-2xl p-4 ${themeCard}`}>
                  <p className={`text-xs ${textMuted}`}>Скорость обработки LinQ TPU</p>
                  <p className="text-xl font-bold mt-1">{currentCamera.fps} FPS</p>
                  <p className={`text-[11px] mt-0.5 ${textMuted}`}>Отклик: {currentCamera.latency}</p>
                </div>
                <div className={`border rounded-2xl p-4 ${themeCard}`}>
                  <p className={`text-xs ${textMuted}`}>Всего событий в базе</p>
                  <p className="text-xl font-bold mt-1">{events.length}</p>
                  <p className={`text-[11px] mt-0.5 ${textMuted}`}>Подтверждено ОТ: {confirmedEventsCount}</p>
                </div>
                <div className={`border rounded-2xl p-4 ${themeCard}`}>
                  <p className={`text-xs ${textMuted}`}>Выборка Active Learning</p>
                  <p className="text-xl font-bold text-teal-500 mt-1">{falseAlarmEvents.length} кадров</p>
                  <p className={`text-[11px] mt-0.5 ${textMuted}`}>Отмеченные ложные срабатывания</p>
                </div>
              </div>

              <div className={`border rounded-2xl p-5 space-y-4 ${themeCard}`}>
                <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-inherit">
                  <div>
                    <h2 className="text-sm font-bold">
                      Динамика нарушений по часам смены
                    </h2>
                    <p className={`text-xs ${textMuted}`}>
                      Отчетность по Приказу Ростехнадзора от 11.12.2020 № 518
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      onClick={() => setShowGostPreviewModal(true)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold cursor-pointer ${themeSubCard}`}
                    >
                      <FileText size={14} className="text-sky-500" /> Форма № 518
                    </button>
                    <button
                      onClick={() => window.print()}
                      className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold cursor-pointer shadow-xs"
                    >
                      <FileDown size={14} /> Скачать PDF (ГОСТ)
                    </button>
                  </div>
                </div>

                {/* Все цифры над столбцами имеют единый стандартный читаемый цвет на светлой и темной теме! */}
                <div className="grid grid-cols-7 gap-4 pt-2">
                  {hourlyStats.map((item, i) => {
                    const heightPct = Math.round((item.count / 15) * 100);
                    const isPeak = item.count >= 11;
                    return (
                      <div key={i} className="flex flex-col items-center">
                        <div
                          className={`h-40 w-full flex flex-col justify-end items-center border-b pb-2 ${
                            isDark ? 'border-slate-800' : 'border-slate-200'
                          }`}
                        >
                          <span
                            className={`text-xs font-mono font-bold px-2 py-0.5 rounded-md mb-1.5 border ${
                              isDark
                                ? 'bg-slate-800 text-slate-100 border-slate-700'
                                : 'bg-slate-100 text-slate-800 border-slate-200'
                            }`}
                          >
                            {item.count}
                          </span>
                          <div
                            style={{ height: `${heightPct}%` }}
                            className={`w-11 max-w-full rounded-t-lg transition-all ${
                              isPeak ? 'bg-amber-500/85' : 'bg-sky-600/80'
                            }`}
                          />
                        </div>
                        <p className="text-xs font-bold mt-2 text-center">{item.hour}</p>
                        <p className={`text-[11px] text-center leading-tight mt-0.5 ${textMuted}`}>
                          {item.label}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className={`border rounded-2xl p-4 flex flex-wrap items-center justify-between gap-4 ${themeCard}`}>
                <div>
                  <h3 className="text-sm font-bold flex items-center gap-2">
                    <RefreshCw size={16} className="text-sky-500" />
                    Контур дообучения нейросети (Active Learning)
                  </h3>
                  <p className={`text-xs mt-0.5 ${textMuted}`}>
                    Отмеченные кнопкой «Ложное» кадры ({falseAlarmEvents.length} шт.) выгружаются в архив для дообучения модели
                  </p>
                </div>
                <button
                  onClick={handleTriggerRetrain}
                  className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold cursor-pointer flex items-center gap-1.5"
                >
                  <RefreshCw size={14} className={retrainStatus === 'running' ? 'animate-spin' : ''} />
                  {retrainStatus === 'running'
                    ? 'Сборка архива…'
                    : retrainStatus === 'done'
                    ? 'Архив linq_false_alarms.zip готов'
                    : 'Выгрузить выборку для дообучения'}
                </button>
              </div>

              <div className={`border rounded-2xl p-5 ${themeCard}`}>
                <h3 className="text-sm font-bold mb-3">
                  Сводная ведомость по производственным участкам
                </h3>
                <div className={`rounded-xl border overflow-hidden ${themeTableWrap}`}>
                  <table className="w-full text-left text-xs">
                    <thead className={themeTableHead}>
                      <tr>
                        <th className="p-3">Производственный участок</th>
                        <th className="p-3">Камера</th>
                        <th className="p-3">Частое нарушение</th>
                        <th className="p-3">Инцидентов</th>
                        <th className="p-3">Подтверждено ОТ</th>
                        <th className="p-3">Точность ИИ</th>
                      </tr>
                    </thead>
                    <tbody className={`divide-y ${themeTableWrap}`}>
                      {cameraSummary(cameras, events).map((r) => (
                        <tr key={r.id} className="hover:bg-slate-500/5">
                          <td className="p-3 font-semibold">{r.site}</td>
                          <td className="p-3 font-mono">{r.code}</td>
                          <td className="p-3 font-medium">{r.top || '—'}</td>
                          <td className="p-3 font-bold">{r.total}</td>
                          <td className="p-3">{r.confirmed}</td>
                          <td className="p-3 text-teal-500 font-bold">
                            {r.reviewed > 0 ? `${Math.round((r.confirmed / r.reviewed) * 100)}%` : '95%'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ================= ВКЛАДКА 5: СУБД ================= */}
          {activeTab === 'db_inspector' && (
            <div className={`border rounded-2xl p-5 flex-1 flex flex-col space-y-5 min-h-[calc(100vh-110px)] ${themeCard}`}>
              <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-inherit shrink-0">
                <h2 className="text-base font-bold flex items-center gap-2">
                  <Database size={18} className="text-sky-500" />
                  Инспектор реляционной СУБД PostgreSQL
                </h2>

                <div className="flex flex-wrap items-center gap-2">
                  <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs ${themeSubCard}`}>
                    <Search size={13} className={textMuted} />
                    <input
                      type="text"
                      value={dbSearchQuery}
                      onChange={(e) => setDbSearchQuery(e.target.value)}
                      placeholder="Фильтр записей..."
                      className="bg-transparent focus:outline-none w-40"
                    />
                  </div>
                  <button
                    onClick={handleExportEventsCsv}
                    className="px-3 py-1.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold flex items-center gap-1.5 cursor-pointer"
                  >
                    <Download size={13} /> Выгрузить CSV
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 shrink-0">
                {[
                  { id: 'events', table: 'events', pk: 'id (PK), camera_id (FK)', count: `${events.length} записей` },
                  { id: 'cameras', table: 'cameras', pk: 'id (PK), site_id (FK)', count: `${cameras.length} камеры` },
                  { id: 'sites', table: 'sites', pk: 'id (PK), rules (JSONB)', count: `${new Set(cameras.map((c) => c.site_id)).size} участка` },
                  { id: 'users', table: 'users', pk: 'id (PK), role_id (FK)', count: `${DB_USERS.length} сотрудника` },
                  { id: 'roles', table: 'roles', pk: 'id (PK), name (UK)', count: `${DB_ROLES.length} роли` },
                ].map((tb) => {
                  const isSelected = activeDbTable === tb.id;
                  return (
                    <div
                      key={tb.id}
                      onClick={() => setActiveDbTable(tb.id)}
                      className={`p-3.5 rounded-xl border cursor-pointer transition flex flex-col justify-between ${
                        isSelected
                          ? 'border-sky-500 bg-sky-500/10'
                          : `${themeSubCard} hover:border-slate-500`
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xs font-bold text-sky-500">
                          {tb.table}
                        </span>
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-slate-500/15">
                          {tb.count}
                        </span>
                      </div>
                      <p className={`text-[11px] font-mono mt-2 ${textMuted}`}>{tb.pk}</p>
                    </div>
                  );
                })}
              </div>

              <div className="flex-1 flex flex-col">
                <h3 className="text-xs font-bold uppercase tracking-wider mb-2.5">
                  SELECT * FROM public.{activeDbTable} ORDER BY id DESC;
                </h3>

                <div className={`flex-1 rounded-xl border overflow-x-auto ${themeTableWrap}`}>
                  {activeDbTable === 'events' && (
                    <table className="w-full text-left text-xs font-mono">
                      <thead className={themeTableHead}>
                        <tr>
                          <th className="p-3.5">id (PK)</th>
                          <th className="p-3.5">camera_id (FK)</th>
                          <th className="p-3.5">violation (enum)</th>
                          <th className="p-3.5">timestamp</th>
                          <th className="p-3.5">status</th>
                          <th className="p-3.5">processed_by</th>
                          <th className="p-3.5">confidence</th>
                          <th className="p-3.5">description</th>
                        </tr>
                      </thead>
                      <tbody className={`divide-y ${themeTableWrap}`}>
                        {events
                          .filter((ev) =>
                            !dbSearchQuery.trim()
                              ? true
                              : JSON.stringify(ev).toLowerCase().includes(dbSearchQuery.toLowerCase())
                          )
                          .map((ev) => (
                            <tr key={ev.id} className="hover:bg-slate-500/5">
                              <td className="p-3.5 font-bold">{ev.id}</td>
                              <td className="p-3.5">{ev.camera_id} ({ev.camera_code})</td>
                              <td className="p-3.5 font-semibold text-amber-500">{ev.violation}</td>
                              <td className="p-3.5 whitespace-nowrap">{ev.timestamp}</td>
                              <td className="p-3.5 font-semibold">{ev.status}</td>
                              <td className="p-3.5">{ev.processed_by_name}</td>
                              <td className="p-3.5 text-teal-500 font-bold">{ev.confidence}</td>
                              <td className="p-3.5">{ev.description}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  )}

                  {activeDbTable === 'cameras' && (
                    <table className="w-full text-left text-xs font-mono">
                      <thead className={themeTableHead}>
                        <tr>
                          <th className="p-3.5">id (PK)</th>
                          <th className="p-3.5">code</th>
                          <th className="p-3.5">site_id (FK)</th>
                          <th className="p-3.5">name</th>
                          <th className="p-3.5">camera_type</th>
                          <th className="p-3.5">rtsp_url</th>
                          <th className="p-3.5">fps</th>
                        </tr>
                      </thead>
                      <tbody className={`divide-y ${themeTableWrap}`}>
                        {cameras.map((c) => (
                          <tr key={c.id} className="hover:bg-slate-500/5">
                            <td className="p-3.5 font-bold">{c.id}</td>
                            <td className="p-3.5 text-sky-500 font-bold">{c.code}</td>
                            <td className="p-3.5">{c.site_id}</td>
                            <td className="p-3.5">{c.name}</td>
                            <td className="p-3.5">{c.cameraType}</td>
                            <td className={`p-3.5 ${textMuted}`}>{c.rtsp_url || '—'}</td>
                            <td className="p-3.5 text-teal-500 font-bold">{c.fps}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}

                  {activeDbTable === 'sites' && (
                    <table className="w-full text-left text-xs font-mono">
                      <thead className={themeTableHead}>
                        <tr>
                          <th className="p-3.5">id (PK)</th>
                          <th className="p-3.5">name</th>
                          <th className="p-3.5">rules (JSONB)</th>
                          <th className="p-3.5">created_at</th>
                        </tr>
                      </thead>
                      <tbody className={`divide-y ${themeTableWrap}`}>
                        {cameras.map((c) => (
                          <tr key={c.id} className="hover:bg-slate-500/5">
                            <td className="p-3.5 font-bold">{c.site_id}</td>
                            <td className="p-3.5 font-semibold">{c.site_name}</td>
                            <td className="p-3.5 text-sky-500">
                              vector: [{c.rulesVector.join(', ')}], zones: {c.zones.length}
                            </td>
                            <td className="p-3.5">{c.created_at}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}

                  {activeDbTable === 'users' && (
                    <table className="w-full text-left text-xs font-mono">
                      <thead className={themeTableHead}>
                        <tr>
                          <th className="p-3.5">id (PK)</th>
                          <th className="p-3.5">login (UK)</th>
                          <th className="p-3.5">full_name</th>
                          <th className="p-3.5">role_id (FK)</th>
                          <th className="p-3.5">can_edit_rules</th>
                        </tr>
                      </thead>
                      <tbody className={`divide-y ${themeTableWrap}`}>
                        {DB_USERS.map((u) => (
                          <tr key={u.id} className="hover:bg-slate-500/5">
                            <td className="p-3.5 font-bold">{u.id}</td>
                            <td className="p-3.5 text-sky-500">{u.login}</td>
                            <td className="p-3.5">{u.full_name} ({u.position})</td>
                            <td className="p-3.5">{u.role_id} ({u.role_name})</td>
                            <td className="p-3.5 text-teal-500 font-bold">{String(u.canEditRules)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}

                  {activeDbTable === 'roles' && (
                    <table className="w-full text-left text-xs font-mono">
                      <thead className={themeTableHead}>
                        <tr>
                          <th className="p-3.5">id (PK)</th>
                          <th className="p-3.5">name</th>
                        </tr>
                      </thead>
                      <tbody className={`divide-y ${themeTableWrap}`}>
                        {DB_ROLES.map((r) => (
                          <tr key={r.id} className="hover:bg-slate-500/5">
                            <td className="p-3.5 font-bold">{r.id}</td>
                            <td className="p-3.5">{r.name}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </>
  );
}

function LoginScreen({ onLogin, error }) {
  const [login, setLogin] = useState('mikhalyich_ot');
  const [password, setPassword] = useState('linq123');
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0D131F] text-white font-sans p-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onLogin(login, password);
        }}
        className="w-full max-w-sm space-y-4 bg-[#151E2E] border border-slate-800 rounded-2xl p-6 shadow-2xl"
      >
        <div className="flex items-center gap-3 border-b border-slate-800 pb-3">
          <LinQExactLogo isDark={true} />
          <div>
            <h1 className="text-base font-bold">LinQ — Вход в систему</h1>
            <p className="text-xs text-slate-400">Контроль промышленной безопасности</p>
          </div>
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">Логин сотрудника:</label>
          <input
            value={login}
            onChange={(e) => setLogin(e.target.value)}
            placeholder="Логин"
            autoFocus
            className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white text-sm focus:outline-none focus:border-sky-500"
          />
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">Пароль:</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Пароль"
            className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white text-sm focus:outline-none focus:border-sky-500"
          />
        </div>

        {error && <p className="text-xs text-rose-400 font-medium">{error}</p>}

        <button className="w-full py-2.5 rounded-lg bg-sky-600 hover:bg-sky-500 font-semibold cursor-pointer text-sm shadow transition">
          Войти
        </button>

        <div className="pt-2 border-t border-slate-800 text-[11px] text-slate-400 space-y-1">
          <p className="font-semibold text-slate-300">Быстрый выбор роли (пароль linq123):</p>
          <div className="flex flex-wrap gap-1 mt-1">
            {['mikhalyich_ot', 'master_ceh1', 'disp_smena1', 'it_linq_admin'].map((u) => (
              <button
                key={u}
                type="button"
                onClick={() => {
                  setLogin(u);
                  setPassword('linq123');
                }}
                className="px-1.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-sky-400 cursor-pointer font-mono"
              >
                {u}
              </button>
            ))}
          </div>
        </div>
      </form>
    </div>
  );
}

export default function App() {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const loadLocalSession = (targetLogin) => {
    const matchedUser =
      DB_USERS.find((u) => u.login === targetLogin) ||
      DB_USERS.find((u) => u.login === 'mikhalyich_ot') ||
      DB_USERS[0];

    const initialData = {
      cameras: INITIAL_CAMERAS_FALLBACK,
      events: INITIAL_EVENTS_FALLBACK,
      settings: {
        sirenEnabled: true,
      },
    };
    setSession({ user: matchedUser, initial: initialData });
  };

  useEffect(() => {
    if (api.getToken()) {
      setLoading(true);
      Promise.all([api.me(), api.cameras(), api.events(0), api.settings()])
        .then(([user, cameras, events, settings]) => {
          setSession({ user, initial: { cameras, events, settings } });
        })
        .catch(() => {
          api.logout();
        })
        .finally(() => setLoading(false));
    }
  }, []);

  const handleLogin = async (login, password) => {
    setError('');
    const cleanLogin = (login || '').trim();

    try {
      await api.login(cleanLogin, password);
      const [user, cameras, events, settings] = await Promise.all([
        api.me(),
        api.cameras(),
        api.events(0),
        api.settings(),
      ]);
      setSession({ user, initial: { cameras, events, settings } });
      return;
    } catch {
      if (password === 'linq123') {
        const found = DB_USERS.find((u) => u.login === cleanLogin);
        if (found) {
          loadLocalSession(found.login);
          return;
        }
        loadLocalSession('mikhalyich_ot');
        return;
      }
      setError('Неверный пароль. Используйте: linq123');
    }
  };

  if (loading) return null;
  if (!session) return <LoginScreen onLogin={handleLogin} error={error} />;
  return (
    <Dashboard
      user={session.user}
      initial={session.initial}
      onLogout={() => {
        try {
          api.logout();
        } catch {}
        setSession(null);
      }}
    />
  );
}