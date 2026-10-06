import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { ArrowRight, Eye, EyeOff, Fingerprint, ShieldCheck } from 'lucide-react';
import { useAuth } from '../lib/auth';
import { api, ApiError, jsonBody } from '../lib/api';
import { Field, Notice } from '../components/ui';

const loginSchema = z.object({ email: z.string().email('Enter a valid email address'), password: z.string().min(1, 'Enter your password') });
type LoginFields = z.infer<typeof loginSchema>;

export function LoginPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);
  const activated = params.get('activated') === 'true';
  const form = useForm<LoginFields>({ resolver: zodResolver(loginSchema), defaultValues: { email: '', password: '' } });

  async function submit(values: LoginFields) {
    setError(''); setWorking(true);
    try {
      await signIn(values.email, values.password);
      const current = await api<{ role: string }>('/auth/me');
      navigate(current.role === 'admin' ? '/admin' : current.role === 'teacher' ? '/teacher' : '/student', { replace: true });
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 429
        ? cause.message
        : 'We could not sign you in with those details. Check your email and password or contact your administrator.');
    } finally { setWorking(false); }
  }

  return <div className="auth-screen">
    <div className="auth-aside">
      <div className="auth-brand"><span className="auth-logo"><Fingerprint size={26} /></span><div><strong>SSAMS</strong><small>Smart attendance. Clear records.</small></div></div>
      <div className="auth-aside-copy">
        <span className="auth-overline">CAMPUS ATTENDANCE, REIMAGINED</span>
        <h1>Time in class<br /><em>counts.</em></h1>
        <p>A private, locally operated attendance workspace for students, teachers, and campus administrators.</p>
        <div className="auth-points"><span><ShieldCheck size={16} /> Identity checks stay on your institution’s server</span><span><ShieldCheck size={16} /> Your attendance history, always within reach</span></div>
      </div>
      <div className="auth-aside-bottom">SSAMS <span>·</span> Smart Student Attendance Management System</div>
      <div className="auth-orb orb-one" /><div className="auth-orb orb-two" />
    </div>
    <div className="auth-panel">
      <div className="auth-panel-inner">
        <div className="auth-mobile-brand"><span className="auth-logo"><Fingerprint size={23} /></span><strong>SSAMS</strong></div>
        <span className="auth-kicker">WELCOME BACK</span>
        <h2>Sign in to your<br className="desktop-break" /> campus workspace</h2>
        <p className="auth-lede">Use the account provided by your administrator.</p>
        {activated && <Notice kind="success">Your account is active. Sign in with your new password.</Notice>}
        {error && <Notice kind="error">{error}</Notice>}
        <form className="auth-form" onSubmit={form.handleSubmit(submit)} noValidate>
          <Field label="Email address">
            <input autoComplete="username" type="email" placeholder="you@campus.edu" {...form.register('email')} aria-invalid={!!form.formState.errors.email} />
          </Field>
          {form.formState.errors.email && <span className="field-error">{form.formState.errors.email.message}</span>}
          <Field label="Password">
            <div className="password-input"><input autoComplete="current-password" type={visible ? 'text' : 'password'} placeholder="Enter your password" {...form.register('password')} aria-invalid={!!form.formState.errors.password} />
              <button type="button" className="password-toggle" aria-label={visible ? 'Hide password' : 'Show password'} onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={17} /> : <Eye size={17} />}</button></div>
          </Field>
          {form.formState.errors.password && <span className="field-error">{form.formState.errors.password.message}</span>}
          <button className="button button-primary button-wide auth-submit" disabled={working} type="submit">{working ? 'Signing in…' : 'Sign in'} <ArrowRight size={17} /></button>
        </form>
        <div className="auth-divider"><span /> <small>SECURE ACCESS</small> <span /></div>
        <p className="auth-help">New to SSAMS? Use the one-time activation link sent by your administrator. <Link to="/activate">Activate account</Link></p>
        <div className="auth-privacy"><ShieldCheck size={16} /><span>Face and location verification runs on the configured campus server. SSAMS does not record video.</span></div>
        <p className="auth-terms">By signing in, you agree to your institution’s attendance and data privacy policies.</p>
      </div>
    </div>
  </div>;
}

const activationSchema = z.object({ token: z.string().min(20, 'The activation token is missing'), password: z.string().min(12, 'Use at least 12 characters').max(256), confirm: z.string() }).refine((value) => value.password === value.confirm, { path: ['confirm'], message: 'Passwords do not match' });
type ActivationFields = z.infer<typeof activationSchema>;

export function ActivationPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [working, setWorking] = useState(false);
  const form = useForm<ActivationFields>({ resolver: zodResolver(activationSchema), defaultValues: { token: params.get('token') || '', password: '', confirm: '' } });

  async function activate(values: ActivationFields) {
    setWorking(true); setError('');
    try {
      await api('/auth/activate', { method: 'POST', body: jsonBody({ token: values.token, password: values.password }) });
      setDone(true);
      window.setTimeout(() => navigate('/login?activated=true', { replace: true }), 1600);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Activation could not be completed.'); }
    finally { setWorking(false); }
  }

  return <div className="activation-screen">
    <div className="activation-card">
      <Link className="activation-brand" to="/login"><span className="auth-logo"><Fingerprint size={22} /></span><strong>SSAMS</strong></Link>
      <span className="auth-kicker">ACCOUNT SETUP</span><h1>Activate your account</h1>
      <p className="auth-lede">Set a private password to finish connecting your campus account.</p>
      {done ? <Notice kind="success">Account activated. Taking you to sign in…</Notice> : <>
        {error && <Notice kind="error">{error}</Notice>}
        <form className="auth-form" onSubmit={form.handleSubmit(activate)}>
          {!params.get('token') && <Field label="Activation token"><input {...form.register('token')} placeholder="Paste your one-time token" /></Field>}
          {form.formState.errors.token && <span className="field-error">{form.formState.errors.token.message}</span>}
          <Field label="New password" hint="At least 12 characters, with a letter and a number."><input type="password" autoComplete="new-password" {...form.register('password')} /></Field>
          {form.formState.errors.password && <span className="field-error">{form.formState.errors.password.message}</span>}
          <Field label="Confirm password"><input type="password" autoComplete="new-password" {...form.register('confirm')} /></Field>
          {form.formState.errors.confirm && <span className="field-error">{form.formState.errors.confirm.message}</span>}
          <button className="button button-primary button-wide" disabled={working} type="submit">{working ? 'Activating…' : 'Activate account'} <ArrowRight size={17} /></button>
        </form>
      </>}
      <div className="auth-privacy"><ShieldCheck size={16} /><span>Activation links expire after 7 days, or 24 hours for password resets.</span></div>
    </div>
  </div>;
}
