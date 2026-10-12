import { useEffect, useState } from 'react';
import { AuthContainer } from './pages/AuthContainer';
import { AuthenticationOverlay } from './components/auth/AuthenticationOverlay';
import { PasswordRecoveryOverlay } from './components/auth/PasswordRecoveryOverlay';
import { ErrorTracker } from './components/ErrorTracker';
import { CrashMonitor } from './components/security/CrashMonitor';
import { supabase } from './supabase/supabaseClient';

function AppContent() {
  const [sessionReady, setSessionReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    let mounted = true;

    void supabase.auth.getSession().then(({ data, error }) => {
      if (!mounted) return;
      setAuthenticated(!error && Boolean(data.session));
      setSessionReady(true);
    }).catch(() => {
      if (!mounted) return;
      setAuthenticated(false);
      setSessionReady(true);
    });

    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!mounted) return;
      setAuthenticated(Boolean(session));
      setSessionReady(true);
    });

    return () => {
      mounted = false;
      data.subscription.unsubscribe();
    };
  }, []);

  return (
    <>
      <CrashMonitor />
      {sessionReady && authenticated ? <AuthContainer /> : null}
      {(!sessionReady || !authenticated) ? <AuthenticationOverlay /> : null}
      <PasswordRecoveryOverlay />
    </>
  );
}

function App() {
  return (
    <ErrorTracker>
      <AppContent />
    </ErrorTracker>
  );
}

export default App;
