import { AuthContainer } from './pages/AuthContainer';
import { AuthenticationOverlay } from './components/auth/AuthenticationOverlay';
import { PasswordRecoveryOverlay } from './components/auth/PasswordRecoveryOverlay';
import { ErrorTracker } from './components/ErrorTracker';
import { CrashMonitor } from './components/security/CrashMonitor';
import { LegalDocumentModal } from './components/legal/LegalDocuments';

function LegalRoute() {
  const path = window.location.pathname;
  if (path !== '/terms' && path !== '/privacy') return null;
  return <LegalDocumentModal open type={path === '/privacy' ? 'privacy' : 'terms'} onClose={() => { window.location.href = '/'; }} />;
}

function App() {
  return (
    <ErrorTracker>
      <CrashMonitor />
      <AuthContainer />
      <AuthenticationOverlay />
      <PasswordRecoveryOverlay />
      <LegalRoute />
    </ErrorTracker>
  );
}

export default App;
