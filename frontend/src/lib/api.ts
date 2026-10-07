export type Role = 'admin' | 'teacher' | 'student';

/**
 * Application/business timezone. The API reports the configured campus timezone at /health/live;
 * until that answers (and if it is unavailable) the client keeps using India Standard Time so a
 * browser in another system timezone never silently shows UTC attendance times.
 */
export const DEFAULT_CAMPUS_TIMEZONE = 'Asia/Kolkata';

let campusTimezone = DEFAULT_CAMPUS_TIMEZONE;
export function setCampusTimezone(value?: string | null) {
  campusTimezone = value && value.trim() ? value.trim() : DEFAULT_CAMPUS_TIMEZONE;
}
export function getCampusTimezone() { return campusTimezone; }

function zoneFormatter(options: Intl.DateTimeFormatOptions, timezone: string | undefined): Intl.DateTimeFormat {
  const zone = timezone && timezone.trim() ? timezone.trim() : campusTimezone;
  try {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone: zone });
  } catch {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone: DEFAULT_CAMPUS_TIMEZONE });
  }
}

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  active: boolean;
  student_number?: string | null;
  employee_number?: string | null;
}

export class ApiError extends Error {
  status: number;
  code?: string;
  requestId?: string;

  constructor(status: number, message: string, code?: string, requestId?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

function readCookie(name: string): string | undefined {
  if (typeof document === 'undefined') return undefined;
  const value = document.cookie.split('; ').find((part) => part.startsWith(`${name}=`));
  return value ? decodeURIComponent(value.slice(name.length + 1)) : undefined;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || 'GET').toUpperCase();
  const headers = new Headers(options.headers);
  const isForm = typeof FormData !== 'undefined' && options.body instanceof FormData;
  if (options.body && !isForm && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !path.endsWith('/auth/login') && !path.endsWith('/auth/activate')) {
    const csrf = readCookie('ssams_csrf');
    if (csrf) headers.set('X-CSRF-Token', csrf);
  }
  const response = await fetch(path.startsWith('/api/') ? path : `/api/v1${path}`, {
    ...options,
    method,
    headers,
    credentials: 'include',
  });
  if (response.status === 204) return undefined as T;
  if (response.status === 401 && !path.endsWith('/auth/login')) window.dispatchEvent(new CustomEvent('ssams:session-expired'));
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload?.detail;
    const message = typeof detail === 'string'
      ? detail
      : typeof detail?.message === 'string'
        ? detail.message
        : payload?.message || `Request failed (${response.status})`;
    throw new ApiError(response.status, message, detail?.code, payload?.request_id);
  }
  return payload as T;
}

export function jsonBody(value: unknown): string {
  return JSON.stringify(value);
}

export function formatDate(value?: string | null, timezone: string | undefined = campusTimezone): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return zoneFormatter({ dateStyle: 'medium', timeStyle: 'short' }, timezone).format(date);
}

export function formatTime(value?: string | null, timezone: string | undefined = campusTimezone): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return zoneFormatter({ hour: 'numeric', minute: '2-digit' }, timezone).format(date);
}

export function formatMonthDay(value?: string | null, timezone: string | undefined = campusTimezone): { month: string; day: string } {
  if (!value) return { month: '—', day: '—' };
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return { month: '—', day: '—' };
  const parts = zoneFormatter({ month: 'short', day: 'numeric' }, timezone).formatToParts(date);
  return { month: parts.find((part) => part.type === 'month')?.value || '—', day: parts.find((part) => part.type === 'day')?.value || '—' };
}

export function formatPercent(value: number | null | undefined): string {
  return value == null ? 'No eligible sessions' : `${value.toFixed(1)}%`;
}
