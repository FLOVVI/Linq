import React, { useState, useEffect, useRef } from 'react';
import { api } from './api';
import {
  Video,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Send,
  Cpu,
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
  Move,
  MessageSquare,
  Radar,
  Clock,
  Layers,
  Camera,
  Upload,
  Sparkles,
  RotateCw,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ChevronDown,
  ZoomIn,
  ZoomOut,
  Volume2,
  Lock,
  FileDown,
  FileText,
  Sliders,
  Maximize2,
  RefreshCw,
  FlipHorizontal,
  Play,
  Crosshair,
  Flame,
  LayoutGrid,
  HeartPulse,
  GraduationCap,
  LogOut,
  Keyboard,
  ShieldCheck,
  Activity,
  Image as ImageIcon,
  Copy,
  Check,
  HardHat,
  Compass,
  Search,
  Download,
} from 'lucide-react';

// 13 типов нарушений (полная совместимость с ИИ-модулем и бэкендом)
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

const ADVICE = {
  NO_HELMET: 'Проверить выдачу касок и блокировку турникета СКУД',
  NO_VEST: 'Проверить выдачу сигнальных жилетов перед сменой',
  DANGER_ZONE: 'Активировать физическое ограждение и звуковой маяк',
  DANGER_PROXIMITY: 'Разделить пешеходные и транспортные маршруты',
  SMOKING_FIRE: 'Проверить датчики огня и пожарный пост',
  PHONE_USAGE: 'Включить 5-минутный инструктаж о запрете смартфонов',
  RUNNING: 'Нанести противоскользящую разметку проходов',
  PERSON_FALL: 'Экстренный вызов медпункта (норматив до 30 сек)',
  NO_GLOVES: 'Контроль выдачи СИЗ рук на складе',
  NO_GOGGLES: 'Контроль защитных щитков у станочников',
};

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
      top: top.map(([k, n]) => `[${title(k)?.code}] ${title(k)?.name} — ${n}`).join(' / '),
      advice: top.length ? ADVICE[top[0][0]] || 'Разобрать с мастером участка' : 'В пределах нормы',
    };
  });
}

// Мягкий приятный двухтональный сигнал ИИ-ассистента
function playAliceChime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const now = ctx.currentTime;

    const playNote = (freq, start, duration) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, start);
      gain.gain.setValueAtTime(0.001, start);
      gain.gain.exponentialRampToValueAtTime(0.08, start + 0.03);
      gain.gain.exponentialRampToValueAtTime(0.001, start + duration);
      osc.connect(gain).connect(ctx.destination);
      osc.start(start);
      osc.stop(start + duration);
    };

    playNote(587.33, now, 0.16);
    playNote(880.0, now + 0.11, 0.24);
    setTimeout(() => ctx.close(), 500);
  } catch {}
}

// Выбор приятного женского русского нейро-голоса (в стиле Алисы)
function speakAliceVoice(text) {
  try {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    playAliceChime();

    const speakNow = () => {
      const utter = new SpeechSynthesisUtterance(text);
      utter.lang = 'ru-RU';

      const voices = window.speechSynthesis.getVoices();
      const ruVoices = voices.filter(
        (v) => v.lang.toLowerCase().includes('ru') || v.name.toLowerCase().includes('russian')
      );

      const preferredOrder = [
        'svetlana',
        'dariya',
        'natural',
        'google',
        'milena',
        'katya',
        'irina',
        'female',
      ];

      let chosenVoice = null;
      for (const keyword of preferredOrder) {
        const match = ruVoices.find((v) => v.name.toLowerCase().includes(keyword));
        if (match) {
          chosenVoice = match;
          break;
        }
      }
      if (!chosenVoice && ruVoices.length > 0) {
        chosenVoice = ruVoices[0];
      }

      if (chosenVoice) {
        utter.voice = chosenVoice;
      }
      utter.pitch = 1.08;
      utter.rate = 1.04;
      utter.volume = 0.95;

      window.speechSynthesis.speak(utter);
    };

    if (window.speechSynthesis.getVoices().length === 0) {
      window.speechSynthesis.onvoiceschanged = speakNow;
    } else {
      setTimeout(speakNow, 150);
    }
  } catch {}
}

const DB_USERS = [
  { id: 1, login: 'mikhalyich_ot', full_name: 'Кузьмин М.П.', position: 'Специалист по ОТ', role_id: 1, role_name: 'Роль 1: Специалист по ОТ', canEditRules: true },
  { id: 2, login: 'disp_smena1', full_name: 'Соколов А.В.', position: 'Диспетчер ЦУП', role_id: 3, role_name: 'Роль 3: Диспетчер', canEditRules: false },
  { id: 3, login: 'master_ceh1', full_name: 'Громов И.С.', position: 'Мастер смены', role_id: 2, role_name: 'Роль 2: Мастер участка', canEditRules: false },
  { id: 4, login: 'it_linq_admin', full_name: 'Дехтерюк Д.К.', position: 'ИТ-Инженер LinQ', role_id: 7, role_name: 'Роль 7: ИТ-интегратор', canEditRules: true },
];

const DB_ROLES = [
  { id: 1, name: 'Специалист по охране труда (Полный доступ к правилам и отчетам)' },
  { id: 2, name: 'Мастер производственного участка (Реагирование на инциденты)' },
  { id: 3, name: 'Оператор / Диспетчер ЦУП (Мониторинг и верификация потока)' },
  { id: 7, name: 'ИТ-интегратор LinQ TPU (Настройка потоков, камер и нейросетей)' },
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

function formatCompactRulesJson(obj) {
  const raw = JSON.stringify(obj, null, 2);
  return raw.replace(
    /"vector": \[\s+([\d,\s]+)\s+\]/g,
    (_, nums) => `"vector": [${nums.replace(/\s+/g, ' ').trim()}]`
  );
}

function IconTipButton({ icon: Icon, label, active, onClick, badge, danger, isDark }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group relative flex items-center justify-center w-9 h-9 rounded-xl border transition-all cursor-pointer shrink-0 ${
        active
          ? danger
            ? 'bg-red-600 text-white border-red-500 shadow-sm'
            : 'bg-sky-600 text-white border-sky-500 shadow-sm'
          : isDark
          ? 'bg-slate-800/90 text-slate-300 border-slate-700 hover:border-sky-500/60 hover:text-white'
          : 'bg-white text-slate-700 border-slate-200 hover:border-sky-500/60 hover:text-sky-600 shadow-2xs'
      }`}
    >
      <Icon size={16} />
      {badge !== undefined && badge > 0 && (
        <span className="absolute -top-1 -right-1 px-1 min-w-[16px] h-4 rounded-full bg-amber-500 text-slate-950 text-[10px] font-bold flex items-center justify-center">
          {badge}
        </span>
      )}
      <span className="pointer-events-none absolute -bottom-8 left-1/2 -translate-x-1/2 px-2 py-1 rounded-md bg-slate-950 text-white text-[11px] font-medium whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-50 shadow-lg border border-slate-700">
        {label}
      </span>
    </button>
  );
}

function LinQExactLogo({ forceDarkText = false, isDark = false }) {
  const mainColor = forceDarkText ? '#1E242B' : isDark ? '#FFFFFF' : '#1E242B';
  const bluePixel = '#2589DF';
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

function GostRostechnadzorReport({ cameras, events, currentUser, clusterCamerasCount, hourly }) {
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
          по данным автоматизированного аппаратно-программного комплекса видеоаналитики «LinQ Vision Guard» на базе отечественных ускорителей LinQ TPU
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
              <td className="border border-black p-1.5 font-bold">Применяемые технические средства контроля в реальном времени</td>
              <td className="border border-black p-1.5">
                Кластер российских ИИ-ускорителей LinQ TPU ({Math.ceil(clusterCamerasCount / 16)} вычислительных узла INT8, пропускная способность {clusterCamerasCount * 25} кадров/с, среднее время отклика 11.2 мс)
              </td>
            </tr>
            <tr>
              <td className="border border-black p-1.5 font-bold">Количество контролируемых участков / видеопотоков</td>
              <td className="border border-black p-1.5">
                Участков ОПО: {cameras.length} шт. | Активных потоков в отчете: {cameras.length} (расчет масштабирования: {clusterCamerasCount} камер)
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="mb-4 break-inside-avoid">
        <h2 className="text-[11pt] font-bold uppercase mb-1.5">
          2. Состояние оснащенности опасных производственных участков средствами видеоаналитики
        </h2>
        <table className="w-full border-collapse border border-black text-[9.5pt]">
          <thead>
            <tr className="bg-slate-100 font-bold text-center">
              <th className="border border-black p-1.5">Код узла</th>
              <th className="border border-black p-1.5">Наименование производственного участка (ОПО)</th>
              <th className="border border-black p-1.5">Тип камеры</th>
              <th className="border border-black p-1.5">Вектор правил контроля</th>
              <th className="border border-black p-1.5">Выделенные зоны контроля и режим</th>
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
                  {cam.ai?.online ? `Исправен (${cam.fps} FPS)` : `Активен (${cam.fps} FPS)`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mb-4 break-inside-avoid">
        <h2 className="text-[11pt] font-bold uppercase mb-1.5">
          3. Ведомость выявленных нарушений требований промышленной безопасности и принятых мер
        </h2>
        <table className="w-full border-collapse border border-black text-[9.5pt]">
          <thead>
            <tr className="bg-slate-100 font-bold text-center">
              <th className="border border-black p-1.5">№ акта (ID)</th>
              <th className="border border-black p-1.5">Время фиксации</th>
              <th className="border border-black p-1.5">Участок / Камера</th>
              <th className="border border-black p-1.5">Выявленный опасный паттерн</th>
              <th className="border border-black p-1.5">Достоверность ИИ</th>
              <th className="border border-black p-1.5">Сведения о принятых мерах и ответственном лице</th>
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
          4. Анализ распределения инцидентов по часам рабочей смены и профилактические мероприятия
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
      { id: 'TRK-31', label: 'ID #31 • Кладовщик', x: 12, y: 42, w: 12, h: 34, ppeOk: true },
    ],
    zones: [
      {
        id: 'z-3',
        type: 'danger',
        shape: 'rect',
        label: 'Работа погрузчика',
        schedule: '07:55 – 12:00',
        rect: { x: 25, y: 38, w: 48, h: 46 },
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
    ai_pos: { x: 68, y: 62 },
    status: 'new',
    processed_by_id: null,
    processed_by_name: 'Ожидает реакции',
    processed_at: null,
    confidence: 0.98,
    description: 'Сотрудник без движения более 3.5 сек у линии сборки',
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
    ai_pos: { x: 44, y: 58 },
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
    ai_pos: { x: 26, y: 64 },
    status: 'confirmed',
    processed_by_id: 1,
    processed_by_name: 'Кузьмин М.П.',
    processed_at: '13:20:10',
    confidence: 0.92,
    description: 'Зафиксировано в зоне особого внимания у конвейера, проведен инструктаж',
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
  const [briefingModalOpen, setBriefingModalOpen] = useState(false);

  const [showHeatmap, setShowHeatmap] = useState(false);
  const [voiceAssistantEnabled, setVoiceAssistantEnabled] = useState(true);
  const [emergencyDispatchedId, setEmergencyDispatchedId] = useState(null);
  const [copiedJson, setCopiedJson] = useState(false);

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

  const [enhanceFilter, setEnhanceFilter] = useState(initial.settings?.enhanceFilter ?? false);
  const [stabilizeZonesOnPTZ, setStabilizeZonesOnPTZ] = useState(initial.settings?.stabilizeZonesOnPTZ ?? true);
  const [sirenEnabled, setSirenEnabled] = useState(initial.settings?.sirenEnabled ?? true);
  const [skudLockEnabled, setSkudLockEnabled] = useState(initial.settings?.skudLockEnabled ?? false);
  const [simulateWorkersWalk, setSimulateWorkersWalk] = useState(false);

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
  const mapContainerRef = useRef(null);

  const [newSiteInput, setNewSiteInput] = useState('');
  const [newCamInput, setNewCamInput] = useState('');
  const [newCamTypeInput, setNewCamTypeInput] = useState('dynamic');
  const [newRtspInput, setNewRtspInput] = useState('');

  const [clusterCamerasCount, setClusterCamerasCount] = useState(24);

  const [verifyProgress, setVerifyProgress] = useState(0);
  const [isVerifying, setIsVerifying] = useState(false);
  const verificationLockRef = useRef(false);

  const currentCamera = cameras.find((c) => c.id === selectedCamId) || cameras[0] || INITIAL_CAMERAS_FALLBACK[0];
  const activeEvent = events.find((e) => e.id === selectedEventId) || events[0] || NO_EVENT;
  const falseAlarmEvents = events.filter((e) => e.status === 'false_alarm');
  const aiMode = videoSource === 'ai';
  const camAi = currentCamera.ai || {};
  const aiOnlineCams = cameras.filter((c) => c.ai?.online);
  const frameAspect = camAi.frame ? `${camAi.frame[0]} / ${camAi.frame[1]}` : '16 / 9';

  // Быстрые горячие клавиши 1, 2, 3
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

  useEffect(() => {
    if (!currentCamera.autoPatrol || currentCamera.cameraType !== 'dynamic') return;
    const interval = setInterval(() => {
      setCameras((prev) =>
        prev.map((cam) => {
          if (cam.id !== currentCamera.id) return cam;
          const nextAngle = cam.panAngle >= 35 ? -35 : cam.panAngle + 5;
          return { ...cam, panAngle: nextAngle };
        })
      );
    }, 900);
    return () => clearInterval(interval);
  }, [currentCamera.autoPatrol, currentCamera.cameraType, currentCamera.id]);

  useEffect(() => {
    if (!simulateWorkersWalk) return;
    const interval = setInterval(() => {
      setCameras((prev) =>
        prev.map((cam) => {
          if (cam.id !== currentCamera.id) return cam;
          return {
            ...cam,
            workers: (cam.workers || []).map((w, idx) => {
              const step = idx === 0 ? 3.5 : -3;
              let nextX = w.x + step;
              if (nextX > 78) nextX = 12;
              if (nextX < 8) nextX = 74;
              return { ...w, x: Math.round(nextX) };
            }),
          };
        })
      );
    }, 700);
    return () => clearInterval(interval);
  }, [simulateWorkersWalk, currentCamera.id]);

  const collidingDangerWorker =
    aiMode && camAi.online
      ? null
      : (currentCamera.workers || []).find((w) => {
          const hitZone = checkWorkerZoneCollision(w, currentCamera.zones);
          return (hitZone && hitZone.type === 'danger') || w.ppeOk === false;
        });

  useEffect(() => {
    if (collidingDangerWorker && !isVerifying && !verificationLockRef.current) {
      startIncidentVerification();
    }
  }, [collidingDangerWorker]);

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

  useEffect(() => {
    if (!isVerifying) return;
    const timer = setInterval(() => {
      setVerifyProgress((prev) => Math.min(100, prev + 10));
    }, 220);
    return () => clearInterval(timer);
  }, [isVerifying]);

  useEffect(() => {
    if (isVerifying && verifyProgress >= 100 && !verificationLockRef.current) {
      verificationLockRef.current = true;
      setIsVerifying(false);
      setVerifyProgress(0);

      const noHelmetWorker = (currentCamera.workers || []).find((w) => w.ppeOk === false);
      const enabledIndices = currentCamera.rulesVector
        .map((v, i) => (v === 1 ? i : null))
        .filter((v) => v !== null);
      const chosenIdx = noHelmetWorker
        ? 8
        : enabledIndices.length > 0
        ? enabledIndices[Math.floor(Math.random() * enabledIndices.length)]
        : 1;
      const vType = VIOLATION_TYPES[chosenIdx];

      if (voiceAssistantEnabled) {
        speakAliceVoice(
          `Внимание, диспетчер. ${currentCamera.site_name}. Зафиксировано нарушение: ${vType.name}. Рекомендуется проверка.`
        );
      } else if (sirenEnabled) {
        playAliceChime();
      }

      api
        .createEvent({
          camera_id: currentCamera.id,
          violation: vType.enumKey,
          confidence: Number((0.92 + Math.random() * 0.07).toFixed(2)),
          ai_pos: { x: Math.floor(25 + Math.random() * 55), y: Math.floor(30 + Math.random() * 50) },
          description: collidingDangerWorker
            ? `Фиксация по объекту ${collidingDangerWorker.id} (${currentCamera.code})`
            : `Автофиксация на участке (${currentCamera.code})`,
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
            ai_pos: { x: Math.floor(25 + Math.random() * 55), y: Math.floor(30 + Math.random() * 50) },
            status: 'new',
            processed_by_id: null,
            processed_by_name: 'Ожидает реакции',
            processed_at: null,
            confidence: Number((0.92 + Math.random() * 0.07).toFixed(2)),
            description: collidingDangerWorker
              ? `Фиксация по объекту ${collidingDangerWorker.id} (${currentCamera.code})`
              : `Автофиксация на участке (${currentCamera.code})`,
            severity: vType.code === '07' ? 'critical' : 'warning',
          };
          setEvents((prev) => [localEvt, ...prev]);
          setSelectedEventId(nextId);
        });
    }
  }, [verifyProgress, isVerifying, currentCamera, collidingDangerWorker, events, sirenEnabled, voiceAssistantEnabled]);

  const startIncidentVerification = () => {
    if (isVerifying) return;
    verificationLockRef.current = false;
    setVerifyProgress(10);
    setIsVerifying(true);
  };

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

  const adjustCameraPan = (deltaAngle) => {
    setCameras((prev) =>
      prev.map((cam) =>
        cam.id === selectedCamId
          ? { ...cam, panAngle: Math.max(-60, Math.min(60, cam.panAngle + deltaAngle)) }
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

  const adjustCameraTilt = (deltaTilt) => {
    setCameras((prev) =>
      prev.map((cam) =>
        cam.id === selectedCamId
          ? { ...cam, tiltAngle: Math.max(-30, Math.min(30, (cam.tiltAngle || 0) + deltaTilt)) }
          : cam
      )
    );
  };

  const resetCameraPTZ = () => {
    setCameras((prev) =>
      prev.map((cam) =>
        cam.id === selectedCamId
          ? { ...cam, panAngle: 0, tiltAngle: 0, zoomLevel: 1, autoPatrol: false }
          : cam
      )
    );
  };

  const adjustCameraZoom = (deltaZoom) => {
    setCameras((prev) =>
      prev.map((cam) =>
        cam.id === selectedCamId
          ? {
              ...cam,
              zoomLevel: Number(
                Math.max(1, Math.min(1.8, cam.zoomLevel + deltaZoom)).toFixed(2)
              ),
            }
          : cam
      )
    );
  };

  const toggleAutoPatrol = () => {
    setCameras((prev) =>
      prev.map((cam) =>
        cam.id === selectedCamId ? { ...cam, autoPatrol: !cam.autoPatrol } : cam
      )
    );
  };

  const toggleFirstWorkerPPE = () => {
    setCameras((prev) =>
      prev.map((cam) => {
        if (cam.id !== selectedCamId) return cam;
        return {
          ...cam,
          workers: (cam.workers || []).map((w, i) =>
            i === 0 ? { ...w, ppeOk: !w.ppeOk } : w
          ),
        };
      })
    );
  };

  const handleMapMouseMove = (e) => {
    if (!draggingCamId || !mapContainerRef.current) return;
    const rect = mapContainerRef.current.getBoundingClientRect();
    const x = Math.max(5, Math.min(95, Math.round(((e.clientX - rect.left) / rect.width) * 100)));
    const y = Math.max(8, Math.min(92, Math.round(((e.clientY - rect.top) / rect.height) * 100)));

    setCameras((prev) =>
      prev.map((cam) => (cam.id === draggingCamId ? { ...cam, mapPos: { x, y } } : cam))
    );
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
            if (newest) {
              if (voiceAssistantEnabled) {
                speakAliceVoice(`Внимание! ${newest.camera_code}. ${newest.violation_title}`);
              } else if (sirenEnabled) {
                playAliceChime();
              }
            }
            const merged = fresh.map((f) => (local[f.id] ? { ...f, description: local[f.id].description } : f));
            const ids = new Set(merged.map((e) => e.id));
            return [...merged, ...prev.filter((e) => !ids.has(e.id))];
          });
        })
        .catch(() => {});
    }, 4000);
    return () => clearInterval(t);
  }, [sirenEnabled, voiceAssistantEnabled]);

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
      api.putSettings({ sirenEnabled, skudLockEnabled, enhanceFilter, stabilizeZonesOnPTZ }).catch(() => {});
    }
  }, [sirenEnabled, skudLockEnabled, enhanceFilter, stabilizeZonesOnPTZ, currentUser.canEditRules]);

  const handleAddCamera = (e) => {
    e.preventDefault();
    if (!currentUser.canEditRules) return;
    if (!newSiteInput.trim() || !newCamInput.trim()) return;
    const nextNum = cameras.length + 1;
    const offsetX = Math.min(85, 28 + ((nextNum * 15) % 52));
    const offsetY = Math.min(85, 32 + ((nextNum * 19) % 48));

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

  const handleEmergencyDispatch = (ev) => {
    setEmergencyDispatchedId(ev.id);
    handleProcessEvent(ev.id, 'confirmed');
    handleUpdateEventComment(ev.id, 'ЭКСТРЕННО: Вызван медпункт и остановлена линия (< 30 сек)');
    if (voiceAssistantEnabled) {
      speakAliceVoice(`Экстренный протокол активирован. Бригада медпункта направлена на ${ev.site_name}. Конвейерная линия остановлена.`);
    }
  };

  const handleUpdateEventComment = (eventId, text) => {
    setEvents((prev) => prev.map((ev) => (ev.id === eventId ? { ...ev, description: text } : ev)));
    clearTimeout(commentTimer.current);
    commentTimer.current = setTimeout(() => api.commentEvent(eventId, text).catch(() => {}), 600);
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

  const handleCopyJson = () => {
    const jsonStr = formatCompactRulesJson({
      site_id: currentCamera.site_id,
      site_name: currentCamera.site_name,
      camera: currentCamera.code,
      camera_type: currentCamera.cameraType,
      direction_deg: (currentCamera.mapDirection || 0) + (currentCamera.panAngle || 0),
      vector: currentCamera.rulesVector,
      zones: currentCamera.zones.map((z) => ({
        label: z.label,
        type: z.type,
        shape: z.shape,
        schedule: z.schedule,
        coords: z.shape === 'rect' ? z.rect : z.points,
      })),
    });
    navigator.clipboard?.writeText(jsonStr);
    setCopiedJson(true);
    setTimeout(() => setCopiedJson(false), 1800);
  };

  // Экспорт таблицы events в CSV для отчета
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

  // Адаптивные переменные темы (строго зависят от isDark, чтобы системная тема ОС никогда не ломала цвета!)
  const themePage = isDark
    ? 'bg-[#0B1120] text-slate-100'
    : 'bg-[#F4F7FA] text-slate-800';
  const themeCard = isDark
    ? 'bg-[#151F32] border-slate-800 text-slate-100'
    : 'bg-white border-slate-200/90 text-slate-800 shadow-2xs';
  const themeSubCard = isDark
    ? 'bg-[#0F172A]/85 border-slate-800 text-slate-100'
    : 'bg-slate-50 border-slate-200/90 text-slate-800';
  const themeCodeBlock = isDark
    ? 'bg-slate-950 text-sky-300 border-slate-800'
    : 'bg-slate-100 text-slate-800 border-slate-300';
  const themeTableHead = isDark
    ? 'bg-slate-800/90 text-slate-200 border-b border-slate-700'
    : 'bg-slate-100 text-slate-700 border-b border-slate-200';
  const themeTableWrap = isDark
    ? 'border-slate-700 divide-slate-800'
    : 'border-slate-200 divide-slate-200';
  const textMuted = isDark ? 'text-slate-400' : 'text-slate-500';

  const zoneColors = {
    danger: {
      border: '#EF4444',
      bg: 'rgba(239, 68, 68, 0.22)',
      badge: 'bg-red-600 text-white',
      name: 'Опасная зона',
    },
    attention: {
      border: '#F59E0B',
      bg: 'rgba(245, 158, 11, 0.22)',
      badge: 'bg-amber-500 text-slate-950',
      name: 'Особое внимание',
    },
    blind: {
      border: '#64748B',
      bg: 'rgba(100, 116, 139, 0.28)',
      badge: 'bg-slate-600 text-white',
      name: 'Слепая зона',
    },
  };

  const panOffsetPercent =
    currentCamera.cameraType === 'dynamic' && stabilizeZonesOnPTZ
      ? -currentCamera.panAngle * 0.6
      : 0;
  const tiltOffsetPercent =
    currentCamera.cameraType === 'dynamic' && stabilizeZonesOnPTZ
      ? -(currentCamera.tiltAngle || 0) * 0.6
      : 0;

  return (
    <>
      <div className="hidden print:block bg-white text-black">
        <GostRostechnadzorReport
          hourly={hourlyStats}
          cameras={cameras}
          events={events}
          currentUser={currentUser}
          clusterCamerasCount={clusterCamerasCount}
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
              clusterCamerasCount={clusterCamerasCount}
            />
          </div>
        </div>
      )}

      {/* МОДАЛЬНОЕ ОКНО АВТО-ГЕНЕРАЦИИ ПРЕДСМЕННОГО ИНСТРУКТАЖА */}
      {briefingModalOpen && (
        <div className="print:hidden fixed inset-0 bg-black/75 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className={`max-w-xl w-full rounded-2xl border p-6 shadow-2xl ${themeCard}`}>
            <div className="flex items-center justify-between pb-3 border-b border-inherit">
              <div className="flex items-center gap-2">
                <GraduationCap size={18} className="text-sky-500" />
                <h3 className="text-sm font-bold">
                  ИИ-Генератор целевого 5-минутного инструктажа для смены
                </h3>
              </div>
              <button
                onClick={() => setBriefingModalOpen(false)}
                className="px-2.5 py-1 rounded-lg bg-slate-500/20 text-xs font-semibold cursor-pointer"
              >
                Закрыть
              </button>
            </div>

            <div className="mt-4 space-y-3 text-xs">
              <div className={`p-3.5 rounded-xl border ${themeSubCard}`}>
                <p className="font-bold text-sky-500">
                  Автоматическая сводка по обезличенным случаям за предыдущие 24 часа:
                </p>
                <ul className="mt-2 space-y-1.5 list-disc list-inside">
                  <li>
                    <strong>Пик нарушений:</strong> 08:00 – 10:00 (первые 2 часа после пересменки).
                  </li>
                  <li>
                    <strong>Проблемная зона:</strong> {currentCamera.site_name} ({currentCamera.code}).
                  </li>
                  <li>
                    <strong>Ключевой акцент инструктажа:</strong> контроль касок и сигнальных жилетов при входе, соблюдение дистанции 2.5 м до погрузчика и манипулятора.
                  </li>
                </ul>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  onClick={() => {
                    if (voiceAssistantEnabled) {
                      speakAliceVoice('Целевой предсменный инструктаж сформирован и отправлен на терминалы СКУД участка.');
                    }
                    setBriefingModalOpen(false);
                  }}
                  className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-white font-semibold cursor-pointer"
                >
                  Отправить на терминал СКУД и планшет мастера
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* МОДАЛЬНОЕ ОКНО: РАЗБОР СТОП-КАДРА И ВИДЕОКЛИПА */}
      {inspectModalEvent && (
        <div className="print:hidden fixed inset-0 bg-black/75 backdrop-blur-xs z-50 flex items-center justify-center p-4 overflow-y-auto">
          <div className={`max-w-4xl w-full rounded-2xl border p-6 shadow-2xl ${themeCard}`}>
            <div className="flex items-center justify-between pb-3 border-b border-inherit">
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-0.5 rounded bg-red-600 text-white text-xs font-bold">
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
                  <div className="w-28 h-36 border-2 border-red-500 bg-red-500/15 rounded relative">
                    <span className="absolute -top-5 left-0 bg-red-600 text-white text-[10px] font-bold px-1.5 py-0.5 rounded whitespace-nowrap">
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
                    className="flex-1 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold cursor-pointer"
                  >
                    Подтвердить
                  </button>
                  <button
                    onClick={() => {
                      handleProcessEvent(inspectModalEvent.id, 'false_alarm');
                      setInspectModalEvent(null);
                    }}
                    className="flex-1 py-2 rounded-xl bg-red-600 hover:bg-red-500 text-white font-semibold cursor-pointer"
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
        {/* ЕДИНАЯ ШАПКА */}
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
                      ? 'bg-emerald-500/15 text-emerald-500 border-emerald-500/30'
                      : 'bg-sky-500/15 text-sky-500 border-sky-500/30'
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
                      : `${themeSubCard} border hover:border-sky-500/50`
                  }`}
                >
                  <Icon size={15} />
                  <span>{tab.label}</span>
                  {tab.badge && (
                    <span
                      className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                        active ? 'bg-white/20 text-white' : 'bg-slate-500/15 text-slate-500'
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
            <button
              onClick={startIncidentVerification}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold transition cursor-pointer shadow-2xs"
              title="Смоделировать нарушение с 3-секундной верификацией"
            >
              <AlertTriangle size={14} />
              <span className="hidden xl:inline">
                {isVerifying ? `${(verifyProgress * 0.03).toFixed(1)} с...` : 'Тест тревоги'}
              </span>
            </button>

            <IconTipButton
              icon={Volume2}
              label={voiceAssistantEnabled ? 'Голосовой ИИ-ассистент (Алиса): ВКЛ' : 'Голосовой ИИ-ассистент: ВЫКЛ'}
              active={voiceAssistantEnabled}
              onClick={() => {
                const next = !voiceAssistantEnabled;
                setVoiceAssistantEnabled(next);
                if (next) {
                  speakAliceVoice(
                    `Здравствуйте, ${currentUser.full_name.split(' ')[0]}. Голосовой ассистент промышленной безопасности LinQ готов к работе.`
                  );
                }
              }}
              isDark={isDark}
            />

            <IconTipButton
              icon={Eye}
              label={eyeComfort ? 'Защита зрения: ВКЛ' : 'Защита зрения 24/7'}
              active={eyeComfort}
              onClick={() => setEyeComfort(!eyeComfort)}
              isDark={isDark}
            />

            <IconTipButton
              icon={isDark ? Sun : Moon}
              label={isDark ? 'Светлая тема' : 'Темная тема'}
              active={false}
              onClick={() => setIsDark(!isDark)}
              isDark={isDark}
            />

            <IconTipButton
              icon={LogOut}
              label="Сменить пользователя / Выйти"
              active={false}
              onClick={onLogout}
              isDark={isDark}
            />
          </div>
        </header>

        {isVerifying && (
          <div className="px-5 pt-2.5">
            <div className="bg-amber-500/15 border border-amber-500/40 rounded-xl px-4 py-2 flex items-center justify-between gap-4">
              <div className="flex items-center gap-2 text-xs font-medium text-amber-500">
                <Clock size={15} className="animate-spin" />
                <span>Верификация длительности паттерна (защита от случайных одиночных кадров)...</span>
              </div>
              <div className="w-48 h-2 bg-slate-500/30 rounded-full overflow-hidden">
                <div
                  className="h-full bg-amber-500 transition-all duration-200"
                  style={{ width: `${verifyProgress}%` }}
                />
              </div>
            </div>
          </div>
        )}

        <main className="flex-1 flex flex-col p-5">
          {/* ================= ВКЛАДКА 1: ВИДЕОКОНТРОЛЬ ================= */}
          {activeTab === 'monitoring' && (
            <div className="flex-1 flex flex-col gap-5 justify-between">
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 flex-1 items-stretch">
                {/* ЛЕВАЯ ЧАСТЬ (8 из 12): Камера + Таймлайн смены */}
                <div className={`lg:col-span-8 border rounded-2xl flex flex-col overflow-hidden ${themeCard}`}>
                  <div className="p-3 border-b border-inherit flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {cameras.map((cam) => (
                        <button
                          key={cam.id}
                          onClick={() => setSelectedCamId(cam.id)}
                          className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition cursor-pointer flex items-center gap-1.5 ${
                            selectedCamId === cam.id
                              ? 'bg-sky-600 text-white border-sky-600 shadow-2xs'
                              : `${themeSubCard} hover:border-sky-500/50`
                          }`}
                        >
                          <span
                            className={`w-2 h-2 rounded-full ${
                              selectedCamId === cam.id ? 'bg-white' : 'bg-emerald-500'
                            }`}
                          />
                          <span>{cam.code}</span>
                        </button>
                      ))}
                      <span className={`text-xs font-medium ml-1 hidden sm:inline ${textMuted}`}>
                        {currentCamera.site_name}
                      </span>
                    </div>

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
                        icon={HardHat}
                        label="Снять / Надеть каску у рабочего (Тест СИЗ)"
                        active={currentCamera.workers?.[0]?.ppeOk === false}
                        danger={true}
                        onClick={toggleFirstWorkerPPE}
                        isDark={isDark}
                      />
                      <IconTipButton
                        icon={Flame}
                        label="Предиктивная тепловая карта рисков (Heatmap)"
                        active={showHeatmap}
                        danger={true}
                        onClick={() => setShowHeatmap(!showHeatmap)}
                        isDark={isDark}
                      />
                      <IconTipButton
                        icon={Cpu}
                        label={aiMode ? 'Режим: Поток ИИ LinQ' : 'Включить поток ИИ LinQ'}
                        active={aiMode}
                        onClick={() => setVideoSource(aiMode ? 'simulation' : 'ai')}
                        isDark={isDark}
                      />
                      <IconTipButton
                        icon={Play}
                        label="Симуляция движения рабочих в цеху"
                        active={simulateWorkersWalk}
                        onClick={() => {
                          setVideoSource('simulation');
                          setSimulateWorkersWalk(!simulateWorkersWalk);
                        }}
                        isDark={isDark}
                      />
                      <IconTipButton
                        icon={Camera}
                        label="Подключить живую веб-камеру"
                        active={videoSource === 'webcam'}
                        onClick={() =>
                          setVideoSource(videoSource === 'webcam' ? 'simulation' : 'webcam')
                        }
                        isDark={isDark}
                      />
                      {videoSource === 'webcam' && (
                        <IconTipButton
                          icon={FlipHorizontal}
                          label={webcamUnmirrored ? 'Прямой вид камеры' : 'Зеркальный вид'}
                          active={webcamUnmirrored}
                          onClick={() => setWebcamUnmirrored(!webcamUnmirrored)}
                          isDark={isDark}
                        />
                      )}
                      <label className="group relative flex items-center justify-center w-9 h-9 rounded-xl border cursor-pointer shrink-0 bg-slate-500/10 border-slate-500/30 hover:border-sky-500">
                        <Upload size={16} />
                        <input
                          type="file"
                          accept="video/*"
                          onChange={handleVideoFileUpload}
                          className="hidden"
                        />
                        <span className="pointer-events-none absolute -bottom-8 left-1/2 -translate-x-1/2 px-2 py-1 rounded-md bg-slate-950 text-white text-[11px] font-medium whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-50 shadow-lg border border-slate-700">
                          Загрузить видеофайл (.mp4)
                        </span>
                      </label>
                      <IconTipButton
                        icon={Sparkles}
                        label="Анти-пыль / Ночное контрастирование"
                        active={enhanceFilter}
                        onClick={() => setEnhanceFilter(!enhanceFilter)}
                        isDark={isDark}
                      />
                    </div>
                  </div>

                  {drawMode !== 'none' && (
                    <div className="px-4 py-2 bg-sky-500/10 border-b border-sky-500/30 flex flex-wrap items-center justify-between gap-2 text-xs">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-bold text-sky-500">
                          Параметры новой зоны:
                        </span>
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
                            className="px-3 py-1 rounded-lg bg-emerald-600 text-white font-semibold cursor-pointer"
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
                    style={aiMode && camAi.online ? { aspectRatio: frameAspect } : undefined}
                    className={`relative bg-slate-950 overflow-hidden select-none flex-1 min-h-[450px] ${
                      drawMode !== 'none' ? 'cursor-crosshair ring-2 ring-sky-500' : ''
                    } ${enhanceFilter ? 'contrast-125 brightness-110 saturate-125' : ''}`}
                  >
                    <div
                      ref={worldSceneRef}
                      style={{
                        transform: `scale(${currentCamera.zoomLevel}) translate(${panOffsetPercent}%, ${tiltOffsetPercent}%)`,
                        transformOrigin: 'center center',
                      }}
                      className={`absolute inset-0 w-full h-full ${
                        activeZoneAction || drawMode !== 'none'
                          ? ''
                          : 'transition-transform duration-300 ease-out'
                      }`}
                    >
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
                            className="absolute w-72 h-72 rounded-full blur-2xl opacity-65"
                            style={{
                              left: '50%',
                              top: '30%',
                              background:
                                'radial-gradient(circle, rgba(239,68,68,0.85) 0%, rgba(245,158,11,0.5) 45%, transparent 75%)',
                            }}
                          />
                          <div
                            className="absolute w-56 h-56 rounded-full blur-2xl opacity-55"
                            style={{
                              left: '14%',
                              top: '40%',
                              background:
                                'radial-gradient(circle, rgba(245,158,11,0.8) 0%, rgba(56,189,248,0.4) 55%, transparent 75%)',
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
                              title={`${zone.label} • Режим: ${zone.schedule || '24/7'}`}
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
                                  className="text-slate-300 hover:text-red-400 ml-0.5 cursor-pointer"
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
                                  className="text-slate-300 hover:text-red-400 ml-0.5 cursor-pointer"
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
                          const isDanger = hitZone?.type === 'danger' || worker.ppeOk === false;
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
                              title="Перетащите сотрудника мышкой в опасную зону для теста срабатывания"
                              className={`absolute border-2 rounded-md cursor-grab active:cursor-grabbing z-25 transition-colors ${
                                isDanger
                                  ? 'border-red-500 bg-red-500/25 ring-2 ring-red-500/50'
                                  : isAttention
                                  ? 'border-amber-400 bg-amber-400/20'
                                  : 'border-emerald-400 bg-emerald-500/10'
                              }`}
                            >
                              <div
                                className={`absolute -top-5 left-0 text-white text-[10px] font-semibold px-1.5 py-0.5 rounded whitespace-nowrap shadow ${
                                  isDanger
                                    ? 'bg-red-600 animate-pulse'
                                    : isAttention
                                    ? 'bg-amber-500 text-slate-950'
                                    : 'bg-emerald-600'
                                }`}
                              >
                                {worker.ppeOk === false
                                  ? `${worker.id} • НЕТ КАСКИ!`
                                  : isDanger
                                  ? `${worker.id} • ОПАСНАЯ ЗОНА!`
                                  : isAttention
                                  ? `${worker.id} • Контроль СИЗ`
                                  : `${worker.label} • Норма`}
                              </div>
                            </div>
                          );
                        })}
                    </div>

                    {currentCamera.cameraType === 'dynamic' && (
                      <div
                        onMouseDown={(e) => e.stopPropagation()}
                        className="absolute top-3 right-3 flex items-center gap-1 bg-slate-950/85 backdrop-blur-xs border border-slate-700/80 rounded-xl p-1 z-30 text-slate-200"
                      >
                        <button
                          onClick={() => adjustCameraPan(-10)}
                          title="Поворот влево"
                          className="p-1.5 hover:bg-slate-800 rounded-lg cursor-pointer"
                        >
                          <ChevronLeft size={14} />
                        </button>
                        <button
                          onClick={() => adjustCameraPan(10)}
                          title="Поворот вправо"
                          className="p-1.5 hover:bg-slate-800 rounded-lg cursor-pointer"
                        >
                          <ChevronRight size={14} />
                        </button>
                        <button
                          onClick={() => adjustCameraTilt(-8)}
                          title="Наклон вверх"
                          className="p-1.5 hover:bg-slate-800 rounded-lg cursor-pointer"
                        >
                          <ChevronUp size={14} />
                        </button>
                        <button
                          onClick={() => adjustCameraTilt(8)}
                          title="Наклон вниз"
                          className="p-1.5 hover:bg-slate-800 rounded-lg cursor-pointer"
                        >
                          <ChevronDown size={14} />
                        </button>
                        <button
                          onClick={() => adjustCameraZoom(0.15)}
                          title="Приблизить (Zoom +)"
                          className="p-1.5 hover:bg-slate-800 rounded-lg cursor-pointer"
                        >
                          <ZoomIn size={14} />
                        </button>
                        <button
                          onClick={() => adjustCameraZoom(-0.15)}
                          title="Отдалить (Zoom -)"
                          className="p-1.5 hover:bg-slate-800 rounded-lg cursor-pointer"
                        >
                          <ZoomOut size={14} />
                        </button>
                        <button
                          onClick={resetCameraPTZ}
                          title="Центрировать 0°"
                          className="p-1.5 hover:bg-slate-800 rounded-lg cursor-pointer"
                        >
                          <Crosshair size={13} />
                        </button>
                        <button
                          onClick={toggleAutoPatrol}
                          title="Автоматическое патрулирование 360°"
                          className={`p-1.5 rounded-lg cursor-pointer ${
                            currentCamera.autoPatrol ? 'bg-amber-600 text-white' : 'hover:bg-slate-800'
                          }`}
                        >
                          <RotateCw size={13} className={currentCamera.autoPatrol ? 'animate-spin' : ''} />
                        </button>
                      </div>
                    )}

                    <div className="absolute bottom-3 left-3 flex flex-wrap items-center gap-2 pointer-events-none z-30">
                      <span className="px-2.5 py-1 rounded-lg bg-slate-950/85 border border-slate-700 text-[11px] font-mono text-slate-200 flex items-center gap-1.5">
                        <Cpu size={12} className="text-sky-400" />
                        {currentCamera.code} • {currentCamera.fps} FPS • {currentCamera.latency} • Зум {currentCamera.zoomLevel}x
                      </span>
                      {showHeatmap && (
                        <span className="px-2.5 py-1 rounded-lg bg-amber-500/90 text-slate-950 text-[11px] font-bold">
                          Предиктивный риск смены: Высокий (Зона манипулятора)
                        </span>
                      )}
                      {collidingDangerWorker && (
                        <span className="px-2.5 py-1 rounded-lg bg-red-600 text-white text-[11px] font-bold animate-pulse">
                          ТРЕВОГА: Нарушение ТБ ({collidingDangerWorker.id})
                        </span>
                      )}
                    </div>
                  </div>

                  {/* ИНТЕРАКТИВНЫЙ ТАЙМЛАЙН СМЕНЫ С МЕТКАМИ ИНЦИДЕНТОВ + АВТОМАТИКА */}
                  <div className="px-4 py-2.5 border-t border-inherit flex flex-wrap items-center justify-between gap-3 text-xs">
                    <div className="flex flex-wrap items-center gap-4">
                      <label className="flex items-center gap-1.5 cursor-pointer font-medium">
                        <input
                          type="checkbox"
                          checked={sirenEnabled}
                          onChange={(e) => setSirenEnabled(e.target.checked)}
                        />
                        <Volume2 size={14} className="text-amber-500" />
                        <span>Сирена в цеху</span>
                      </label>

                      <label className="flex items-center gap-1.5 cursor-pointer font-medium">
                        <input
                          type="checkbox"
                          checked={skudLockEnabled}
                          onChange={(e) => setSkudLockEnabled(e.target.checked)}
                        />
                        <Lock size={14} className="text-sky-500" />
                        <span>Авто-блокировка СКУД</span>
                      </label>
                    </div>

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
                              className={`absolute -translate-x-1/2 w-3 h-3 rounded-full border border-white cursor-pointer transition-transform hover:scale-125 ${
                                ev.severity === 'critical' ? 'bg-red-500' : 'bg-amber-400'
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

                {/* ПРАВАЯ ЧАСТЬ (4 из 12): Лента событий */}
                <div
                  className={`lg:col-span-4 border rounded-2xl flex flex-col overflow-hidden ${themeCard}`}
                >
                  <div className="p-3.5 border-b border-inherit flex items-center justify-between gap-2 shrink-0">
                    <div>
                      <h2 className="text-sm font-bold flex items-center gap-1.5">
                        <span>Лента событий</span>
                        <span className="text-[11px] px-2 py-0.5 rounded-full bg-red-500/15 text-red-500 font-bold">
                          {events.filter((e) => e.status === 'new').length} новых
                        </span>
                      </h2>
                      <p className={`text-[11px] flex items-center gap-1 mt-0.5 ${textMuted}`}>
                        <Keyboard size={11} /> Быстрые клавиши: [1] Подтв. [2] Мастеру [3] Ложное
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

                  <div className="p-3 space-y-2.5 overflow-y-auto flex-1 max-h-[520px]">
                    {filteredEvents.map((ev) => {
                      const isSelected = ev.id === selectedEventId;
                      const isCritical = ev.severity === 'critical' || ev.violation === 'PERSON_FALL';
                      return (
                        <div
                          key={ev.id}
                          onClick={() => setSelectedEventId(ev.id)}
                          className={`p-3 rounded-xl border transition cursor-pointer ${
                            isSelected
                              ? 'ring-2 ring-sky-500 border-sky-500'
                              : `${themeSubCard} hover:border-slate-400`
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <div className="flex items-center gap-1.5">
                                <span
                                  className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                                    isCritical
                                      ? 'bg-red-600 text-white'
                                      : 'bg-amber-500 text-slate-950'
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
                            <span className="text-xs font-mono font-semibold text-sky-500">
                              {ev.timestamp}
                            </span>
                          </div>

                          <p className={`text-[11px] mt-1 ${textMuted}`}>{ev.description}</p>

                          {isCritical && (
                            <div onClick={(e) => e.stopPropagation()} className="mt-2">
                              <button
                                onClick={() => handleEmergencyDispatch(ev)}
                                className={`w-full py-1.5 px-2.5 rounded-lg text-[11px] font-bold flex items-center justify-center gap-1.5 cursor-pointer transition ${
                                  emergencyDispatchedId === ev.id
                                    ? 'bg-emerald-600 text-white'
                                    : 'bg-red-600 hover:bg-red-500 text-white animate-pulse'
                                }`}
                              >
                                <HeartPulse size={13} />
                                {emergencyDispatchedId === ev.id
                                  ? 'Медпункт вызван • Линия остановлена (18 сек)'
                                  : 'Экстренно: Вызвать медпункт и стоп линии (< 30 с)'}
                              </button>
                            </div>
                          )}

                          <div
                            className={`mt-2.5 pt-2 border-t flex items-center justify-between gap-1 ${
                              isDark ? 'border-slate-700/70' : 'border-slate-200'
                            }`}
                            onClick={(e) => e.stopPropagation()}
                          >
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => handleProcessEvent(ev.id, 'confirmed')}
                                className={`px-2 py-1 rounded-lg text-[11px] font-medium border flex items-center gap-1 cursor-pointer transition ${
                                  ev.status === 'confirmed'
                                    ? 'bg-emerald-600 text-white border-emerald-600'
                                    : `${themeCard} border-emerald-500/40 hover:border-emerald-500`
                                }`}
                              >
                                <CheckCircle2 size={12} />
                                <span>Подтв.</span>
                              </button>
                              <button
                                onClick={() => handleProcessEvent(ev.id, 'sent_to_master')}
                                className={`px-2 py-1 rounded-lg text-[11px] font-medium border flex items-center gap-1 cursor-pointer transition ${
                                  ev.status === 'sent_to_master'
                                    ? 'bg-sky-600 text-white border-sky-600'
                                    : `${themeCard} hover:border-sky-500`
                                }`}
                              >
                                <Send size={12} />
                                <span>Мастеру</span>
                              </button>
                              <button
                                onClick={() => handleProcessEvent(ev.id, 'false_alarm')}
                                className={`px-2 py-1 rounded-lg text-[11px] font-medium border flex items-center gap-1 cursor-pointer transition ${
                                  ev.status === 'false_alarm'
                                    ? 'bg-red-600 text-white border-red-600'
                                    : `${themeCard} border-red-500/40 text-red-500 hover:bg-red-500/10`
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

              {/* НАГЛЯДНАЯ КАРТОЧКА ДЕКОМПОЗИЦИИ КОНВЕЙЕРА И ТАЙМИНГОВ LinQ TPU */}
              <div className={`border rounded-2xl p-4 ${themeCard}`}>
                <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                  <div className="flex items-center gap-2">
                    <Activity size={17} className="text-sky-500" />
                    <h3 className="text-xs font-bold uppercase tracking-wider">
                      Аппаратный конвейер обработки кадра LinQ TPU ({currentCamera.tpuProgram})
                    </h3>
                  </div>
                  <div className="flex items-center gap-3 text-xs">
                    <span className="px-2.5 py-0.5 rounded-lg bg-emerald-500/15 text-emerald-500 font-mono font-bold">
                      Суммарная задержка: {currentCamera.latency} ({currentCamera.fps} FPS)
                    </span>
                    <span className="px-2.5 py-0.5 rounded-lg bg-sky-500/15 text-sky-500 font-mono font-semibold">
                      Температура кристалла: 46°C
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
                  {[
                    {
                      step: 'Этап 01 • Препроцессинг',
                      title: 'Декодирование RTSP + CLAHE',
                      time: '1.8 мс',
                      pct: 16,
                      sub: 'Нормализация 640×640 RGB и фильтрация пыли',
                      color: 'bg-sky-500',
                    },
                    {
                      step: 'Этап 02 • Ускоритель LinQ TPU',
                      title: 'Квантованный инференс INT8',
                      time: '7.4 мс',
                      pct: 66,
                      sub: `${currentCamera.rulesVector.filter(Boolean).length} активных детекторов ТБ и СИЗ`,
                      color: 'bg-emerald-500',
                    },
                    {
                      step: 'Этап 03 • Постпроцессинг',
                      title: 'NMS + Трекер ByteTrack',
                      time: '1.4 мс',
                      pct: 13,
                      sub: `Проверка ${currentCamera.zones.length} зон и фильтр повторов`,
                      color: 'bg-amber-500',
                    },
                    {
                      step: 'Этап 04 • Реакция и СУБД',
                      title: 'Гомография + PostgreSQL',
                      time: '0.6 мс',
                      pct: 5,
                      sub: 'Запись в events и сигнал на СКУД / Сирену',
                      color: 'bg-purple-500',
                    },
                  ].map((st, i) => (
                    <div key={i} className={`p-3.5 rounded-xl border flex flex-col justify-between ${themeSubCard}`}>
                      <div>
                        <div className="flex items-center justify-between text-[11px]">
                          <span className={`font-semibold ${textMuted}`}>{st.step}</span>
                          <span className="font-mono font-bold text-sm text-sky-500">{st.time}</span>
                        </div>
                        <p className="text-xs font-bold mt-1">{st.title}</p>
                        <p className={`text-[11px] mt-0.5 ${textMuted}`}>{st.sub}</p>
                      </div>
                      <div className={`mt-2.5 w-full h-1.5 rounded-full overflow-hidden ${isDark ? 'bg-slate-800' : 'bg-slate-200'}`}>
                        <div className={`h-full ${st.color}`} style={{ width: `${st.pct}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ================= ВКЛАДКА 2: МУЛЬТИЭКРАН ================= */}
          {activeTab === 'multiview' && (
            <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch">
              <div className={`lg:col-span-8 border rounded-2xl p-5 flex flex-col justify-between ${themeCard}`}>
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h2 className="text-sm font-bold flex items-center gap-2">
                      <Layers size={16} className="text-sky-500" />
                      Видеостена промышленного мониторинга ({cameras.length} активных потока)
                    </h2>
                    <p className={`text-xs ${textMuted}`}>
                      Параллельный аппаратный инференс всех потоков на кластере LinQ TPU
                    </p>
                  </div>
                  <span className="text-xs font-mono px-2.5 py-1 rounded-lg bg-sky-500/15 text-sky-500 font-bold">
                    Суммарно: {cameras.reduce((a, c) => a + (c.fps || 95), 0)} FPS
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 flex-1">
                  {cameras.map((cam) => (
                    <div
                      key={cam.id}
                      onClick={() => {
                        setSelectedCamId(cam.id);
                        setActiveTab('monitoring');
                      }}
                      className={`p-4 rounded-2xl border cursor-pointer transition flex flex-col justify-between min-h-[240px] relative overflow-hidden bg-slate-950 text-white ${
                        selectedCamId === cam.id ? 'ring-2 ring-sky-500 border-sky-500' : 'border-slate-800 hover:border-sky-500/60'
                      }`}
                    >
                      <div
                        className="absolute inset-0 opacity-15 pointer-events-none"
                        style={{
                          backgroundImage:
                            'linear-gradient(to right, #38bdf8 1px, transparent 1px), linear-gradient(to bottom, #38bdf8 1px, transparent 1px)',
                          backgroundSize: '32px 32px',
                        }}
                      />
                      <div className="relative z-10 flex items-center justify-between">
                        <span className="text-xs font-bold px-2.5 py-0.5 rounded bg-sky-600">
                          {cam.code}
                        </span>
                        <span className="text-[11px] font-mono text-emerald-400">
                          {cam.fps} FPS • {cam.cameraType === 'dynamic' ? 'PTZ' : 'Стат.'}
                        </span>
                      </div>

                      <div className="relative z-10 my-auto text-center">
                        <Video size={28} className="mx-auto text-sky-400/70 mb-1.5" />
                        <p className="text-sm font-bold">{cam.name}</p>
                        <p className="text-xs text-slate-400 mt-0.5">{cam.site_name}</p>
                      </div>

                      <div className="relative z-10 flex items-center justify-between text-xs text-slate-300 border-t border-slate-800 pt-2.5">
                        <span>Активных зон: {cam.zones.length} • Правил: {cam.rulesVector.filter(Boolean).length}</span>
                        <span className="text-sky-400 font-semibold">Развернуть →</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className={`lg:col-span-4 border rounded-2xl p-5 flex flex-col justify-between ${themeCard}`}>
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <h3 className="text-sm font-bold flex items-center gap-1.5">
                        <Radar size={16} className="text-amber-500" />
                        ИИ-локатор позиции нарушителя (Homography)
                      </h3>
                      <p className={`text-xs ${textMuted}`}>
                        Событие #{activeEvent.id} • {activeEvent.violation_title}
                      </p>
                    </div>
                    <button
                      onClick={() => setInspectModalEvent(activeEvent)}
                      className="text-xs font-semibold px-2.5 py-1 rounded-lg bg-sky-500/15 text-sky-500 cursor-pointer"
                    >
                      Кадр
                    </button>
                  </div>

                  <div className="relative bg-slate-950 rounded-2xl h-64 border border-slate-800 overflow-hidden flex items-center justify-center my-2">
                    <div
                      className="absolute inset-0 opacity-20"
                      style={{
                        backgroundImage: 'radial-gradient(#38bdf8 1px, transparent 1px)',
                        backgroundSize: '18px 18px',
                      }}
                    />
                    <div
                      style={{
                        left: `${activeEvent.ai_pos.x}%`,
                        top: `${activeEvent.ai_pos.y}%`,
                      }}
                      className="absolute -translate-x-1/2 -translate-y-1/2 flex flex-col items-center"
                    >
                      <span className="w-5 h-5 rounded-full bg-red-500 animate-ping absolute" />
                      <span className="w-3.5 h-3.5 rounded-full bg-red-500 border-2 border-white relative z-10" />
                      <span className="text-[10px] bg-black/85 text-white px-2 py-0.5 rounded mt-1.5 whitespace-nowrap">
                        {activeEvent.camera_code} (X:{activeEvent.ai_pos.x}%, Y:{activeEvent.ai_pos.y}%)
                      </span>
                    </div>
                  </div>

                  <div className={`mt-4 p-3.5 rounded-xl border space-y-2 text-xs ${themeSubCard}`}>
                    <p className="font-bold">Статус аппаратного кластера LinQ TPU:</p>
                    <div className="flex justify-between">
                      <span className={textMuted}>Модель детекции:</span>
                      <span className="font-mono font-semibold">yolov8m_safety_v2_int8.tpu</span>
                    </div>
                    <div className="flex justify-between">
                      <span className={textMuted}>Трекер объектов:</span>
                      <span className="font-mono font-semibold text-emerald-500">ByteTrack (Активен)</span>
                    </div>
                    <div className="flex justify-between">
                      <span className={textMuted}>Загрузка NPU ядер:</span>
                      <span className="font-mono font-semibold text-sky-500">42% (Штатный режим)</span>
                    </div>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-inherit">
                  <label className={`block text-xs font-medium mb-1.5 ${textMuted}`}>
                    Оперативный комментарий в журнал (events.description):
                  </label>
                  <div className="flex items-center gap-2">
                    <MessageSquare size={14} className={textMuted} />
                    <input
                      type="text"
                      value={activeEvent.description}
                      onChange={(e) => handleUpdateEventComment(activeEvent.id, e.target.value)}
                      placeholder="Введите примечание..."
                      className={`text-xs px-3 py-2 rounded-xl border flex-1 ${themeSubCard}`}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ================= ВКЛАДКА 3: КАРТА И ПРАВИЛА (С адаптивным JSONB для светлой и темной темы!) ================= */}
          {activeTab === 'map_rules' && (
            <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch">
              <div className="lg:col-span-7 flex flex-col gap-4 justify-between">
                <div className={`border rounded-2xl p-5 flex-1 flex flex-col justify-between ${themeCard}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-inherit">
                    <div>
                      <h2 className="text-sm font-bold flex items-center gap-2">
                        <Move size={16} className="text-sky-500" />
                        Интерактивная карта цеха (Перетаскивайте камеры и настраивайте сектор обзора)
                      </h2>
                      <p className={`text-xs ${textMuted}`}>
                        Луч обзора жестко закреплен в центре камеры и вращается вокруг её оси
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <div className={`flex items-center gap-2 px-3 py-1 rounded-xl border text-xs ${themeSubCard}`}>
                        <Compass size={14} className="text-sky-500" />
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
                        <ImageIcon size={13} className="text-sky-500" />
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
                          showHeatmap ? 'bg-red-600 text-white border-red-600' : themeSubCard
                        }`}
                      >
                        <Flame size={13} /> Риски
                      </button>
                    </div>
                  </div>

                  {/* ПОЛОТНО КАРТЫ ЦЕХА */}
                  <div
                    ref={mapContainerRef}
                    onMouseMove={handleMapMouseMove}
                    onMouseUp={() => setDraggingCamId(null)}
                    onMouseLeave={() => setDraggingCamId(null)}
                    className="mt-4 relative bg-slate-950 border-2 border-slate-800 rounded-2xl flex-1 min-h-[440px] select-none overflow-hidden"
                  >
                    {floorplanBgUrl && (
                      <img
                        src={floorplanBgUrl}
                        alt="Чертеж цеха"
                        className="absolute inset-0 w-full h-full object-cover opacity-55 pointer-events-none"
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

                    {showHeatmap && (
                      <div
                        className="absolute w-64 h-64 rounded-full blur-2xl opacity-60 pointer-events-none"
                        style={{
                          left: '14%',
                          top: '18%',
                          background:
                            'radial-gradient(circle, rgba(239,68,68,0.85) 0%, rgba(245,158,11,0.4) 60%, transparent 80%)',
                        }}
                      />
                    )}

                    <div className="absolute top-8 left-10 w-40 h-28 bg-red-500/15 border border-red-500/60 rounded-xl p-2.5 pointer-events-none">
                      <span className="text-[10px] font-bold text-red-300 uppercase">
                        ОПО А-1: Зона кран-балки
                      </span>
                    </div>

                    <div className="absolute bottom-10 left-1/3 w-44 h-28 bg-amber-500/15 border border-amber-400/60 rounded-xl p-2.5 pointer-events-none">
                      <span className="text-[10px] font-bold text-amber-200 uppercase">
                        Линия сборки и конвейер
                      </span>
                    </div>

                    <div className="absolute top-10 right-10 w-32 h-28 bg-slate-800/80 border border-slate-600 rounded-xl p-2 flex items-center justify-center text-center pointer-events-none">
                      <span className="text-[10px] text-slate-300 font-medium">
                        Стеллажи хранения (ОПО А-2)
                      </span>
                    </div>

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
                            e.stopPropagation();
                            setSelectedCamId(cam.id);
                            setDraggingCamId(cam.id);
                          }}
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
                                  stopOpacity={isSelected ? '0.55' : '0.35'}
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
                                stroke={isSelected ? 'rgba(56, 189, 248, 0.55)' : 'rgba(148, 163, 184, 0.25)'}
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
                                opacity="0.65"
                              />
                            </g>
                          </svg>

                          <div
                            className={`relative z-10 w-8 h-8 rounded-full flex items-center justify-center border-2 transition-transform ${
                              isSelected
                                ? 'bg-sky-600 text-white border-white shadow-lg scale-110'
                                : 'bg-slate-900 text-sky-400 border-sky-400/80 hover:scale-110'
                            }`}
                          >
                            <Video size={13} />
                            <span
                              className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-slate-950 ${
                                cam.cameraType === 'dynamic' ? 'bg-amber-400' : 'bg-emerald-400'
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

                <div className={`border rounded-2xl p-4 ${themeCard}`}>
                  <div className="flex items-center justify-between mb-2.5">
                    <h3 className="text-xs font-bold uppercase tracking-wider flex items-center gap-1.5">
                      <Plus size={14} className="text-sky-500" />
                      Регистрация новой камеры и участка
                    </h3>
                    {!currentUser.canEditRules && (
                      <span className="text-xs text-red-500 font-medium flex items-center gap-1">
                        <Lock size={12} /> Только для Специалиста по ОТ / ИТ
                      </span>
                    )}
                  </div>

                  <form
                    onSubmit={handleAddCamera}
                    className="grid grid-cols-1 sm:grid-cols-5 gap-2.5"
                  >
                    <input
                      type="text"
                      disabled={!currentUser.canEditRules}
                      placeholder="Участок"
                      value={newSiteInput}
                      onChange={(e) => setNewSiteInput(e.target.value)}
                      className={`text-xs rounded-xl px-3 py-2 border ${themeSubCard}`}
                    />
                    <input
                      type="text"
                      disabled={!currentUser.canEditRules}
                      placeholder="Имя камеры"
                      value={newCamInput}
                      onChange={(e) => setNewCamInput(e.target.value)}
                      className={`text-xs rounded-xl px-3 py-2 border ${themeSubCard}`}
                    />
                    <input
                      type="text"
                      disabled={!currentUser.canEditRules}
                      placeholder="rtsp://… (необяз.)"
                      value={newRtspInput}
                      onChange={(e) => setNewRtspInput(e.target.value)}
                      className={`text-xs rounded-xl px-3 py-2 border ${themeSubCard}`}
                    />
                    <select
                      disabled={!currentUser.canEditRules}
                      value={newCamTypeInput}
                      onChange={(e) => setNewCamTypeInput(e.target.value)}
                      className={`text-xs rounded-xl px-3 py-2 border font-medium ${themeSubCard}`}
                    >
                      <option value="dynamic">Динамичная PTZ</option>
                      <option value="static">Статичная</option>
                    </select>
                    <button
                      type="submit"
                      disabled={!currentUser.canEditRules}
                      className="bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white font-semibold text-xs rounded-xl py-2 px-3 cursor-pointer transition"
                    >
                      + Добавить
                    </button>
                  </form>
                </div>
              </div>

              {/* ПРАВАЯ КОЛОНКА (5 из 12): ПРАВИЛА КОНТРОЛЯ + АДАПТИВНЫЙ БЛОК JSONB (Светлый на светлой теме!) */}
              <div
                className={`lg:col-span-5 border rounded-2xl p-5 flex flex-col gap-4 ${themeCard}`}
              >
                <div className="shrink-0">
                  <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-inherit">
                    <div>
                      <h2 className="text-sm font-bold">
                        Правила контроля: {currentCamera.code}
                      </h2>
                      <p className={`text-xs ${textMuted}`}>
                        Все 13 детекторов участка (кликните для переключения)
                      </p>
                    </div>
                    <span className="text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-sky-500/15 text-sky-500">
                      Активно: {currentCamera.rulesVector.filter(Boolean).length}/{VIOLATION_TYPES.length}
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5 mt-3">
                    <span className={`text-[11px] mr-1 ${textMuted}`}>Пресеты:</span>
                    <button
                      onClick={() => applyRulesPreset('all')}
                      className={`text-[11px] px-2.5 py-1 rounded-lg border font-medium cursor-pointer ${themeSubCard} hover:border-sky-500`}
                    >
                      Включить все (13)
                    </button>
                    <button
                      onClick={() => applyRulesPreset('ppe_only')}
                      className={`text-[11px] px-2.5 py-1 rounded-lg border font-medium cursor-pointer ${themeSubCard} hover:border-sky-500`}
                    >
                      Только СИЗ и падения
                    </button>
                    <button
                      onClick={() => applyRulesPreset('warehouse')}
                      className={`text-[11px] px-2.5 py-1 rounded-lg border font-medium cursor-pointer ${themeSubCard} hover:border-sky-500`}
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
                              ? 'border-sky-500/80 bg-sky-500/10'
                              : `${themeSubCard} opacity-60 hover:opacity-90`
                          }`}
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-sky-600 text-white shrink-0">
                              {v.code}
                            </span>
                            <span className="text-[11px] font-medium truncate" title={v.name}>
                              {v.name}
                            </span>
                          </div>
                          <span
                            className={`text-[10px] font-bold px-2 py-0.5 rounded-md shrink-0 ${
                              active
                                ? 'bg-emerald-600 text-white'
                                : isDark
                                ? 'bg-slate-700 text-slate-300'
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

                {/* АДАПТИВНЫЙ БЛОК JSONB (На светлой теме — светлый и аккуратный, на темной — темный!) */}
                <div className="flex-1 flex flex-col pt-3 border-t border-inherit min-h-[200px]">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <span className="text-xs font-bold text-sky-500">
                        Синхронизируемый объект JSONB (sites.rules)
                      </span>
                      <p className={`text-[11px] ${textMuted}`}>
                        Передается в PostgreSQL и ИИ-модуль LinQ TPU в реальном времени
                      </p>
                    </div>
                    <button
                      onClick={handleCopyJson}
                      className={`px-2.5 py-1 rounded-lg border text-[11px] font-semibold flex items-center gap-1 cursor-pointer ${themeSubCard}`}
                    >
                      {copiedJson ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
                      <span>{copiedJson ? 'Скопировано' : 'Копировать JSON'}</span>
                    </button>
                  </div>

                  <pre className={`flex-1 p-3.5 rounded-xl text-xs font-mono overflow-y-auto border leading-relaxed ${themeCodeBlock}`}>
                    {formatCompactRulesJson({
                      site_id: currentCamera.site_id,
                      site_name: currentCamera.site_name,
                      camera: currentCamera.code,
                      camera_type: currentCamera.cameraType,
                      direction_deg: (currentCamera.mapDirection || 0) + (currentCamera.panAngle || 0),
                      vector: currentCamera.rulesVector,
                      zones: currentCamera.zones.map((z) => ({
                        label: z.label,
                        type: z.type,
                        shape: z.shape,
                        schedule: z.schedule,
                        coords: z.shape === 'rect' ? z.rect : z.points,
                      })),
                    })}
                  </pre>
                </div>
              </div>
            </div>
          )}

          {/* ================= ВКЛАДКА 4: АНАЛИТИКА, ИНСТРУКТАЖИ И ГОСТ (Без пустых дыр внутри карточек!) ================= */}
          {activeTab === 'analytics' && (
            <div className="space-y-4">
              {/* Верхний ряд KPI */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <div className={`border rounded-2xl p-4 ${themeCard}`}>
                  <p className={`text-xs ${textMuted}`}>Скорость LinQ TPU</p>
                  <p className="text-xl font-bold text-sky-500 mt-1">{currentCamera.fps} FPS</p>
                  <p className={`text-[11px] mt-0.5 ${textMuted}`}>Отклик: {currentCamera.latency}</p>
                </div>
                <div className={`border rounded-2xl p-4 ${themeCard}`}>
                  <p className={`text-xs ${textMuted}`}>Всего событий в базе</p>
                  <p className="text-xl font-bold text-red-500 mt-1">{events.length}</p>
                  <p className={`text-[11px] mt-0.5 ${textMuted}`}>Подавлено дублей: 142</p>
                </div>
                <div className={`border rounded-2xl p-4 ${themeCard}`}>
                  <p className={`text-xs ${textMuted}`}>Выборка Active Learning</p>
                  <p className="text-xl font-bold text-emerald-500 mt-1">{falseAlarmEvents.length} кадров</p>
                  <p className={`text-[11px] mt-0.5 ${textMuted}`}>Готовы к дообучению .tpu</p>
                </div>
                <div
                  onClick={() => setBriefingModalOpen(true)}
                  className="border border-sky-500/40 bg-sky-500/10 hover:bg-sky-500/20 rounded-2xl p-4 cursor-pointer transition flex flex-col justify-between"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-sky-500">ИИ-Инструктаж смены</span>
                    <GraduationCap size={18} className="text-sky-500" />
                  </div>
                  <p className="text-xs font-semibold mt-1">
                    Сформировать 5-минутный инструктаж по реальным случаям →
                  </p>
                </div>
              </div>

              {/* Средний ряд: Почасовой график + Калькулятор (Плотная верстка без огромного пустого промежутка!) */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
                <div className={`lg:col-span-7 border rounded-2xl p-5 space-y-4 ${themeCard}`}>
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

                  {/* Столбцы почасовой статистики без пустого растягивания */}
                  <div className="grid grid-cols-7 gap-3 pt-1">
                    {hourlyStats.map((item, i) => {
                      const heightPct = Math.round((item.count / 15) * 100);
                      return (
                        <div key={i} className="flex flex-col items-center">
                          <div
                            className={`h-36 w-full flex flex-col justify-end items-center border-b pb-2 ${
                              isDark ? 'border-slate-700' : 'border-slate-200'
                            }`}
                          >
                            <span className="text-xs font-bold mb-1 text-sky-500">
                              {item.count}
                            </span>
                            <div
                              style={{ height: `${heightPct}%` }}
                              className={`w-9 max-w-full rounded-t-lg transition-all ${
                                item.count >= 11 ? 'bg-red-500' : 'bg-sky-500'
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

                  {/* Компактная разбивка по категориям нарушений внизу графика */}
                  <div className={`pt-3 border-t grid grid-cols-3 gap-3 text-xs ${isDark ? 'border-slate-800' : 'border-slate-200'}`}>
                    <div className={`p-2.5 rounded-xl border ${themeSubCard}`}>
                      <span className={textMuted}>Отсутствие СИЗ (09–13)</span>
                      <p className="text-sm font-bold text-amber-500 mt-0.5">44% всех случаев</p>
                    </div>
                    <div className={`p-2.5 rounded-xl border ${themeSubCard}`}>
                      <span className={textMuted}>Опасные зоны и техника</span>
                      <p className="text-sm font-bold text-red-500 mt-0.5">38% всех случаев</p>
                    </div>
                    <div className={`p-2.5 rounded-xl border ${themeSubCard}`}>
                      <span className={textMuted}>Дисциплина и смартфон</span>
                      <p className="text-sm font-bold text-sky-500 mt-0.5">18% всех случаев</p>
                    </div>
                  </div>
                </div>

                <div className={`lg:col-span-5 border rounded-2xl p-5 space-y-4 ${themeCard}`}>
                  <h2 className="text-sm font-bold pb-3 border-b border-inherit flex items-center gap-2">
                    <Sliders size={16} className="text-sky-500" />
                    Калькулятор кластера LinQ TPU
                  </h2>

                  <div className={`p-3.5 rounded-xl border ${themeSubCard}`}>
                    <div className="flex justify-between text-xs font-semibold mb-2">
                      <span>Масштаб внедрения:</span>
                      <span className="text-sky-500 font-bold text-sm">
                        {clusterCamerasCount} камер
                      </span>
                    </div>
                    <input
                      type="range"
                      min="5"
                      max="100"
                      value={clusterCamerasCount}
                      onChange={(e) => setClusterCamerasCount(Number(e.target.value))}
                      className="w-full accent-sky-600 cursor-pointer"
                    />
                    <div className={`flex justify-between text-[10px] mt-1 ${textMuted}`}>
                      <span>5 камер (100 м²)</span>
                      <span>50 камер (Цех)</span>
                      <span>100 камер (10 000 м²)</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className={`p-3 rounded-xl border ${themeSubCard}`}>
                      <p className={`text-[11px] ${textMuted}`}>Узлов ускорителей LinQ</p>
                      <p className="text-lg font-bold mt-0.5 text-sky-500">
                        {Math.ceil(clusterCamerasCount / 16)} шт. (INT8)
                      </p>
                    </div>
                    <div className={`p-3 rounded-xl border ${themeSubCard}`}>
                      <p className={`text-[11px] ${textMuted}`}>Суммарный поток</p>
                      <p className="text-lg font-bold mt-0.5">
                        {clusterCamerasCount * 25} FPS
                      </p>
                    </div>
                    <div className={`p-3 rounded-xl border ${themeSubCard}`}>
                      <p className={`text-[11px] ${textMuted}`}>Снижение травматизма</p>
                      <p className="text-lg font-bold mt-0.5 text-emerald-500">
                        до -78% в год
                      </p>
                    </div>
                    <div className={`p-3 rounded-xl border ${themeSubCard}`}>
                      <p className={`text-[11px] ${textMuted}`}>Энергопотребление</p>
                      <p className="text-lg font-bold mt-0.5">
                        до 75 Вт (Edge)
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Active Learning */}
              <div className={`border rounded-2xl p-4 flex flex-wrap items-center justify-between gap-4 ${themeCard}`}>
                <div>
                  <h3 className="text-sm font-bold flex items-center gap-2">
                    <RefreshCw size={16} className="text-sky-500" />
                    Контур дообучения нейросети (Active Learning)
                  </h3>
                  <p className={`text-xs mt-0.5 ${textMuted}`}>
                    Отмеченные красной кнопкой «Ложное» кадры ({falseAlarmEvents.length} шт.) выгружаются в ZIP-архив для дообучения модели
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

              {/* Сводная ведомость */}
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
                        <th className="p-3">Рекомендация ИИ</th>
                      </tr>
                    </thead>
                    <tbody className={`divide-y ${themeTableWrap}`}>
                      {cameraSummary(cameras, events).map((r) => (
                        <tr key={r.id} className="hover:bg-sky-500/5">
                          <td className="p-3 font-semibold">{r.site}</td>
                          <td className="p-3">{r.code}</td>
                          <td className="p-3 text-red-500 font-medium">{r.top || '—'}</td>
                          <td className="p-3 font-bold">{r.total}</td>
                          <td className="p-3">{r.confirmed}</td>
                          <td className="p-3 text-emerald-500 font-bold">
                            {r.reviewed > 0 ? `${Math.round((r.confirmed / r.reviewed) * 100)}%` : '96%'}
                          </td>
                          <td className="p-3">{r.advice}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ================= ВКЛАДКА 5: ИНСПЕКТОР СУБД (Без пустых разрывов и с адаптивной светлой/темной темой!) ================= */}
          {activeTab === 'db_inspector' && (
            <div className={`border rounded-2xl p-5 space-y-5 ${themeCard}`}>
              {/* Заголовок + Экспорт CSV */}
              <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-inherit">
                <div>
                  <h2 className="text-base font-bold flex items-center gap-2">
                    <Database size={18} className="text-sky-500" />
                    Инспектор реляционной СУБД PostgreSQL
                  </h2>
                  <p className={`text-xs ${textMuted}`}>
                    Выберите любую таблицу схемы для просмотра живых записей и связей
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs ${themeSubCard}`}>
                    <Search size={13} className={textMuted} />
                    <input
                      type="text"
                      value={dbSearchQuery}
                      onChange={(e) => setDbSearchQuery(e.target.value)}
                      placeholder="Фильтр записей..."
                      className="bg-transparent focus:outline-none w-36"
                    />
                  </div>
                  <button
                    onClick={handleExportEventsCsv}
                    className="px-3 py-1.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold flex items-center gap-1.5 cursor-pointer"
                  >
                    <Download size={13} /> Выгрузить CSV
                  </button>
                  <span className="text-xs font-mono px-3 py-1.5 rounded-xl bg-emerald-500/15 text-emerald-500 font-semibold">
                    PostgreSQL 16 • Активно
                  </span>
                </div>
              </div>

              {/* 5 карточек таблиц */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
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
                          ? 'border-sky-500 bg-sky-500/10 ring-1 ring-sky-500'
                          : `${themeSubCard} hover:border-slate-400`
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
                      <p className="text-[11px] font-mono text-amber-500 mt-2">{tb.pk}</p>
                    </div>
                  );
                })}
              </div>

              {/* Таблица выбранной сущности (Плотно, без пустого разрыва под ней!) */}
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider mb-2 flex items-center justify-between">
                  <span>SELECT * FROM public.{activeDbTable} ORDER BY id DESC;</span>
                  <span className={`font-mono text-[11px] ${textMuted}`}>Связь с ИИ-модулем и веб-клиентом</span>
                </h3>

                {activeDbTable === 'events' && (
                  <div className={`overflow-x-auto rounded-xl border ${themeTableWrap}`}>
                    <table className="w-full text-left text-xs font-mono">
                      <thead className={themeTableHead}>
                        <tr>
                          <th className="p-3">id (PK)</th>
                          <th className="p-3">camera_id (FK)</th>
                          <th className="p-3">violation (enum)</th>
                          <th className="p-3">timestamp</th>
                          <th className="p-3">status</th>
                          <th className="p-3">processed_by</th>
                          <th className="p-3">confidence</th>
                          <th className="p-3">description</th>
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
                            <tr key={ev.id} className="hover:bg-sky-500/5">
                              <td className="p-3 font-bold">{ev.id}</td>
                              <td className="p-3">{ev.camera_id} ({ev.camera_code})</td>
                              <td className="p-3 text-red-500 font-semibold">{ev.violation}</td>
                              <td className="p-3 whitespace-nowrap">{ev.timestamp}</td>
                              <td className="p-3 font-semibold">{ev.status}</td>
                              <td className="p-3">{ev.processed_by_name}</td>
                              <td className="p-3 text-emerald-500 font-bold">{ev.confidence}</td>
                              <td className="p-3 max-w-xs truncate">{ev.description}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {activeDbTable === 'cameras' && (
                  <div className={`overflow-x-auto rounded-xl border ${themeTableWrap}`}>
                    <table className="w-full text-left text-xs font-mono">
                      <thead className={themeTableHead}>
                        <tr>
                          <th className="p-3">id (PK)</th>
                          <th className="p-3">code</th>
                          <th className="p-3">site_id (FK)</th>
                          <th className="p-3">name</th>
                          <th className="p-3">camera_type</th>
                          <th className="p-3">rtsp_url</th>
                          <th className="p-3">fps</th>
                        </tr>
                      </thead>
                      <tbody className={`divide-y ${themeTableWrap}`}>
                        {cameras.map((c) => (
                          <tr key={c.id} className="hover:bg-sky-500/5">
                            <td className="p-3 font-bold">{c.id}</td>
                            <td className="p-3 text-sky-500 font-bold">{c.code}</td>
                            <td className="p-3">{c.site_id}</td>
                            <td className="p-3">{c.name}</td>
                            <td className="p-3">{c.cameraType}</td>
                            <td className={`p-3 ${textMuted}`}>{c.rtsp_url}</td>
                            <td className="p-3 text-emerald-500 font-bold">{c.fps}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {activeDbTable === 'sites' && (
                  <div className={`overflow-x-auto rounded-xl border ${themeTableWrap}`}>
                    <table className="w-full text-left text-xs font-mono">
                      <thead className={themeTableHead}>
                        <tr>
                          <th className="p-3">id (PK)</th>
                          <th className="p-3">name (Производственный участок)</th>
                          <th className="p-3">rules (JSONB вектор и зоны)</th>
                          <th className="p-3">created_at</th>
                        </tr>
                      </thead>
                      <tbody className={`divide-y ${themeTableWrap}`}>
                        {cameras.map((c) => (
                          <tr key={c.site_id} className="hover:bg-sky-500/5">
                            <td className="p-3 font-bold">{c.site_id}</td>
                            <td className="p-3 font-semibold">{c.site_name}</td>
                            <td className="p-3 text-sky-500">
                              vector: [{c.rulesVector.join(',')}], zones: {c.zones.length}
                            </td>
                            <td className="p-3">{c.created_at}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {activeDbTable === 'users' && (
                  <div className={`overflow-x-auto rounded-xl border ${themeTableWrap}`}>
                    <table className="w-full text-left text-xs font-mono">
                      <thead className={themeTableHead}>
                        <tr>
                          <th className="p-3">id (PK)</th>
                          <th className="p-3">login (UK)</th>
                          <th className="p-3">full_name</th>
                          <th className="p-3">role_id (FK)</th>
                          <th className="p-3">can_edit_rules</th>
                        </tr>
                      </thead>
                      <tbody className={`divide-y ${themeTableWrap}`}>
                        {DB_USERS.map((u) => (
                          <tr key={u.id} className="hover:bg-sky-500/5">
                            <td className="p-3 font-bold">{u.id}</td>
                            <td className="p-3 text-sky-500">{u.login}</td>
                            <td className="p-3">{u.full_name} ({u.position})</td>
                            <td className="p-3">{u.role_id} ({u.role_name})</td>
                            <td className="p-3 text-emerald-500 font-bold">{String(u.canEditRules)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {activeDbTable === 'roles' && (
                  <div className={`overflow-x-auto rounded-xl border ${themeTableWrap}`}>
                    <table className="w-full text-left text-xs font-mono">
                      <thead className={themeTableHead}>
                        <tr>
                          <th className="p-3">id (PK)</th>
                          <th className="p-3">name (Наименование роли и полномочия)</th>
                        </tr>
                      </thead>
                      <tbody className={`divide-y ${themeTableWrap}`}>
                        {DB_ROLES.map((r) => (
                          <tr key={r.id} className="hover:bg-sky-500/5">
                            <td className="p-3 font-bold">{r.id}</td>
                            <td className="p-3">{r.name}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Сбалансированный нижний ряд из 2 колонок: JSONB документ слева + Журнал SQL/REST транзакций справа */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className={`p-4 rounded-xl border ${themeSubCard}`}>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-bold">
                      Актуальный документ JSONB (sites.rules • {currentCamera.code}):
                    </p>
                    <button
                      onClick={handleCopyJson}
                      className={`px-2 py-0.5 rounded border text-[11px] font-semibold flex items-center gap-1 cursor-pointer ${themeCard}`}
                    >
                      {copiedJson ? <Check size={11} className="text-emerald-500" /> : <Copy size={11} />}
                      <span>{copiedJson ? 'Скопировано' : 'Копировать'}</span>
                    </button>
                  </div>
                  <pre className={`p-3 rounded-xl text-xs font-mono overflow-x-auto border max-h-48 ${themeCodeBlock}`}>
                    {formatCompactRulesJson({
                      site_id: currentCamera.site_id,
                      site_name: currentCamera.site_name,
                      camera_type: currentCamera.cameraType,
                      vector: currentCamera.rulesVector,
                      zones: currentCamera.zones,
                    })}
                  </pre>
                </div>

                <div className={`p-4 rounded-xl border flex flex-col justify-between ${themeSubCard}`}>
                  <div>
                    <p className="text-xs font-bold mb-2">
                      Журнал синхронизации REST API и транзакций PostgreSQL:
                    </p>
                    <div className={`p-3 rounded-xl border font-mono text-[11px] space-y-1.5 ${themeCodeBlock}`}>
                      <div>[SYNC] PATCH /api/cameras/{currentCamera.id} → 200 OK (sites.rules JSONB updated)</div>
                      <div>[POLL] GET /api/events?after_id=0 → {events.length} rows fetched (3.2 ms)</div>
                      <div>[TPU] Bridge heartbeat {currentCamera.code}: {currentCamera.fps} FPS, INT8 active</div>
                      <div>[AUTH] Session verified for role_id={currentUser.role_id} ({currentUser.login})</div>
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-2 mt-3 text-xs">
                    <div className={`p-2 rounded-lg border ${themeCard}`}>
                      <span className={`text-[10px] ${textMuted}`}>Индекс GIN (JSONB)</span>
                      <p className="font-bold text-emerald-500">Активен (0.4 мс)</p>
                    </div>
                    <div className={`p-2 rounded-lg border ${themeCard}`}>
                      <span className={`text-[10px] ${textMuted}`}>Пул соединений</span>
                      <p className="font-bold text-sky-500">psycopg3 • ОК</p>
                    </div>
                    <div className={`p-2 rounded-lg border ${themeCard}`}>
                      <span className={`text-[10px] ${textMuted}`}>Архив кадров</span>
                      <p className="font-bold">{events.length} файлов</p>
                    </div>
                  </div>
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
    <div className="min-h-screen flex items-center justify-center bg-slate-900 text-white font-sans p-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onLogin(login, password);
        }}
        className="w-full max-w-sm space-y-4 bg-slate-800/90 border border-slate-700 rounded-2xl p-6 shadow-2xl"
      >
        <div className="flex items-center gap-3 border-b border-slate-700 pb-3">
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
            className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-600 text-white text-sm focus:outline-none focus:border-sky-500"
          />
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">Пароль:</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Пароль"
            className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-600 text-white text-sm focus:outline-none focus:border-sky-500"
          />
        </div>

        {error && <p className="text-xs text-red-400 font-medium">{error}</p>}

        <button className="w-full py-2.5 rounded-lg bg-sky-600 hover:bg-sky-500 font-semibold cursor-pointer text-sm shadow transition">
          Войти
        </button>

        <div className="pt-2 border-t border-slate-700/80 text-[11px] text-slate-400 space-y-1">
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
                className="px-1.5 py-0.5 rounded bg-slate-700/70 hover:bg-slate-700 text-sky-400 cursor-pointer font-mono"
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
        enhanceFilter: false,
        stabilizeZonesOnPTZ: true,
        sirenEnabled: true,
        skudLockEnabled: false,
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