import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { App } from './App';
import { AuthProvider } from './lib/auth';

function jsonResponse(status: number, payload: unknown) {
  return { status, ok: status >= 200 && status < 300, json: async () => payload } as Response;
}

const fetchMock = vi.fn();

function mount(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><AuthProvider><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></AuthProvider></QueryClientProvider>);
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock);
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(jsonResponse(401, { detail: 'Not authenticated' }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('application routes', () => {
  it('redirects an unauthenticated user away from protected admin screens', async () => {
    mount('/admin/people');
    expect(await screen.findByRole('heading', { name: /sign in to your/i })).toBeInTheDocument();
  });

  it('keeps the biometric notice reachable before sign-in', async () => {
    mount('/privacy');
    expect(await screen.findByRole('heading', { name: /biometric & location notice/i })).toBeInTheDocument();
    expect(screen.getByText(/institution review required/i)).toBeInTheDocument();
  });
});
