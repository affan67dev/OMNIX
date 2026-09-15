import { AuthContainer } from './pages/AuthContainer';
import { PasswordRecoveryOverlay } from './components/auth/PasswordRecoveryOverlay';
import { ErrorTracker } from './components/ErrorTracker';
import { CrashMonitor } from './components/security/CrashMonitor';

function App() {
  return (
    <ErrorTracker>
      <CrashMonitor />
      <AuthContainer />
      <PasswordRecoveryOverlay />
    </ErrorTracker>
  );
}

export default App;
