import React from 'react';

export function LaunchSplashScreen() {
  return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(130deg, #f0f9ff 0%, #ecfeff 34%, #fdf2f8 68%, #fef9c3 100%)', color: '#111827', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px', boxSizing: 'border-box', overflow: 'hidden' }}>
      <style>{`
        @keyframes omnixPulse {
          0% { transform: scale(0.96); opacity: 0.72; }
          50% { transform: scale(1); opacity: 1; }
          100% { transform: scale(0.96); opacity: 0.72; }
        }
        @keyframes omnixSweep {
          0% { transform: translateX(-120%); }
          100% { transform: translateX(220%); }
        }
      `}</style>
      <div style={{ width: '100%', maxWidth: '460px', textAlign: 'center' }}>
        <div style={{ width: '108px', height: '108px', margin: '0 auto 22px', borderRadius: '28px', background: 'linear-gradient(145deg, rgba(34, 211, 238, 0.16), rgba(59, 130, 246, 0.12))', border: '1px solid #bae6fd', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 70px rgba(34, 211, 238, 0.14)', animation: 'omnixPulse 2.8s ease-in-out infinite' }}>
          <div style={{ fontSize: '32px', fontWeight: 900, letterSpacing: '0.16em' }}>OM</div>
        </div>
        <div style={{ fontSize: '14px', letterSpacing: '0.24em', textTransform: 'uppercase', color: '#0369a1', marginBottom: '8px' }}>OMNIX</div>
        <div style={{ fontSize: '34px', fontWeight: 900, lineHeight: 1.1, marginBottom: '12px' }}>Private social application.</div>
        <div style={{ fontSize: '14px', color: '#475569', marginBottom: '20px', lineHeight: 1.6 }}>Preparing the secure authentication gate.</div>
        <div style={{ position: 'relative', height: '6px', borderRadius: '999px', background: '#e2e8f0', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', inset: 0, width: '36%', borderRadius: '999px', background: 'linear-gradient(90deg, #22d3ee, #3b82f6)', animation: 'omnixSweep 1.8s linear infinite' }} />
        </div>
      </div>
    </div>
  );
}
