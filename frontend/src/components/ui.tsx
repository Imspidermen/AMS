import type { ReactNode } from 'react';
import { AlertCircle, CheckCircle2, Info, LoaderCircle } from 'lucide-react';

export function PageHeader({ eyebrow, title, description, actions }: {
  eyebrow?: string; title: string; description?: string; actions?: ReactNode;
}) {
  return <div className="page-header">
    <div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>
    {actions && <div className="page-actions">{actions}</div>}
  </div>;
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`card ${className}`}>{children}</section>;
}

export function StatCard({ label, value, subtext, icon, accent = 'blue' }: {
  label: string; value: string | number; subtext?: string; icon: ReactNode; accent?: string;
}) {
  return <div className={`stat-card accent-${accent}`}>
    <div className="stat-top"><span>{label}</span><span className="stat-icon">{icon}</span></div>
    <strong>{value}</strong>{subtext && <small>{subtext}</small>}
  </div>;
}

export function EmptyState({ title, message, action }: { title: string; message: string; action?: ReactNode }) {
  return <div className="empty-state"><div className="empty-icon"><Info size={20} /></div><strong>{title}</strong><p>{message}</p>{action}</div>;
}

export function Loading({ label = 'Loading your workspace…' }: { label?: string }) {
  return <div className="loading"><LoaderCircle className="spin" size={22} />{label}</div>;
}

export function Notice({ kind = 'info', children }: { kind?: 'info' | 'success' | 'error'; children: ReactNode }) {
  const Icon = kind === 'success' ? CheckCircle2 : kind === 'error' ? AlertCircle : Info;
  return <div className={`notice notice-${kind}`} role={kind === 'error' ? 'alert' : 'status'}><Icon size={17} /><span>{children}</span></div>;
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: string }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label className="field"><span className="field-label">{label}</span>{children}{hint && <small>{hint}</small>}</label>;
}
