import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, formatDate, formatMonthDay, formatPercent, formatTime, setCampusTimezone } from './api';

function response(status: number, payload: unknown = {}) {
  return { status, ok: status >= 200 && status < 300, json: vi.fn().mockResolvedValue(payload) } as unknown as Response;
}

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
  fetchMock.mockReset();
  document.cookie = 'ssams_csrf=; Max-Age=0; path=/';
  setCampusTimezone('UTC');
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = 'ssams_csrf=; Max-Age=0; path=/';
});

describe('api client', () => {
  it('prefixes versioned API paths and includes same-origin credentials', async () => {
    fetchMock.mockResolvedValue(response(200, { items: [] }));
    await expect(api<{ items: unknown[] }>('/admin/departments')).resolves.toEqual({ items: [] });
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/departments', expect.objectContaining({
      method: 'GET', credentials: 'include',
    }));
  });

  it('attaches the CSRF cookie to mutations but leaves login bootstrap public', async () => {
    document.cookie = 'ssams_csrf=campus-token; path=/';
    fetchMock.mockResolvedValue(response(204));
    await api('/auth/logout', { method: 'POST' });
    expect(fetchMock.mock.calls[0][1].headers.get('X-CSRF-Token')).toBe('campus-token');
    await api('/auth/login', { method: 'POST', body: JSON.stringify({ email: 'a@b.test', password: 'x' }) });
    expect(fetchMock.mock.calls[1][1].headers.has('X-CSRF-Token')).toBe(false);
  });

  it('turns API error details into ApiError and announces expired sessions', async () => {
    const expired = vi.fn();
    window.addEventListener('ssams:session-expired', expired);
    fetchMock.mockResolvedValue(response(401, { detail: { code: 'session_expired', message: 'Sign in again.' } }));
    await expect(api('/student/dashboard')).rejects.toMatchObject({
      name: 'ApiError', status: 401, code: 'session_expired', message: 'Sign in again.',
    });
    expect(expired).toHaveBeenCalledOnce();
    window.removeEventListener('ssams:session-expired', expired);
  });

  it('does not report failed login credentials as an expired authenticated session', async () => {
    const expired = vi.fn();
    window.addEventListener('ssams:session-expired', expired);
    fetchMock.mockResolvedValue(response(401, { detail: 'Invalid email or password' }));
    await expect(api('/auth/login', { method: 'POST', body: '{}' })).rejects.toBeInstanceOf(ApiError);
    expect(expired).not.toHaveBeenCalled();
    window.removeEventListener('ssams:session-expired', expired);
  });
});

describe('campus time formatting', () => {
  it('formats dates, times, and compact dates in the configured campus zone', () => {
    setCampusTimezone('America/Los_Angeles');
    const value = '2026-01-01T01:30:00.000Z';
    expect(formatDate(value)).toContain('Dec');
    expect(formatTime(value)).toMatch(/5:30/);
    expect(formatMonthDay(value)).toEqual({ month: 'Dec', day: '31' });
  });

  it('handles empty values and nullable percentages without inventing data', () => {
    expect(formatDate(null)).toBe('—');
    expect(formatTime('not a timestamp')).toBe('—');
    expect(formatPercent(null)).toBe('No eligible sessions');
    expect(formatPercent(83.456)).toBe('83.5%');
  });
});
