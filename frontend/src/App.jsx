
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
  UserCheck,
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
  KeyRound,
  FlipHorizontal,
  Play,
  Crosshair,
} from 'lucide-react';

// Типы нарушений (events.violation ENUM); индекс = позиция в векторе правил камеры.
// ai: есть ли у ИИ-модуля детектор этого типа (09–13 — СИЗ и опасные зоны, добавлены в конец)
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
  NO_HELMET: 'Проверить выдачу касок и допуск на участок',
  NO_VEST: 'Проверить выдачу сигнальных жилетов',
  DANGER_ZONE: 'Оградить опасную зону физически',
  DANGER_PROXIMITY: 'Разделить пешеходные и транспортные пути',
  SMOKING_FIRE: 'Проверить места для курения и пожарный пост',
  PHONE_USAGE: 'Напомнить о запрете телефонов у оборудования',
  RUNNING: 'Разметить пешеходные маршруты',
  PERSON_FALL: 'Проверить покрытие пола и проходы',
  NO_GLOVES: 'Проверить выдачу перчаток',
  NO_GOGGLES: 'Проверить выдачу защитных очков',
};

// Сводка по камерам из журнала: всего, подтверждено, самое частое нарушение (ложные срабатывания не считаются)
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

// Короткий звуковой сигнал о новом нарушении («Светозвуковое оповещение на участке»)
function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'square';
    osc.frequency.value = 880;
    gain.gain.value = 0.06;
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.35);
    osc.onended = () => ctx.close();
  } catch {
    /* браузер запретил звук до первого клика — не страшно */
  }
}

const DB_USERS = [
  { id: 1, login: 'mikhalyich_ot', full_name: 'Кузьмин М.П.', position: 'Специалист по ОТ', role_id: 1, role_name: 'Роль 1: Специалист по ОТ', canEditRules: true },
  { id: 2, login: 'disp_smena1', full_name: 'Соколов А.В.', position: 'Диспетчер ЦУП', role_id: 3, role_name: 'Роль 3: Диспетчер', canEditRules: false },
  { id: 3, login: 'master_ceh1', full_name: 'Громов И.С.', position: 'Мастер смены', role_id: 2, role_name: 'Роль 2: Мастер участка', canEditRules: false },
  { id: 4, login: 'it_linq_admin', full_name: 'Дехтерюк Д.К.', position: 'ИТ-Инженер LinQ', role_id: 7, role_name: 'Роль 7: ИТ-интегратор', canEditRules: true },
];

// Упорядочивание вершин многоугольника по кругу (исключает самопересечения)
function sortPolygonPoints(points) {
  if (!points || points.length < 3) return points || [];
  const cx = points.reduce((acc, p) => acc + p.x, 0) / points.length;
  const cy = points.reduce((acc, p) => acc + p.y, 0) / points.length;
  return [...points].sort(
    (a, b) => Math.atan2(a.y - cy, a.x - cx) - Math.atan2(b.y - cy, b.x - cx)
  );
}

// Геометрическая проверка попадания точки (рабочего) внутрь полигона (Ray-Casting)
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

// Проверка пересечения бокса сотрудника с зонами камеры
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

// ТОЧНАЯ ПОПИКСЕЛЬНАЯ КОПИЯ ОРИГИНАЛЬНОГО ЛОГОТИПА LinQ.
function LinQExactLogo({ forceDarkText = false, isDark = false }) {
  const mainColor = forceDarkText ? '#1E242B' : isDark ? '#FFFFFF' : '#1E242B';
  const bluePixel = '#2589DF';
  return (
    <svg
      width="96"
      height="56"
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

// ОФИЦИАЛЬНЫЙ ОТЧЕТ ПО ГОСТ Р 7.0.97-2016 И ПРИКАЗУ РОСТЕХНАДЗОРА ОТ 11.12.2020 № 518
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
                  {cam.ai?.online ? `Исправен (${cam.fps} FPS)` : 'ИИ не подключён'}
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
        <p className="text-[9.5pt] mt-2">
          <strong>Заключение службы производственного контроля:</strong> наибольшая частота нарушений фиксируется в интервале пересменки (08:00–10:00). На основании данных АПК «LinQ Vision Guard» введен обязательный предсменный целевой инструктаж и автоматическое ограничение допуска через СКУД при отсутствии СИЗ.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-8 pt-4 border-t border-black text-[10pt] break-inside-avoid">
        <div>
          <p className="font-bold">Ответственный за осуществление производственного контроля:</p>
          <p className="mt-4">___________________ / {currentUser.full_name} /</p>
          <p className="text-[8.5pt] text-slate-600">(личная подпись, расшифровка подписи)</p>
        </div>
        <div>
          <p className="font-bold">Представитель ИТ-службы эксплуатации LinQ TPU:</p>
          <p className="mt-4">___________________ / Дехтерюк Д.К. /</p>
          <p className="text-[8.5pt] text-slate-600">(личная подпись, расшифровка подписи)</p>
        </div>
      </div>
    </div>
  );
}

// Поля камеры, которые сохраняются на сервере (остальное — служебная симуляция интерфейса)
const PERSIST = ['name', 'cameraType', 'panAngle', 'tiltAngle', 'zoomLevel', 'autoPatrol', 'rtsp_url', 'is_active', 'rulesVector', 'mapPos', 'zones'];
const snap = (c) => Object.fromEntries(PERSIST.map((k) => [k, JSON.stringify(c[k])]));

// заглушка, пока в журнале нет ни одного события
const NO_EVENT = { id: '—', violation_title: 'Событий пока нет', ai_pos: { x: 50, y: 50 }, camera_code: '—', description: '', confidence: 0, status: 'none' };

function Dashboard({ user: currentUser, initial, onLogout }) {
  const [isDark, setIsDark] = useState(false);
  const [eyeComfort, setEyeComfort] = useState(false);
  const [activeTab, setActiveTab] = useState('monitoring');
  const [showGostPreviewModal, setShowGostPreviewModal] = useState(false);
  const [inspectModalEvent, setInspectModalEvent] = useState(null);
  const [retrainStatus, setRetrainStatus] = useState(null);

  const [cameras, setCameras] = useState(initial.cameras);
  const [selectedCamId, setSelectedCamId] = useState(initial.cameras[0]?.id);
  const [events, setEvents] = useState(initial.events);
  const [selectedEventId, setSelectedEventId] = useState(initial.events[0]?.id);
  const [filterStatus, setFilterStatus] = useState('all');

  // ai — живое видео с разметкой от ИИ-модуля; simulation / webcam / file — демонстрация без ИИ
  const [videoSource, setVideoSource] = useState('ai');
  const [uploadState, setUploadState] = useState(null); // null | 'uploading' | текст ошибки
  const [webcamUnmirrored, setWebcamUnmirrored] = useState(true); // Исправление зеркалирования веб-камеры
  const [uploadedVideoUrl, setUploadedVideoUrl] = useState(null);
  const webcamVideoRef = useRef(null);

  const [enhanceFilter, setEnhanceFilter] = useState(initial.settings.enhanceFilter ?? false);
  const [stabilizeZonesOnPTZ, setStabilizeZonesOnPTZ] = useState(initial.settings.stabilizeZonesOnPTZ ?? true);
  const [sirenEnabled, setSirenEnabled] = useState(initial.settings.sirenEnabled ?? true);
  const [skudLockEnabled, setSkudLockEnabled] = useState(initial.settings.skudLockEnabled ?? false);
  const [simulateWorkersWalk, setSimulateWorkersWalk] = useState(false);

  const [drawMode, setDrawMode] = useState('none'); // none | rect | polygon
  const [newZoneType, setNewZoneType] = useState('danger');
  const [newZoneLabel, setNewZoneLabel] = useState('Зона контроля');
  const [newZoneSchedule, setNewZoneSchedule] = useState('07:55 – 12:00');
  const [dragStart, setDragStart] = useState(null);
  const [dragCurrent, setDragCurrent] = useState(null);
  const [tempPolygon, setTempPolygon] = useState([]);

  // Перетаскивание и ресайз прямоугольников, полигонов, вершин и сотрудников внутри единой сцены
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

  const currentCamera = cameras.find((c) => c.id === selectedCamId) || cameras[0];
  const activeEvent = events.find((e) => e.id === selectedEventId) || events[0] || NO_EVENT;
  const falseAlarmEvents = events.filter((e) => e.status === 'false_alarm');
  const aiMode = videoSource === 'ai';
  const camAi = currentCamera.ai || {};
  const aiOnlineCams = cameras.filter((c) => c.ai?.online);
  const aiBackend = aiOnlineCams[0]?.ai?.backend;
  const frameAspect = camAi.frame ? `${camAi.frame[0]} / ${camAi.frame[1]}` : '16 / 9';

  // Авто-обход поворотной PTZ-камеры
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

  // Автоматическое перемещение рабочих по цеху (для демонстрации вхождения в опасные зоны)
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

  // Проверка пересечения рабочих с опасными зонами: если рабочий зашел в красную зону — запускаем верификацию.
  // Только в режиме симуляции: с живым видео нарушения фиксирует ИИ-модуль
  const collidingDangerWorker = aiMode
    ? null
    : (currentCamera.workers || []).find((w) => {
        const hitZone = checkWorkerZoneCollision(w, currentCamera.zones);
        return hitZone && hitZone.type === 'danger';
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

      const enabledIndices = currentCamera.rulesVector
        .map((v, i) => (v === 1 ? i : null))
        .filter((v) => v !== null);
      const chosenIdx =
        enabledIndices.length > 0
          ? enabledIndices[Math.floor(Math.random() * enabledIndices.length)]
          : 1;
      const vType = VIOLATION_TYPES[chosenIdx];

      api
        .createEvent({
          camera_id: currentCamera.id,
          violation: vType.enumKey,
          confidence: Number((0.92 + Math.random() * 0.07).toFixed(2)),
          ai_pos: { x: Math.floor(25 + Math.random() * 55), y: Math.floor(30 + Math.random() * 50) },
          description: collidingDangerWorker
            ? `Пересечение опасной зоны объектом ${collidingDangerWorker.id} (${currentCamera.code})`
            : `Автофиксация на участке (${currentCamera.code})`,
        })
        .then((ev) => {
          setEvents((prev) => (prev.some((e) => e.id === ev.id) ? prev : [ev, ...prev]));
          setSelectedEventId(ev.id);
        })
        .catch((err) => alert(err.message));
    }
  }, [verifyProgress, isVerifying, currentCamera, collidingDangerWorker]);

  const startIncidentVerification = () => {
    if (isVerifying) return;
    verificationLockRef.current = false;
    setVerifyProgress(10);
    setIsVerifying(true);
  };

  // Точные координаты в мировом слое сцены (корректно учитывают и поворот PTZ, и зум!)
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

  // Свободное движение зон, контуров и рабочих (разрешено заходить за границы кадра от -40% до 140%!)
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

  const handleMapMouseMove = (e) => {
    if (!draggingCamId || !mapContainerRef.current) return;
    const rect = mapContainerRef.current.getBoundingClientRect();
    const x = Math.max(6, Math.min(92, Math.round(((e.clientX - rect.left) / rect.width) * 100)));
    const y = Math.max(8, Math.min(90, Math.round(((e.clientY - rect.top) / rect.height) * 100)));

    setCameras((prev) =>
      prev.map((cam) => (cam.id === draggingCamId ? { ...cam, mapPos: { x, y } } : cam))
    );
  };

  // --- Синхронизация с бэкендом ---
  const commentTimer = useRef(null);
  const syncedRef = useRef(Object.fromEntries(initial.cameras.map((c) => [c.id, snap(c)])));
  const [statsHourly, setStatsHourly] = useState({});
  const firstSettingsRun = useRef(true);

  // изменения камер (правила, зоны, PTZ, позиция на карте) уходят на сервер через 0.6 c; при отказе (нет прав) — откат
  useEffect(() => {
    const t = setTimeout(() => {
      cameras.forEach((c) => {
        const prev = syncedRef.current[c.id];
        const cur = snap(c);
        const changed = PERSIST.filter((k) => !prev || prev[k] !== cur[k]);
        if (!prev || changed.length === 0) return;
        syncedRef.current[c.id] = cur;
        api.patchCamera(c.id, Object.fromEntries(changed.map((k) => [k, c[k]]))).catch(() =>
          api
            .cameras()
            .then((list) => {
              list.forEach((x) => (syncedRef.current[x.id] = snap(x)));
              setCameras(list);
            })
            .catch(() => {})
        );
      });
    }, 600);
    return () => clearTimeout(t);
  }, [cameras]);

  // новые события от ИИ-модуля и других операторов (оповещения) + обновления уже показанных:
  // ИИ присылает конец нарушения и клип позже, другой оператор мог поменять статус.
  // Комментарий берём локальный — его может прямо сейчас набирать этот оператор.
  useEffect(() => {
    const t = setInterval(() => {
      api
        .events(0)
        .then((fresh) => {
          setEvents((prev) => {
            const local = Object.fromEntries(prev.map((e) => [e.id, e]));
            const maxId = prev.reduce((m, e) => Math.max(m, e.id), 0);
            if (sirenEnabled && fresh.some((f) => f.id > maxId)) beep();
            const merged = fresh.map((f) => (local[f.id] ? { ...f, description: local[f.id].description } : f));
            const ids = new Set(merged.map((e) => e.id));
            return [...merged, ...prev.filter((e) => !ids.has(e.id))];
          });
        })
        .catch(() => {});
    }, 4000);
    return () => clearInterval(t);
  }, [sirenEnabled]);

  // живой статус ИИ по камерам (FPS, задержка, адрес видеопотока); правки оператора не трогаем
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
  const hourlyStats = HOURLY_STATS.map((h) => ({ ...h, count: statsHourly[h.hour] ?? 0 }));

  useEffect(() => {
    if (firstSettingsRun.current) {
      firstSettingsRun.current = false;
      return;
    }
    if (currentUser.canEditRules) {
      api.putSettings({ sirenEnabled, skudLockEnabled, enhanceFilter, stabilizeZonesOnPTZ }).catch(() => {});
    }
  }, [sirenEnabled, skudLockEnabled, enhanceFilter, stabilizeZonesOnPTZ]);

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
        setCameras((prev) => [...prev, createdCam]);
        setSelectedCamId(createdCam.id);
      })
      .catch((err) => alert(err.message));
    setNewSiteInput('');
    setNewCamInput('');
    setNewRtspInput('');
  };

  const handleProcessEvent = (eventId, newStatus) => {
    api
      .processEvent(eventId, newStatus)
      .then((ev) => setEvents((prev) => prev.map((e) => (e.id === eventId ? ev : e))))
      .catch((err) => alert(err.message));
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

  // Видеофайл: с правами администратора уходит на сервер и становится источником камеры для ИИ,
  // без прав — просто проигрывается в браузере
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
      .catch((err) => setUploadState(err.message));
  };

  const handleTriggerRetrain = () => {
    setRetrainStatus('running');
    api
      .downloadFalseAlarms()
      .then(() => setRetrainStatus('done'))
      .catch((err) => {
        setRetrainStatus(null);
        alert(err.message);
      });
  };

  const filteredEvents = events.filter((e) =>
    filterStatus === 'all' ? true : e.status === filterStatus
  );

  const themePage = isDark
    ? 'bg-[#0F172A] text-slate-100'
    : 'bg-[#F1F5F9] text-slate-800';
  const themeCard = isDark
    ? 'bg-[#1E293B] border-slate-700/80 text-slate-100'
    : 'bg-white border-slate-200/90 text-slate-800 shadow-xs';
  const themeSubCard = isDark
    ? 'bg-[#0F172A]/70 border-slate-700/60'
    : 'bg-slate-50 border-slate-200';
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

  // Смещение всей мировой сцены при повороте/наклоне динамичной PTZ-камеры
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
      {/* ================= ПЕЧАТНЫЙ ДОКУМЕНТ ПО ГОСТ И ПРИКАЗУ РОСТЕХНАДЗОРА № 518 ================= */}
      <div className="hidden print:block bg-white text-black">
        <GostRostechnadzorReport
          hourly={hourlyStats}
          cameras={cameras}
          events={events}
          currentUser={currentUser}
          clusterCamerasCount={clusterCamerasCount}
        />
      </div>

      {/* ================= МОДАЛЬНОЕ ОКНО ПРЕДПРОСМОТРА ДОКУМЕНТА ГОСТ / ПРИКАЗА № 518 ================= */}
      {showGostPreviewModal && (
        <div className="print:hidden fixed inset-0 bg-black/75 backdrop-blur-xs z-50 flex flex-col items-center justify-start overflow-y-auto p-6">
          <div className="max-w-[210mm] w-full bg-slate-900 text-white px-5 py-3 rounded-t-2xl flex items-center justify-between border-b border-slate-700">
            <div className="flex items-center gap-2 text-xs font-semibold">
              <FileText size={16} className="text-sky-400" />
              <span>
                Предпросмотр регламентного отчета (Приказ Ростехнадзора от 11.12.2020 № 518 • ГОСТ Р 7.0.97-2016)
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => window.print()}
                className="px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold cursor-pointer flex items-center gap-1.5"
              >
                <FileDown size={14} /> Печать / Сохранить PDF
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

      {/* ================= МОДАЛЬНОЕ ОКНО ДЕТАЛЬНОГО РАЗБОРА СТОП-КАДРА ИНЦИДЕНТА ================= */}
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
                    Видеоклип {inspectModalEvent.clip_url ? '' : '— появится, когда нарушение закончится'}
                  </p>
                  {inspectModalEvent.clip_url ? (
                    <video src={inspectModalEvent.clip_url} controls autoPlay muted loop className="w-full rounded-xl border border-slate-700 bg-black" />
                  ) : (
                    <div className="h-40 rounded-xl border border-dashed border-slate-600 bg-slate-950 flex items-center justify-center text-[11px] text-slate-400">
                      Нарушение продолжается…
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
                <span className="absolute bottom-2 left-2 text-[10px] font-mono bg-black/80 text-slate-300 px-2 py-0.5 rounded">
                  Файл БД: {inspectModalEvent.frame_url || 'нет (тестовый инцидент)'}
                </span>
              </div>
              )}

              <div className="space-y-2 text-xs flex flex-col justify-between">
                <div className={`p-3 rounded-xl border space-y-1.5 ${themeSubCard}`}>
                  <p><span className={textMuted}>Участок:</span> <strong>{inspectModalEvent.site_name}</strong></p>
                  <p><span className={textMuted}>Камера:</span> <strong>{inspectModalEvent.camera_code}</strong></p>
                  <p>
                    <span className={textMuted}>Начало / конец:</span>{' '}
                    <strong>
                      {inspectModalEvent.date} {inspectModalEvent.timestamp} —{' '}
                      {inspectModalEvent.end_time || (inspectModalEvent.ai_event_id ? 'продолжается' : 'тестовый инцидент')}
                      {inspectModalEvent.duration_s != null && ` (${Math.round(inspectModalEvent.duration_s)} с)`}
                    </strong>
                  </p>
                  {inspectModalEvent.zone && (
                    <p><span className={textMuted}>Зона:</span> <strong>{inspectModalEvent.zone}</strong></p>
                  )}
                  {inspectModalEvent.description && (
                    <p><span className={textMuted}>Описание:</span> <strong>{inspectModalEvent.description}</strong></p>
                  )}
                  <p><span className={textMuted}>Достоверность LinQ TPU:</span> <strong>{Math.round(inspectModalEvent.confidence * 100)}%</strong></p>
                  <p><span className={textMuted}>Координата на ИИ-карте:</span> <strong>X:{inspectModalEvent.ai_pos.x}%, Y:{inspectModalEvent.ai_pos.y}%</strong></p>
                  <p><span className={textMuted}>Обработал:</span> <strong>{inspectModalEvent.processed_by_name}</strong></p>
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

      {/* ================= ОСНОВНОЙ ИНТЕРФЕЙС САЙТА ================= */}
      <div
        className={`print:hidden min-h-screen flex flex-col transition-colors duration-300 ${themePage} ${
          eyeComfort ? 'sepia-[.18] saturate-[.85] contrast-[.96]' : ''
        }`}
      >
        {/* Верхняя корпоративная полоса */}
        <div className="bg-[#0F172A] text-slate-200 text-xs px-6 py-2 flex flex-wrap items-center justify-between gap-3 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <span className="px-2.5 py-0.5 rounded bg-sky-600 text-white font-semibold">
              ООО «ХайТэк» • LinQ TPU
            </span>
            <span className="hidden md:inline text-slate-400">
              Автоматизированная система видеоконтроля промышленной безопасности
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1.5 bg-slate-800/90 px-2.5 py-1 rounded-lg border border-slate-700">
              <KeyRound size={13} className="text-emerald-400" title="Сессия bcrypt верифицирована" />
              <span className="text-slate-400">Профиль:</span>
              <span className="text-white font-medium">
                {currentUser.full_name} — {currentUser.position}
              </span>
              <button onClick={onLogout} className="ml-1 text-slate-400 hover:text-white underline cursor-pointer">
                Выйти
              </button>
            </div>

            <button
              onClick={() => setEyeComfort(!eyeComfort)}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-lg border transition cursor-pointer ${
                eyeComfort
                  ? 'bg-amber-500/20 border-amber-400 text-amber-300 font-semibold'
                  : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'
              }`}
            >
              <Eye size={14} />
              <span>{eyeComfort ? 'Защита зрения: ВКЛ' : 'Защита зрения'}</span>
            </button>

            <button
              onClick={() => setIsDark(!isDark)}
              className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 cursor-pointer transition"
            >
              {isDark ? (
                <Sun size={14} className="text-amber-400" />
              ) : (
                <Moon size={14} className="text-sky-400" />
              )}
              <span>{isDark ? 'Светлая тема' : 'Темная тема'}</span>
            </button>
          </div>
        </div>

        {/* Шапка с оригинальным логотипом LinQ. и 4 вкладками */}
        <header
          className={`border-b px-6 py-3 flex flex-wrap items-center justify-between gap-4 ${themeCard}`}
        >
          <div className="flex items-center gap-4">
            <LinQExactLogo isDark={isDark} />
            <div className="h-9 w-[1px] bg-slate-300 dark:bg-slate-700 hidden sm:block" />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold tracking-tight">
                  Система контроля безопасности цеха
                </span>
                {aiOnlineCams.length > 0 ? (
                  <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
                    ИИ в сети: {aiOnlineCams.length}/{cameras.length} камер • {aiBackend === 'tpu' ? 'LinQ TPU' : 'ONNX (CPU)'}
                  </span>
                ) : (
                  <span
                    title="Запустите ИИ-модуль: python -m safetyvision bridge configs/site_bridge.yaml"
                    className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-red-500/15 text-red-600 dark:text-red-400 border border-red-500/30"
                  >
                    ИИ-модуль не подключён
                  </span>
                )}
              </div>
              <p className={`text-xs ${textMuted}`}>
                {currentUser.role_name} •{' '}
                {currentUser.canEditRules
                  ? 'Администрирование участков и правил'
                  : 'Оперативный мониторинг'}
              </p>
            </div>
          </div>

          <nav className="flex flex-wrap items-center gap-2">
            {[
              { id: 'monitoring', label: '01. Мониторинг и разметка', icon: Video },
              { id: 'map_rules', label: '02. Карта цеха и Правила', icon: Map },
              { id: 'analytics', label: '03. Аналитика и Статистика', icon: BarChart3 },
              { id: 'db_inspector', label: '04. Инспектор СУБД', icon: Database },
            ].map((tab) => {
              const Icon = tab.icon;
              const active = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold transition cursor-pointer ${
                    active
                      ? 'bg-sky-600 text-white shadow-sm'
                      : `${themeSubCard} border hover:border-sky-500/50`
                  }`}
                >
                  <Icon size={15} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </nav>

          <button
            onClick={startIncidentVerification}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 active:scale-98 text-white text-xs font-semibold transition cursor-pointer shadow-xs"
          >
            <AlertTriangle size={15} />
            <span>
              {isVerifying
                ? `Верификация ${(verifyProgress * 0.03).toFixed(1)} с...`
                : 'Тестовый инцидент'}
            </span>
          </button>
        </header>

        {/* Индикатор верификации события во времени */}
        {isVerifying && (
          <div className="px-6 pt-3">
            <div className="bg-amber-500/15 border border-amber-500/40 rounded-xl p-3 flex items-center justify-between gap-4">
              <div className="flex items-center gap-2.5 text-xs font-medium text-amber-700 dark:text-amber-300">
                <Clock size={16} className="animate-spin" />
                <span>
                  Подтверждение устойчивости паттерна во времени и подавление дублирующих кадров...
                </span>
              </div>
              <div className="w-56 h-2.5 bg-slate-300 dark:bg-slate-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-amber-500 transition-all duration-200"
                  style={{ width: `${verifyProgress}%` }}
                />
              </div>
            </div>
          </div>
        )}

        {/* Верхняя панель метрик */}
        <section className="px-6 pt-4 grid grid-cols-2 lg:grid-cols-4 gap-3.5">
          {[
            {
              label: `Конвейер ИИ • ${currentCamera.code}`,
              val: camAi.online ? `${currentCamera.fps} кадров/с` : 'не в сети',
              sub: camAi.online
                ? `Обработка кадра: ${currentCamera.latency} • ${camAi.backend === 'tpu' ? 'LinQ TPU' : 'ONNX CPU'} • людей в кадре: ${camAi.persons ?? 0}`
                : 'Запустите ИИ-модуль (safetyvision bridge)',
              color: 'text-sky-600 dark:text-sky-400',
            },
            {
              label: 'Конфигурация камеры',
              val:
                currentCamera.cameraType === 'dynamic'
                  ? `Динамичная PTZ • ${currentCamera.panAngle}°`
                  : 'Статичная камера',
              sub: `Кратность зума: ${currentCamera.zoomLevel}x • Зон: ${currentCamera.zones.length}`,
              color: 'text-amber-600 dark:text-amber-400',
            },
            {
              label: 'Журнал инцидентов',
              val: events.length,
              sub: `Требуют реакции: ${events.filter((e) => e.status === 'new').length}`,
              color: 'text-red-600 dark:text-red-400',
            },
            {
              label: 'Пул дообучения (Active Learning)',
              val: `${falseAlarmEvents.length} кадр(ов)`,
              sub: `Уверенность ИИ в выбранном событии: ${Math.round(activeEvent.confidence * 100)}%`,
              color: 'text-emerald-600 dark:text-emerald-400',
            },
          ].map((m, i) => (
            <div key={i} className={`border rounded-2xl p-3.5 ${themeCard}`}>
              <p className={`text-xs font-medium ${textMuted}`}>{m.label}</p>
              <p className={`text-lg font-bold mt-0.5 ${m.color}`}>{m.val}</p>
              <p className={`text-[11px] truncate mt-0.5 ${textMuted}`}>{m.sub}</p>
            </div>
          ))}
        </section>

        {/* ОСНОВНОЙ КОНТЕНТ */}
        <main className="flex-1 p-6">
          {/* ================= ВКЛАДКА 1: МОНИТОРИНГ И РАЗМЕТКА ================= */}
          {activeTab === 'monitoring' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch">
              <div className="lg:col-span-8 flex flex-col gap-5">
                <div className={`border rounded-2xl flex flex-col overflow-hidden ${themeCard}`}>
                  <div className="p-3.5 border-b border-inherit flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                        <h2 className="text-sm font-bold">
                          {currentCamera.name} — {currentCamera.site_name}
                        </h2>
                        <button
                          onClick={() => toggleCameraType(currentCamera.id)}
                          className={`text-[11px] font-semibold px-2.5 py-0.5 rounded-lg border cursor-pointer transition ${
                            currentCamera.cameraType === 'dynamic'
                              ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/40'
                              : 'bg-slate-500/15 text-slate-600 dark:text-slate-300 border-slate-500/30'
                          }`}
                        >
                          {currentCamera.cameraType === 'dynamic'
                            ? 'Динамичная PTZ'
                            : 'Статичная'}
                        </button>
                      </div>
                      <p className={`text-xs mt-0.5 ${textMuted}`}>
                        Поток: {currentCamera.rtsp_url} • Программа TPU: {currentCamera.tpuProgram}
                      </p>
                    </div>

                    <div className="flex flex-wrap gap-1.5">
                      {cameras.map((cam) => (
                        <button
                          key={cam.id}
                          onClick={() => setSelectedCamId(cam.id)}
                          className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition cursor-pointer ${
                            selectedCamId === cam.id
                              ? 'bg-sky-600 text-white border-sky-600'
                              : `${themeSubCard} hover:border-sky-500/50`
                          }`}
                        >
                          {cam.code}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Панель управления динамичной PTZ-камерой (Влево/Вправо/Вверх/Вниз/Зум/Центр 0°) */}
                  {currentCamera.cameraType === 'dynamic' && (
                    <div className="px-4 py-2 bg-amber-500/10 border-b border-amber-500/25 flex flex-wrap items-center justify-between gap-2 text-xs">
                      <div className="flex items-center gap-2">
                        <RotateCw
                          size={14}
                          className={`text-amber-600 dark:text-amber-400 ${
                            currentCamera.autoPatrol ? 'animate-spin' : ''
                          }`}
                        />
                        <span className="font-semibold">
                          Привод PTZ: панорама {currentCamera.panAngle}° | наклон {currentCamera.tiltAngle || 0}° | кратность {currentCamera.zoomLevel}x
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-1.5">
                        <button
                          onClick={() => adjustCameraPan(-10)}
                          className={`px-2 py-1 rounded border flex items-center gap-0.5 cursor-pointer ${themeCard}`}
                        >
                          <ChevronLeft size={13} /> Влево
                        </button>
                        <button
                          onClick={() => adjustCameraPan(10)}
                          className={`px-2 py-1 rounded border flex items-center gap-0.5 cursor-pointer ${themeCard}`}
                        >
                          Вправо <ChevronRight size={13} />
                        </button>
                        <button
                          onClick={() => adjustCameraTilt(-8)}
                          className={`px-2 py-1 rounded border flex items-center gap-0.5 cursor-pointer ${themeCard}`}
                          title="Наклон камеры вверх"
                        >
                          <ChevronUp size={13} />
                        </button>
                        <button
                          onClick={() => adjustCameraTilt(8)}
                          className={`px-2 py-1 rounded border flex items-center gap-0.5 cursor-pointer ${themeCard}`}
                          title="Наклон камеры вниз"
                        >
                          <ChevronDown size={13} />
                        </button>
                        <button
                          onClick={() => adjustCameraZoom(0.15)}
                          className={`px-2 py-1 rounded border flex items-center gap-1 cursor-pointer ${themeCard}`}
                        >
                          <ZoomIn size={13} /> +
                        </button>
                        <button
                          onClick={() => adjustCameraZoom(-0.15)}
                          className={`px-2 py-1 rounded border flex items-center gap-1 cursor-pointer ${themeCard}`}
                        >
                          <ZoomOut size={13} /> -
                        </button>
                        <button
                          onClick={resetCameraPTZ}
                          className={`px-2 py-1 rounded border flex items-center gap-1 cursor-pointer ${themeCard}`}
                          title="Сбросить поворот и зум в 0°"
                        >
                          <Crosshair size={12} /> 0°
                        </button>
                        <button
                          onClick={toggleAutoPatrol}
                          className={`px-2.5 py-1 rounded font-semibold border cursor-pointer ${
                            currentCamera.autoPatrol
                              ? 'bg-amber-600 text-white border-amber-600'
                              : themeCard
                          }`}
                        >
                          {currentCamera.autoPatrol ? 'Стоп' : 'Авто-обход'}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Инструменты разметки зон и управления видеопотоком */}
                  <div
                    className={`px-4 py-2.5 border-b border-inherit flex flex-wrap items-center justify-between gap-2 ${themeSubCard}`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <select
                        value={newZoneType}
                        onChange={(e) => setNewZoneType(e.target.value)}
                        className={`text-xs rounded-lg px-2.5 py-1.5 border font-medium ${themeCard}`}
                      >
                        <option value="danger">🔴 Опасная зона</option>
                        <option value="attention">🟡 Особое внимание</option>
                        <option value="blind">⚪ Слепая зона</option>
                      </select>

                      <input
                        type="text"
                        value={newZoneLabel}
                        onChange={(e) => setNewZoneLabel(e.target.value)}
                        placeholder="Наименование зоны..."
                        className={`text-xs rounded-lg px-2.5 py-1.5 border w-36 ${themeCard}`}
                      />

                      <select
                        value={newZoneSchedule}
                        onChange={(e) => setNewZoneSchedule(e.target.value)}
                        className={`text-xs rounded-lg px-2 py-1.5 border ${themeCard}`}
                      >
                        <option value="Круглосуточно">24/7 Постоянно</option>
                        <option value="07:55 – 12:00">07:55 – 12:00</option>
                        <option value="08:00 – 20:00">08:00 – 20:00</option>
                      </select>

                      <button
                        onClick={() => {
                          setTempPolygon([]);
                          setDrawMode(drawMode === 'rect' ? 'none' : 'rect');
                        }}
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 border transition cursor-pointer ${
                          drawMode === 'rect'
                            ? 'bg-sky-600 text-white border-sky-600'
                            : `${themeCard} hover:border-sky-500`
                        }`}
                      >
                        <Square size={13} />
                        {drawMode === 'rect' ? 'Выделите область...' : '+ Область'}
                      </button>

                      <button
                        onClick={() => {
                          if (drawMode === 'polygon') {
                            finishPolygonZone();
                          } else {
                            setTempPolygon([]);
                            setDrawMode('polygon');
                          }
                        }}
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 border transition cursor-pointer ${
                          drawMode === 'polygon'
                            ? 'bg-amber-600 text-white border-amber-600'
                            : `${themeCard} hover:border-amber-500`
                        }`}
                      >
                        <Pentagon size={13} />
                        {drawMode === 'polygon'
                          ? `Сохранить (${tempPolygon.length})`
                          : '+ Контур'}
                      </button>
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5">
                      <button
                        onClick={() => setVideoSource(aiMode ? 'simulation' : 'ai')}
                        className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold border flex items-center gap-1 cursor-pointer ${
                          aiMode ? 'bg-emerald-600 text-white border-emerald-600' : themeCard
                        }`}
                        title="Живое видео с разметкой ИИ-модуля; выключите, чтобы вернуться к симуляции"
                      >
                        <Cpu size={13} /> Поток ИИ
                      </button>

                      <button
                        onClick={() => {
                          setVideoSource('simulation');
                          setSimulateWorkersWalk(!simulateWorkersWalk);
                        }}
                        className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold border flex items-center gap-1 cursor-pointer ${
                          simulateWorkersWalk
                            ? 'bg-sky-600 text-white border-sky-600'
                            : themeCard
                        }`}
                        title="Автоматическое перемещение рабочих по цеху для проверки пересечения опасных зон"
                      >
                        <Play size={12} /> Движение
                      </button>

                      <button
                        onClick={() =>
                          setVideoSource(videoSource === 'webcam' ? 'simulation' : 'webcam')
                        }
                        className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold border flex items-center gap-1 cursor-pointer ${
                          videoSource === 'webcam'
                            ? 'bg-emerald-600 text-white border-emerald-600'
                            : themeCard
                        }`}
                      >
                        <Camera size={13} /> Веб-камера
                      </button>

                      {/* Кнопка отключения зеркалирования веб-камеры */}
                      {videoSource === 'webcam' && (
                        <button
                          onClick={() => setWebcamUnmirrored(!webcamUnmirrored)}
                          className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold border flex items-center gap-1 cursor-pointer ${themeCard}`}
                          title="Переключить прямое / зеркальное отображение веб-камеры"
                        >
                          <FlipHorizontal size={13} />
                          {webcamUnmirrored ? 'Прямой вид' : 'Зеркально'}
                        </button>
                      )}

                      <label
                        className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold border flex items-center gap-1 cursor-pointer ${themeCard}`}
                        title={
                          currentUser.canEditRules
                            ? 'Загрузить видео как источник этой камеры — ИИ-модуль начнёт его анализ'
                            : 'Просмотр видео в браузере (загрузка на сервер — для Специалиста по ОТ / ИТ-службы)'
                        }
                      >
                        <Upload size={13} /> {uploadState === 'uploading' ? 'Загрузка…' : 'Видеофайл'}
                        <input
                          type="file"
                          accept="video/*"
                          onChange={handleVideoFileUpload}
                          className="hidden"
                        />
                      </label>

                      <button
                        onClick={() => setEnhanceFilter(!enhanceFilter)}
                        className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold border flex items-center gap-1 cursor-pointer ${
                          enhanceFilter
                            ? 'bg-sky-600 text-white border-sky-600'
                            : themeCard
                        }`}
                      >
                        <Sparkles size={13} /> Шумоподавление
                      </button>
                    </div>
                  </div>

                  {/* ================= ОБЪЕКТИВ КАМЕРЫ С ЕДИНЫМ ТРАНСФОРМИРУЕМЫМ СЛОЕМ МИРОВОЙ СЦЕНЫ ================= */}
                  <div
                    ref={videoContainerRef}
                    onMouseDown={handleVideoMouseDown}
                    onMouseMove={handleVideoMouseMove}
                    onMouseUp={handleVideoMouseUp}
                    onMouseLeave={handleVideoMouseUp}
                    // с живым видео кадр и сцена одной пропорции: проценты зон = проценты кадра, их же получает ИИ
                    style={aiMode ? { aspectRatio: frameAspect } : undefined}
                    className={`relative bg-slate-900 overflow-hidden select-none ${aiMode ? '' : 'h-[360px]'} ${
                      drawMode !== 'none' ? 'cursor-crosshair ring-2 ring-sky-500' : ''
                    } ${enhanceFilter ? 'contrast-125 brightness-110 saturate-125' : ''}`}
                  >
                    {/* ЕДИНЫЙ СЛОЙ МИРОВОЙ СЦЕНЫ: масштабируется (Zoom) и поворачивается (Pan/Tilt) целиком вместе с сеткой, зонами, текстом и рабочими! */}
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
                      {/* Живое видео с разметкой ИИ-модуля (MJPEG): люди, СИЗ, нарушения — уже в кадре */}
                      {aiMode && camAi.online && camAi.stream_url && (
                        <img
                          key={`${currentCamera.id}-${currentCamera.rtsp_url}`}
                          src={camAi.stream_url}
                          alt="Видеопоток ИИ"
                          draggable={false}
                          className="absolute inset-0 w-full h-full object-fill pointer-events-none"
                        />
                      )}
                      {aiMode && !(camAi.online && camAi.stream_url) && (
                        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 text-center text-slate-300 text-xs pointer-events-none">
                          <Cpu size={22} className="text-slate-500" />
                          <span className="font-semibold">ИИ-модуль не передаёт видео с этой камеры</span>
                          <span className="text-slate-400 font-mono text-[11px]">
                            {camAi.error || 'python -m safetyvision bridge configs/site_bridge.yaml'}
                          </span>
                        </div>
                      )}

                      {/* Веб-камера с исправленным зеркалированием */}
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

                      {/* Загруженный видеофайл */}
                      {videoSource === 'file' && uploadedVideoUrl && (
                        <video
                          src={uploadedVideoUrl}
                          autoPlay
                          loop
                          muted
                          className="absolute inset-0 w-full h-full object-cover"
                        />
                      )}

                      {/* БЕСКОНЕЧНАЯ ИНЖЕНЕРНАЯ СЕТКА (-inset-[100%] w-[300%] h-[300%] — никогда не обрывается при повороте и наклоне!) */}
                      <div
                        className={`absolute -inset-[100%] w-[300%] h-[300%] pointer-events-none ${aiMode ? 'opacity-0' : 'opacity-15'}`}
                        style={{
                          backgroundImage:
                            'linear-gradient(to right, #94a3b8 1px, transparent 1px), linear-gradient(to bottom, #94a3b8 1px, transparent 1px)',
                          backgroundSize: '48px 48px',
                        }}
                      />

                      {/* ПРЯМОУГОЛЬНЫЕ ЗОНЫ (Свободно увеличиваются при зуме и уходят за край кадра вместе со своей подписью!) */}
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
                              {/* Подпись жестко привязана к самой зоне и уходит за экран вместе с ней, ни во что не врезаясь! */}
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

                              {/* Уголок изменения размера */}
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

                      {/* Предпросмотр создаваемой прямоугольной зоны */}
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

                      {/* SVG-СЛОЙ ДЛЯ ПОЛИГОНОВ (overflow-visible позволяет контурам свободно заходить за границы кадра!) */}
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

                      {/* Вершины рисуемого контура */}
                      {tempPolygon.map((p, i) => (
                        <div
                          key={i}
                          style={{ left: `${p.x}%`, top: `${p.y}%` }}
                          className="absolute -translate-x-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-sky-400 border-2 border-slate-950 pointer-events-none z-20 shadow"
                        />
                      ))}

                      {/* Вершины и привязанные подписи сохраненных контуров (Без ограничителей координат — плавно уходят за кадр вместе с контуром!) */}
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

                              {/* Подпись жестко следует за верхней вершиной контура без застревания у края экрана */}
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

                      {/* ИНТЕРАКТИВНЫЕ ОБЪЕКТЫ СОТРУДНИКОВ (Можно двигать мышкой и проверять срабатывание опасных зон!)
                          С живым видео людей показывает сам кадр ИИ, макеты не нужны */}
                      {!aiMode && (currentCamera.workers || []).map((worker) => {
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
                              {isDanger
                                ? `${worker.id} • ОПАСНАЯ ЗОНА!`
                                : isAttention
                                ? `${worker.id} • Контроль СИЗ`
                                : `${worker.label} • Норма`}
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {/* НЕПОДВИЖНЫЙ HUD-СЛОЙ ОБЪЕКТИВА (Не мешает зонам и не перекрывает центр экрана) */}
                    <div className="absolute bottom-2.5 left-3 flex items-center gap-2 pointer-events-none z-30">
                      <span className="px-2 py-0.5 rounded bg-slate-950/80 border border-slate-700 text-[10px] font-mono text-slate-300 flex items-center gap-1.5">
                        <Cpu size={11} className="text-sky-400" />
                        {currentCamera.code} • {currentCamera.fps} FPS • Зум {currentCamera.zoomLevel}x
                        {aiMode && camAi.online && ` • ${camAi.mapped ? 'камера откалибрована' : 'калибровка по людям…'}`}
                      </span>
                      {uploadState && uploadState !== 'uploading' && (
                        <span className="px-2 py-0.5 rounded bg-red-600 text-white text-[10px] font-bold pointer-events-auto">
                          Видео не загружено: {uploadState}
                        </span>
                      )}
                      {collidingDangerWorker && (
                        <span className="px-2 py-0.5 rounded bg-red-600 text-white text-[10px] font-bold animate-pulse">
                          ТРЕВОГА: Нарушение периметра ({collidingDangerWorker.id})
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Нижняя панель интеграции с цеховой автоматикой */}
                  <div className="px-4 py-2.5 border-t border-inherit flex flex-wrap items-center justify-between gap-2 text-xs">
                    <div className="flex flex-wrap items-center gap-4">
                      <label className="flex items-center gap-1.5 cursor-pointer font-medium">
                        <input
                          type="checkbox"
                          checked={sirenEnabled}
                          onChange={(e) => setSirenEnabled(e.target.checked)}
                        />
                        <Volume2 size={14} className="text-amber-500" />
                        <span>Светозвуковое оповещение на участке</span>
                      </label>

                      <label className="flex items-center gap-1.5 cursor-pointer font-medium">
                        <input
                          type="checkbox"
                          checked={skudLockEnabled}
                          onChange={(e) => setSkudLockEnabled(e.target.checked)}
                        />
                        <Lock size={14} className="text-sky-500" />
                        <span>Блокировка СКУД и линии при нарушении</span>
                      </label>
                    </div>

                    <span className={`text-[11px] ${textMuted}`}>
                      Режим кадра: {enhanceFilter ? 'Контраст Пыль/Ночь' : 'Штатный'}
                    </span>
                  </div>
                </div>

                {/* Нижний ряд: Мультиэкран камер + ИИ-позиционирование */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5 flex-1">
                  <div className={`border rounded-2xl p-4 flex flex-col justify-between ${themeCard}`}>
                    <div className="flex items-center justify-between mb-2.5">
                      <h3 className="text-xs font-bold uppercase tracking-wider flex items-center gap-1.5">
                        <Layers size={14} className="text-sky-500" />
                        Видеопотоки предприятия ({cameras.length})
                      </h3>
                      <span className={`text-[11px] ${textMuted}`}>Активные узлы</span>
                    </div>

                    <div className="grid grid-cols-2 gap-2.5 flex-1">
                      {cameras.map((cam) => (
                        <div
                          key={cam.id}
                          onClick={() => setSelectedCamId(cam.id)}
                          className={`p-2.5 rounded-xl border cursor-pointer transition flex flex-col justify-between ${
                            selectedCamId === cam.id
                              ? 'border-sky-500 bg-sky-500/10'
                              : `${themeSubCard} hover:border-slate-400`
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold">{cam.code}</span>
                            <span
                              className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                                cam.cameraType === 'dynamic'
                                  ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400'
                                  : 'bg-slate-500/15 text-slate-500'
                              }`}
                            >
                              {cam.cameraType === 'dynamic' ? 'PTZ' : 'Стат.'}
                            </span>
                          </div>
                          <p className={`text-[11px] truncate mt-1 ${textMuted}`}>{cam.site_name}</p>
                          <p className="text-[10px] text-sky-600 dark:text-sky-400 font-medium mt-1">
                            Зон: {cam.zones.length} • {cam.fps} FPS
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className={`border rounded-2xl p-4 flex flex-col justify-between ${themeCard}`}>
                    <div className="flex items-center justify-between mb-2">
                      <div>
                        <h3 className="text-xs font-bold uppercase tracking-wider flex items-center gap-1.5">
                          <Radar size={14} className="text-amber-500" />
                          Локализация инцидента на плане
                        </h3>
                        <p className={`text-[11px] ${textMuted}`}>
                          Событие #{activeEvent.id} • {activeEvent.violation_title}
                        </p>
                      </div>
                      <button
                        onClick={() => setInspectModalEvent(activeEvent)}
                        className="text-[11px] font-semibold px-2 py-0.5 rounded bg-sky-500/15 text-sky-600 dark:text-sky-400 flex items-center gap-1 cursor-pointer"
                      >
                        <Maximize2 size={11} /> Стоп-кадр
                      </button>
                    </div>

                    <div className="relative bg-slate-900 rounded-xl h-28 border border-slate-700 overflow-hidden flex items-center justify-center my-1">
                      <div
                        className="absolute inset-0 opacity-20"
                        style={{
                          backgroundImage: 'radial-gradient(#38bdf8 1px, transparent 1px)',
                          backgroundSize: '16px 16px',
                        }}
                      />
                      <div
                        style={{
                          left: `${activeEvent.ai_pos.x}%`,
                          top: `${activeEvent.ai_pos.y}%`,
                        }}
                        className="absolute -translate-x-1/2 -translate-y-1/2 flex flex-col items-center"
                      >
                        <span className="w-4 h-4 rounded-full bg-red-500 animate-ping absolute" />
                        <span className="w-3 h-3 rounded-full bg-red-500 border-2 border-white relative z-10" />
                        <span className="text-[9px] bg-black/80 text-white px-1.5 py-0.5 rounded mt-1 whitespace-nowrap">
                          {activeEvent.camera_code} (X:{activeEvent.ai_pos.x}, Y:{activeEvent.ai_pos.y})
                        </span>
                      </div>
                    </div>

                    <div className="mt-1.5 flex items-center gap-2">
                      <MessageSquare size={14} className={textMuted} />
                      <input
                        type="text"
                        value={activeEvent.description}
                        onChange={(e) => handleUpdateEventComment(activeEvent.id, e.target.value)}
                        placeholder="Примечание к инциденту..."
                        className={`text-xs px-2.5 py-1 rounded-lg border flex-1 ${themeSubCard}`}
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* ПРАВАЯ КОЛОНКА: Журнал событий */}
              <div
                className={`lg:col-span-4 border rounded-2xl flex flex-col overflow-hidden ${themeCard}`}
              >
                <div className="p-4 border-b border-inherit flex items-center justify-between gap-2">
                  <div>
                    <h2 className="text-sm font-bold">Журнал инцидентов</h2>
                    <p className={`text-xs ${textMuted}`}>Верификация событий оператором</p>
                  </div>
                  <select
                    value={filterStatus}
                    onChange={(e) => setFilterStatus(e.target.value)}
                    className={`text-xs rounded-lg px-2.5 py-1.5 border font-medium ${themeSubCard}`}
                  >
                    <option value="all">Все ({events.length})</option>
                    <option value="new">Новые</option>
                    <option value="confirmed">Подтверждено</option>
                    <option value="sent_to_master">У мастера</option>
                    <option value="false_alarm">Ложные ({falseAlarmEvents.length})</option>
                  </select>
                </div>

                <div className="p-3.5 space-y-3 overflow-y-auto flex-1 max-h-[640px]">
                  {filteredEvents.map((ev) => {
                    const isSelected = ev.id === selectedEventId;
                    return (
                      <div
                        key={ev.id}
                        onClick={() => setSelectedEventId(ev.id)}
                        className={`p-3.5 rounded-xl border transition cursor-pointer ${
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
                                  ev.severity === 'critical'
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
                            <h3 className="text-sm font-bold mt-1">{ev.violation_title}</h3>
                          </div>
                          <span className="text-xs font-mono font-semibold text-sky-600 dark:text-sky-400 text-right">
                            {ev.timestamp}
                            <br />
                            {ev.end_time ? (
                              <span className={`font-normal ${textMuted}`}>– {ev.end_time}</span>
                            ) : ev.ai_event_id ? (
                              <span className="font-normal text-red-500 animate-pulse">идёт</span>
                            ) : null}
                          </span>
                        </div>

                        {ev.zone && <p className="text-[11px] mt-1 font-semibold text-red-500">Зона: {ev.zone}</p>}
                        <p className={`text-xs mt-1.5 ${textMuted}`}>{ev.description}</p>

                        <div
                          className={`text-[11px] mt-2 pt-2 border-t border-slate-200 dark:border-slate-700/70 flex items-center justify-between ${textMuted}`}
                        >
                          <span>Статус: {ev.processed_by_name}</span>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setInspectModalEvent(ev);
                            }}
                            className="text-sky-500 hover:underline font-medium flex items-center gap-1 cursor-pointer"
                          >
                            <Maximize2 size={11} /> {ev.clip_url ? 'Кадр и клип' : 'Кадр'}
                          </button>
                        </div>

                        <div
                          className="mt-2.5 flex flex-wrap gap-1.5"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            onClick={() => handleProcessEvent(ev.id, 'confirmed')}
                            className={`px-2.5 py-1 rounded-lg text-xs font-medium border flex items-center gap-1 cursor-pointer transition ${
                              ev.status === 'confirmed'
                                ? 'bg-emerald-600 text-white border-emerald-600 shadow-xs'
                                : `${themeCard} border-emerald-500/40 hover:border-emerald-500`
                            }`}
                          >
                            <CheckCircle2 size={12} /> Подтвердить
                          </button>
                          <button
                            onClick={() => handleProcessEvent(ev.id, 'sent_to_master')}
                            className={`px-2.5 py-1 rounded-lg text-xs font-medium border flex items-center gap-1 cursor-pointer transition ${
                              ev.status === 'sent_to_master'
                                ? 'bg-sky-600 text-white border-sky-600 shadow-xs'
                                : `${themeCard} hover:border-sky-500`
                            }`}
                          >
                            <Send size={12} /> Мастеру
                          </button>
                          <button
                            onClick={() => handleProcessEvent(ev.id, 'false_alarm')}
                            className={`px-2.5 py-1 rounded-lg text-xs font-medium border flex items-center gap-1 cursor-pointer transition ${
                              ev.status === 'false_alarm'
                                ? 'bg-red-600 text-white border-red-600 shadow-xs'
                                : `${themeCard} border-red-500/40 text-red-500 hover:bg-red-500/10 hover:border-red-500`
                            }`}
                          >
                            <XCircle size={12} /> Ложное
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* ================= ВКЛАДКА 2: КАРТА ЦЕХА И ПРАВИЛА ================= */}
          {activeTab === 'map_rules' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-7 space-y-5">
                <div className={`border rounded-2xl p-5 ${themeCard}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-inherit">
                    <div>
                      <h2 className="text-sm font-bold flex items-center gap-2">
                        <Move size={16} className="text-sky-500" />
                        Топология размещения камер на производственном участке
                      </h2>
                      <p className={`text-xs ${textMuted}`}>
                        Интерактивная схема расположения узлов видеоконтроля и зон повышенного риска
                      </p>
                    </div>
                    <span className="text-xs font-semibold px-2.5 py-1 rounded-lg bg-sky-500/15 text-sky-600 dark:text-sky-400">
                      Активных камер: {cameras.length}
                    </span>
                  </div>

                  <div
                    ref={mapContainerRef}
                    onMouseMove={handleMapMouseMove}
                    onMouseUp={() => setDraggingCamId(null)}
                    onMouseLeave={() => setDraggingCamId(null)}
                    className="mt-4 relative bg-slate-900 border-2 border-slate-700 rounded-2xl h-[360px] select-none overflow-hidden"
                  >
                    <div
                      className="absolute inset-0 opacity-15 pointer-events-none"
                      style={{
                        backgroundImage:
                          'linear-gradient(to right, #64748b 1px, transparent 1px), linear-gradient(to bottom, #64748b 1px, transparent 1px)',
                        backgroundSize: '36px 36px',
                      }}
                    />

                    <div className="absolute top-8 left-12 w-36 h-24 bg-red-500/20 border-2 border-red-500/70 rounded-xl p-2 pointer-events-none">
                      <span className="text-[10px] font-bold text-red-200 uppercase">
                        Зона работы кран-балки
                      </span>
                    </div>

                    <div className="absolute bottom-10 left-1/3 w-40 h-24 bg-amber-500/20 border-2 border-amber-400/70 rounded-xl p-2 pointer-events-none">
                      <span className="text-[10px] font-bold text-amber-200 uppercase">
                        Линия конвейера
                      </span>
                    </div>

                    <div className="absolute top-10 right-12 w-28 h-24 bg-slate-800/90 border border-slate-600 rounded-xl p-2 flex items-center justify-center text-center pointer-events-none">
                      <span className="text-[10px] text-slate-300 font-medium">
                        Стеллажи хранения
                      </span>
                    </div>

                    {cameras.map((cam) => {
                      const isSelected = cam.id === selectedCamId;
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
                          className={`absolute -translate-x-1/2 -translate-y-1/2 px-3 py-1.5 rounded-xl text-xs font-bold border-2 flex items-center gap-1.5 cursor-grab active:cursor-grabbing ${
                            isSelected
                              ? 'bg-sky-600 text-white border-white shadow-lg scale-105 z-20'
                              : 'bg-slate-800 text-slate-100 border-sky-400/60 hover:border-white z-10'
                          }`}
                        >
                          <Video size={13} />
                          <span>{cam.code}</span>
                          <span className="text-[10px] px-1 rounded bg-black/30">
                            {cam.cameraType === 'dynamic' ? `PTZ ${cam.panAngle}°` : 'Стат.'}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className={`border rounded-2xl p-5 ${themeCard}`}>
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-bold flex items-center gap-2">
                      <Plus size={16} className="text-sky-500" />
                      Регистрация новой камеры и участка
                    </h3>
                    {!currentUser.canEditRules && (
                      <span className="text-xs text-red-500 font-medium flex items-center gap-1">
                        <Lock size={12} /> Требуются права Специалиста по ОТ или ИТ-службы
                      </span>
                    )}
                  </div>

                  <form
                    onSubmit={handleAddCamera}
                    className="grid grid-cols-1 sm:grid-cols-5 gap-3"
                  >
                    <input
                      type="text"
                      disabled={!currentUser.canEditRules}
                      placeholder="Наименование участка"
                      value={newSiteInput}
                      onChange={(e) => setNewSiteInput(e.target.value)}
                      className={`text-xs rounded-xl px-3 py-2 border ${themeSubCard}`}
                    />
                    <input
                      type="text"
                      disabled={!currentUser.canEditRules}
                      placeholder="Наименование камеры"
                      value={newCamInput}
                      onChange={(e) => setNewCamInput(e.target.value)}
                      className={`text-xs rounded-xl px-3 py-2 border ${themeSubCard}`}
                    />
                    <input
                      type="text"
                      disabled={!currentUser.canEditRules}
                      placeholder="rtsp://… или файл (видео можно загрузить позже)"
                      value={newRtspInput}
                      onChange={(e) => setNewRtspInput(e.target.value)}
                      title="Источник видео для ИИ: RTSP/HTTP-поток, номер веб-камеры сервера или путь к файлу. Можно оставить пустым и загрузить видеофайл во вкладке «Мониторинг»."
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
                      className="bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white font-semibold text-xs rounded-xl py-2 px-4 cursor-pointer transition"
                    >
                      + Зарегистрировать
                    </button>
                  </form>
                </div>
              </div>

              <div
                className={`lg:col-span-5 border rounded-2xl p-5 flex flex-col justify-between ${themeCard}`}
              >
                <div>
                  <div className="flex items-center justify-between pb-3 border-b border-inherit">
                    <div>
                      <h2 className="text-sm font-bold">
                        Матрица правил участка: {currentCamera.code}
                      </h2>
                      <p className={`text-xs ${textMuted}`}>
                        Модульное подключение детекторов поведенческих паттернов
                      </p>
                    </div>
                    <span className="text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-sky-500/15 text-sky-600 dark:text-sky-400">
                      [{currentCamera.rulesVector.join(', ')}]
                    </span>
                  </div>

                  <div className="mt-3 space-y-2">
                    {VIOLATION_TYPES.map((v, idx) => {
                      const active = currentCamera.rulesVector[idx] === 1;
                      return (
                        <div
                          key={v.id}
                          onClick={() => toggleRule(idx)}
                          className={`p-2.5 rounded-xl border flex items-center justify-between cursor-pointer transition ${
                            active
                              ? 'border-sky-500 bg-sky-500/10'
                              : `${themeSubCard} opacity-65`
                          }`}
                        >
                          <div className="flex items-center gap-2.5">
                            <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-sky-600 text-white">
                              {v.code}
                            </span>
                            <span className="text-xs font-medium">{v.name}</span>
                            {!v.ai && (
                              <span
                                title="У ИИ-модуля пока нет детектора этого нарушения: правило хранится, но не проверяется"
                                className="text-[10px] px-1.5 py-0.5 rounded bg-slate-500/20 text-slate-500"
                              >
                                нет детектора ИИ
                              </span>
                            )}
                          </div>
                          <span
                            className={`text-[11px] font-bold px-2.5 py-0.5 rounded-lg ${
                              active
                                ? 'bg-emerald-600 text-white'
                                : 'bg-slate-300 dark:bg-slate-700 text-slate-600 dark:text-slate-300'
                            }`}
                          >
                            {active ? 'АКТИВНО' : 'ВЫКЛ'}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-inherit">
                  <p className={`text-[11px] font-mono mb-1.5 ${textMuted}`}>
                    Конфигурация JSONB (sites.rules):
                  </p>
                  <pre className="bg-slate-900 text-sky-300 p-3 rounded-xl text-[11px] font-mono overflow-x-auto border border-slate-700">
                    {JSON.stringify(
                      {
                        site_id: currentCamera.site_id,
                        camera_type: currentCamera.cameraType,
                        vector: currentCamera.rulesVector,
                        zones: currentCamera.zones.map((z) => ({
                          label: z.label,
                          shape: z.shape,
                          type: z.type,
                          schedule: z.schedule,
                          coords: z.shape === 'rect' ? z.rect : z.points,
                        })),
                      },
                      null,
                      2
                    )}
                  </pre>
                </div>
              </div>
            </div>
          )}

          {/* ================= ВКЛАДКА 3: АНАЛИТИКА И СТАТИСТИКА ================= */}
          {activeTab === 'analytics' && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <div className={`lg:col-span-7 border rounded-2xl p-5 flex flex-col justify-between ${themeCard}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-inherit">
                    <div>
                      <h2 className="text-sm font-bold">
                        Динамика нарушений по часам смены
                      </h2>
                      <p className={`text-xs ${textMuted}`}>
                        Отчетность в соответствии с Приказом Ростехнадзора от 11.12.2020 № 518
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        onClick={() => setShowGostPreviewModal(true)}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold cursor-pointer ${themeSubCard}`}
                      >
                        <FileText size={14} className="text-sky-500" /> Предпросмотр формы № 518
                      </button>
                      <button
                        onClick={() => window.print()}
                        className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold cursor-pointer shadow-xs"
                      >
                        <FileDown size={14} /> Экспорт по ГОСТ (PDF)
                      </button>
                    </div>
                  </div>

                  <div className="mt-6 grid grid-cols-7 gap-3 pt-2">
                    {hourlyStats.map((item, i) => {
                      const heightPct = Math.round((item.count / 15) * 100);
                      return (
                        <div key={i} className="flex flex-col items-center">
                          <div className="h-44 w-full flex flex-col justify-end items-center border-b border-slate-300 dark:border-slate-700 pb-2">
                            <span className="text-xs font-bold mb-1.5 text-sky-600 dark:text-sky-400">
                              {item.count}
                            </span>
                            <div
                              style={{ height: `${heightPct}%` }}
                              className={`w-10 max-w-full rounded-t-lg transition-all ${
                                item.count >= 11 ? 'bg-red-500' : 'bg-sky-500'
                              }`}
                            />
                          </div>
                          <p className="text-xs font-bold mt-2.5 text-center">{item.hour}</p>
                          <p className={`text-[11px] text-center leading-tight mt-0.5 ${textMuted}`}>
                            {item.label}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className={`lg:col-span-5 border rounded-2xl p-5 flex flex-col justify-between ${themeCard}`}>
                  <div>
                    <h2 className="text-sm font-bold pb-3 border-b border-inherit flex items-center gap-2">
                      <Sliders size={16} className="text-sky-500" />
                      Калькулятор внедрения и нагрузки LinQ TPU
                    </h2>
                    <p className={`text-xs mt-2 ${textMuted}`}>
                      Расчет вычислительных модулей при масштабировании от небольшого участка до крупного предприятия
                    </p>

                    <div className={`mt-4 p-4 rounded-xl border ${themeSubCard}`}>
                      <div className="flex justify-between text-xs font-semibold mb-2">
                        <span>Количество видеопотоков на предприятии:</span>
                        <span className="text-sky-600 dark:text-sky-400 font-bold text-sm">
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

                    <div className="mt-4 grid grid-cols-2 gap-3">
                      <div className={`p-3 rounded-xl border ${themeSubCard}`}>
                        <p className={`text-[11px] ${textMuted}`}>Узлов ускорителей LinQ</p>
                        <p className="text-lg font-bold mt-0.5 text-sky-600 dark:text-sky-400">
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
                        <p className="text-lg font-bold mt-0.5 text-emerald-600 dark:text-emerald-400">
                          до -78% в год
                        </p>
                      </div>
                      <div className={`p-3 rounded-xl border ${themeSubCard}`}>
                        <p className={`text-[11px] ${textMuted}`}>Энергопотребление узла</p>
                        <p className="text-lg font-bold mt-0.5">
                          до 75 Вт (Edge)
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className={`border rounded-2xl p-5 flex flex-wrap items-center justify-between gap-4 ${themeCard}`}>
                <div>
                  <h3 className="text-sm font-bold flex items-center gap-2">
                    <RefreshCw size={16} className="text-sky-500" />
                    Контур дообучения нейросети (Active Learning • Обратная связь оператора)
                  </h3>
                  <p className={`text-xs mt-0.5 ${textMuted}`}>
                    Отмеченные красной кнопкой «Ложное» кадры ({falseAlarmEvents.length} шт.) формируют выборку для дообучения и перекомпиляции модели ONNX → .tpu
                  </p>
                </div>
                <button
                  onClick={handleTriggerRetrain}
                  className="px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold cursor-pointer flex items-center gap-1.5"
                >
                  <RefreshCw size={14} className={retrainStatus === 'running' ? 'animate-spin' : ''} />
                  {retrainStatus === 'running'
                    ? 'Собираю архив кадров и клипов…'
                    : retrainStatus === 'done'
                    ? 'Архив выборки скачан (linq_false_alarms.zip)'
                    : 'Выгрузить выборку для дообучения'}
                </button>
              </div>

              <div className={`border rounded-2xl p-5 ${themeCard}`}>
                <h3 className="text-sm font-bold mb-3">
                  Сводная таблица безопасности по производственным участкам и типам нарушений
                </h3>
                <div className="rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-100 dark:bg-slate-800">
                      <tr>
                        <th className="p-3">Производственный участок</th>
                        <th className="p-3">Камера и Тип</th>
                        <th className="p-3">Частое нарушение</th>
                        <th className="p-3">Всего инцидентов</th>
                        <th className="p-3">Подтверждено ОТ</th>
                        <th className="p-3">Точность ИИ (по отметкам)</th>
                        <th className="p-3">Рекомендация ИИ</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                      {cameraSummary(cameras, events).map((r) => (
                        <tr key={r.id}>
                          <td className="p-3 font-semibold">{r.site}</td>
                          <td className="p-3">
                            {r.code} ({r.type === 'dynamic' ? 'Динамичная PTZ' : 'Статичная'})
                          </td>
                          <td className="p-3 text-red-600 dark:text-red-400 font-medium">{r.top || '—'}</td>
                          <td className="p-3 font-bold">{r.total}</td>
                          <td className="p-3">
                            {r.confirmed}
                            {r.reviewed > 0 && ` (${Math.round((r.confirmed / r.reviewed) * 100)}% отмеченных)`}
                          </td>
                          <td className="p-3 text-emerald-600 font-bold">
                            {r.reviewed > 0 ? `${Math.round((r.confirmed / r.reviewed) * 100)}%` : 'нет отметок'}
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

          {/* ================= ВКЛАДКА 4: ИНСПЕКТОР СУБД ================= */}
          {activeTab === 'db_inspector' && (
            <div className="space-y-5">
              <div className={`border rounded-2xl p-5 ${themeCard}`}>
                <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-inherit">
                  <div>
                    <h2 className="text-base font-bold flex items-center gap-2">
                      <Database size={18} className="text-sky-500" />
                      Инспектор реляционной СУБД PostgreSQL
                    </h2>
                    <p className={`text-xs ${textMuted}`}>
                      Мониторинг связанных таблиц roles, users, sites, cameras и events
                    </p>
                  </div>
                  <span className="text-xs font-mono px-3 py-1 rounded-lg bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 font-semibold">
                    Синхронизация активна
                  </span>
                </div>

                <div className="mt-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  {[
                    {
                      table: 'roles',
                      pk: 'id (int PK)',
                      fields: ['name (varchar UK)'],
                      count: '4 записи',
                    },
                    {
                      table: 'users',
                      pk: 'id (int PK)',
                      fields: [
                        'login (varchar UK)',
                        'password_hash (bcrypt)',
                        'role_id (int FK → roles.id)',
                        'full_name (varchar)',
                        'is_active (boolean)',
                      ],
                      count: `${DB_USERS.length} записи`,
                    },
                    {
                      table: 'sites',
                      pk: 'id (int PK)',
                      fields: [
                        'name (varchar)',
                        'rules (jsonb)',
                        'created_at (timestamp)',
                      ],
                      count: `${new Set(cameras.map((c) => c.site_id)).size} записи`,
                    },
                    {
                      table: 'cameras',
                      pk: 'id (int PK)',
                      fields: [
                        'site_id (int FK → sites.id)',
                        'name (varchar)',
                        'rtsp_url (varchar)',
                        'is_active (boolean)',
                      ],
                      count: `${cameras.length} записи`,
                    },
                  ].map((tb, idx) => (
                    <div key={idx} className={`p-3.5 rounded-xl border ${themeSubCard}`}>
                      <div className="flex items-center justify-between pb-2 border-b border-slate-300 dark:border-slate-700">
                        <span className="font-mono text-xs font-bold text-sky-600 dark:text-sky-400">
                          {tb.table}
                        </span>
                        <span className="text-[11px] font-semibold">{tb.count}</span>
                      </div>
                      <p className="text-[11px] font-mono text-amber-600 dark:text-amber-400 mt-2">
                        {tb.pk}
                      </p>
                      <ul className={`text-[11px] font-mono mt-1.5 space-y-1 ${textMuted}`}>
                        {tb.fields.map((f, i) => (
                          <li key={i}>• {f}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>

                <div className="mt-6">
                  <h3 className="text-xs font-bold uppercase tracking-wider mb-2.5">
                    Записи таблицы events
                  </h3>
                  <div className="overflow-x-auto rounded-xl border border-slate-300 dark:border-slate-700">
                    <table className="w-full text-left text-xs font-mono">
                      <thead className="bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                        <tr>
                          <th className="p-2.5">id (PK)</th>
                          <th className="p-2.5">camera_id (FK)</th>
                          <th className="p-2.5">violation (enum)</th>
                          <th className="p-2.5">timestamp – ended_at</th>
                          <th className="p-2.5">frame_url, ai_map_url, clip_url</th>
                          <th className="p-2.5">status</th>
                          <th className="p-2.5">processed_by_id (FK)</th>
                          <th className="p-2.5">confidence</th>
                          <th className="p-2.5">description</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                        {events.map((ev) => (
                          <tr key={ev.id} className="hover:bg-sky-500/5">
                            <td className="p-2.5 font-bold">{ev.id}</td>
                            <td className="p-2.5">
                              {ev.camera_id} ({ev.camera_code})
                            </td>
                            <td className="p-2.5 text-red-600 dark:text-red-400 font-semibold">
                              {ev.violation}
                            </td>
                            <td className="p-2.5 whitespace-nowrap">
                              {ev.timestamp} – {ev.end_time || 'NULL'}
                            </td>
                            <td className="p-2.5 text-[11px] text-sky-600 dark:text-sky-400">
                              <div>{ev.frame_url}</div>
                              <div>{ev.ai_map_url}</div>
                              <div>{ev.clip_url}</div>
                            </td>
                            <td className="p-2.5 font-semibold">{ev.status}</td>
                            <td className="p-2.5">
                              {ev.processed_by_id
                                ? `ID:${ev.processed_by_id} (${ev.processed_by_name})`
                                : 'NULL'}
                            </td>
                            <td className="p-2.5 text-emerald-600 dark:text-emerald-400 font-bold">
                              {ev.confidence}
                            </td>
                            <td className="p-2.5 max-w-xs truncate">{ev.description}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
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
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900 text-white">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onLogin(login, password);
        }}
        className="w-80 space-y-3 bg-slate-800 border border-slate-700 rounded-2xl p-6"
      >
        <h1 className="text-lg font-bold">LinQ — вход</h1>
        <input value={login} onChange={(e) => setLogin(e.target.value)} placeholder="Логин" autoFocus
          className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-600" />
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Пароль"
          className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-600" />
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button className="w-full py-2 rounded-lg bg-sky-600 hover:bg-sky-500 font-semibold cursor-pointer">Войти</button>
      </form>
    </div>
  );
}

export default function App() {
  const [session, setSession] = useState(null); // { user, initial }
  const [loading, setLoading] = useState(!!api.getToken());
  const [error, setError] = useState('');

  const load = async () => {
    const [user, cameras, events, settings] = await Promise.all([api.me(), api.cameras(), api.events(0), api.settings()]);
    setSession({ user, initial: { cameras, events, settings } });
  };

  useEffect(() => {
    if (api.getToken()) {
      load().catch(() => api.logout()).finally(() => setLoading(false));
    }
  }, []);

  const handleLogin = async (login, password) => {
    setError('');
    try {
      await api.login(login, password);
      await load();
    } catch (e) {
      setError(e.message);
    }
  };

  if (loading) return null;
  if (!session) return <LoginScreen onLogin={handleLogin} error={error} />;
  return (
    <Dashboard
      user={session.user}
      initial={session.initial}
      onLogout={() => {
        api.logout();
        setSession(null);
      }}
    />
  );
}
