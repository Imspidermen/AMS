import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, type CurrentUser, jsonBody } from './api';

interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  reload: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      const current = await api<CurrentUser>('/auth/me');
      setUser(current);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void reload(); }, [reload]);
  useEffect(() => {
    const expired = () => setUser(null);
    window.addEventListener('ssams:session-expired', expired);
    return () => window.removeEventListener('ssams:session-expired', expired);
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const result = await api<{ user: CurrentUser }>('/auth/login', {
      method: 'POST', body: jsonBody({ email, password }),
    });
    setUser(result.user);
  }, []);

  const signOut = useCallback(async () => {
    try { await api('/auth/logout', { method: 'POST' }); }
    finally { setUser(null); }
  }, []);

  const value = useMemo(() => ({ user, loading, signIn, signOut, reload }), [user, loading, signIn, signOut, reload]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
