import { useEffect, useState } from 'react';
import { AuthContainer } from './pages/AuthContainer';
import { AuthenticationOverlay } from './components/auth/AuthenticationOverlay';
import { PasswordRecoveryOverlay } from './components/auth/PasswordRecoveryOverlay';
import { ErrorTracker } from './components/ErrorTracker';
import { CrashMonitor } from './components/security/CrashMonitor';
import { supabase } from './supabase/supabaseClient';

type AppAuthState = 'loading' | 'signed-out' | 'profile-incomplete' | 'ready';

function AppContent() {
  const [authState, setAuthState] = useState<AppAuthState>('loading');

  useEffect(() => {
    let mounted = true;

    const resolveSession = async (session: any) => {
      if (!session) {
        if (mounted) setAuthState('signed-out');
        return;
      }

      try {
        const { data: profile, error } = await supabase
          .from('profiles')
          .select('username')
          .eq('user_id', session.user.id)
          .maybeSingle();

        if (!mounted) return;
        setAuthState(!error && Boolean(profile?.username) ? 'ready' : 'profile-incomplete');
      } catch {
        if (mounted) setAuthState('profile-incomplete');
      }
    };

    void supabase.auth.getSession()
      .then(({ data, error }) => resolveSession(!error ? data.session : null))
      .catch(() => {
        if (mounted) setAuthState('signed-out');
      });

    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      void resolveSession(session);
    });

    return () => {
      mounted = false;
      data.subscription.unsubscribe();
    };
  }, []);

  const authenticated = authState === 'ready';

  return (
    <>
      <CrashMonitor />
      {authenticated ? <AuthContainer /> : <AuthenticationOverlay />}
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
