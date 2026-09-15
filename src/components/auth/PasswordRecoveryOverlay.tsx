import React, { useEffect, useState } from 'react';
import { supabase } from '../../supabase/supabaseClient';
import { requestPasswordReset, updatePassword } from '../../utils/authApi';

export function PasswordRecoveryOverlay() {
  const [active, setActive] = useState(window.location.pathname === '/forgot-password' || window.location.search.includes('auth=forgot'));
  const [recoverySession, setRecoverySession] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const { data } = supabase.auth.onAuthStateChange(event => {
      if (event === 'PASSWORD_RECOVERY') {
        setRecoverySession(true);
        setActive(true);
        setError('');
        setMessage('Recovery link verified. Choose a new password.');
      }
    });
    void supabase.auth.getSession().then(({ data: sessionData }) => {
      if (sessionData.session && window.location.hash.includes('access_token')) setRecoverySession(true);
    }).catch(() => undefined);
    return () => data.subscription.unsubscribe();
  }, []);

  if (!active) return null;

  const request = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await requestPasswordReset(email);
      setMessage('If the account exists, a password recovery email has been sent. Check your inbox and open the link.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to request password reset.');
    } finally {
      setBusy(false);
    }
  };

  const reset = async (event: React.FormEvent) => {
    event.preventDefault();
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await updatePassword(password);
      await supabase.auth.signOut();
      window.history.replaceState({}, '', '/');
      window.location.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to update password.');
    } finally {
      setBusy(false);
    }
  };

  const field: React.CSSProperties = {
    width: '100%', height: 48, borderRadius: 12, border: '1px solid #cbd5e1',
    background: '#ffffff', color: '#111827', padding: '0 14px', boxSizing: 'border-box', outline: 'none',
  };
  const primary: React.CSSProperties = {
    width: '100%', minHeight: 48, marginTop: 12, border: 0, borderRadius: 12,
    background: '#0f172a', color: '#ffffff', fontWeight: 800, cursor: 'pointer',
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 12000, display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 20, overflowY: 'auto',
      background: 'linear-gradient(130deg, #f0f9ff 0%, #ecfeff 34%, #fdf2f8 68%, #fef9c3 100%)',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif', color: '#111827',
    }}>
      <div style={{ width: '100%', maxWidth: 430, padding: 28, borderRadius: 24, background: 'rgba(255,255,255,.94)', border: '1px solid #e2e8f0', boxShadow: '0 20px 50px rgba(30,41,59,.12)', backdropFilter: 'blur(14px)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div style={{ fontSize: 11, letterSpacing: '.22em', color: '#0f172a', fontWeight: 800 }}>OMNIX</div>
          <h1 style={{ margin: '8px 0 6px', fontSize: 28, letterSpacing: '-.04em' }}>{recoverySession ? 'Set new password' : 'Forgot Password'}</h1>
          <p style={{ margin: 0, color: '#475569', fontSize: 13 }}>{recoverySession ? 'Choose a new password for your OMNIX account.' : 'Enter your email and we will send a secure recovery link.'}</p>
        </div>
        {!recoverySession ? (
          <form onSubmit={request}>
            <input style={field} type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="Email address" autoComplete="email" required />
            <button disabled={busy} style={{ ...primary, opacity: busy ? .7 : 1 }}>{busy ? 'Sending…' : 'Send Recovery Email'}</button>
          </form>
        ) : (
          <form onSubmit={reset}>
            <input style={{ ...field, marginBottom: 10 }} type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="New password (8+ characters)" autoComplete="new-password" required />
            <input style={field} type="password" value={confirm} onChange={e => setConfirm(e.target.value)} placeholder="Confirm new password" autoComplete="new-password" required />
            <button disabled={busy} style={{ ...primary, opacity: busy ? .7 : 1 }}>{busy ? 'Updating…' : 'Update Password'}</button>
          </form>
        )}
        {message && <div style={{ marginTop: 14, padding: '10px 12px', borderRadius: 10, background: '#f0fdf4', color: '#166534', fontSize: 12 }}>{message}</div>}
        {error && <div role="alert" style={{ marginTop: 14, padding: '10px 12px', borderRadius: 10, background: '#fef2f2', color: '#b91c1c', fontSize: 12 }}>{error}</div>}
        <button type="button" onClick={() => { window.location.href = '/'; }} style={{ width: '100%', marginTop: 16, minHeight: 44, borderRadius: 12, border: '1px solid #cbd5e1', background: '#ffffff', color: '#334155', cursor: 'pointer' }}>Back to Log In</button>
      </div>
    </div>
  );
}
