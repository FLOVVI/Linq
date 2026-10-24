// Клиент бэкенда. В dev запросы идут через прокси Vite: /api/* -> http://127.0.0.1:8000/*
const BASE = import.meta.env.VITE_API_URL || '/api';
let token = localStorage.getItem('linq_token');

async function req(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401 && token && path !== '/auth/login') {
    api.logout();
    location.reload();
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Ошибка ${res.status}`);
  return data;
}

export const api = {
  getToken: () => token,
  logout() {
    token = null;
    localStorage.removeItem('linq_token');
  },
  async login(login, password) {
    const r = await req('POST', '/auth/login', { login, password });
    token = r.token;
    localStorage.setItem('linq_token', token);
    return r.user;
  },
  me: () => req('GET', '/me'),
  cameras: () => req('GET', '/cameras'),
  addCamera: (b) => req('POST', '/cameras', b),
  patchCamera: (id, b) => req('PATCH', `/cameras/${id}`, b),
  events: (sinceId = 0) => req('GET', `/events?since_id=${sinceId}`),
  createEvent: (b) => req('POST', '/events', b),
  processEvent: (id, status) => req('PATCH', `/events/${id}/process`, { status }),
  commentEvent: (id, description) => req('PATCH', `/events/${id}/comment`, { description }),
  stats: () => req('GET', '/stats'),
  settings: () => req('GET', '/settings'),
  putSettings: (b) => req('PUT', '/settings', b),
  // видеофайл вместо потока камеры: ИИ-модуль скачает его и начнёт анализ
  async uploadVideo(id, file) {
    const res = await fetch(`${BASE}/cameras/${id}/video`, {
      method: 'PUT',
      headers: { Authorization: `Bearer ${token}`, 'X-Filename': encodeURIComponent(file.name) },
      body: file,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Ошибка ${res.status}`);
    return data;
  },
  // архив кадров и клипов событий, отмеченных «Ложное», — выборка для дообучения
  async downloadFalseAlarms() {
    const res = await fetch(`${BASE}/training/false-alarms.zip`, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) throw new Error(`Ошибка ${res.status}`);
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement('a'), { href: url, download: 'linq_false_alarms.zip' });
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
