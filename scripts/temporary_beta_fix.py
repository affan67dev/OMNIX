from pathlib import Path
import json


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    p = Path(path)
    s = p.read_text()
    n = s.count(old)
    if n < count:
        raise SystemExit(f"Expected {count} occurrence(s) in {path}, found {n}: {old[:80]!r}")
    p.write_text(s.replace(old, new, count))


replace("src/pages/AuthContainer.tsx", "import { checkSignupAvailability, loginWithPassword, persistAuthSession, sendSignupOtp, signupWithWizard, verifySignupOtp } from '../utils/authApi';", "import { checkSignupAvailability, loginWithPassword, persistAuthSession, sendSignupOtp, signupWithWizard, verifySignupOtp } from '../utils/authApi';\nimport { supabase } from '../supabase/supabaseClient';")
replace("src/pages/AuthContainer.tsx", "  const [offlineMode, setOfflineMode] = useState(false);\n", "")
replace("src/pages/AuthContainer.tsx", """      const response = await fetch(`${API_BASE}/api/auth/availability`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: '', username: '' }),
        signal: controller.signal,
      });
      return response.status >= 200 && response.status < 500;""", """      const response = await fetch(`${getApiBase()}/api/health`, { method: 'GET', signal: controller.signal });
      return response.ok;""")
replace("src/pages/AuthContainer.tsx", """        let storedUser: string | null = null;
        let storedToken: string | null = null;
""", """        let storedUser: string | null = null;
        let sessionUser: any = null;
""")
replace("src/pages/AuthContainer.tsx", "          storedToken = window.localStorage.getItem('access_token');\n", "")
replace("src/pages/AuthContainer.tsx", """        const backendReachable = await probeBackendReachable();
        setOfflineMode(!backendReachable);

        if (!backendReachable) {
          setScreen('login');
          setAuthError('Offline Mode');
        }

        if (!storedToken) {
          clearCorruptLocalState();
          setScreen('login');
        }

        if (backendReachable && storedToken) {
          try {
            const parsedUser = storedUser ? JSON.parse(storedUser) as { username?: string } : null;
            if (parsedUser?.username) {
              setCurrentUsername(parsedUser.username);
              setIdentifier(parsedUser.username);
            }
          } catch (error) {
            console.error('Corrupt user payload in local storage', error);
            clearCorruptLocalState();
            setScreen('login');
            setAuthError('Session data was invalid. Please login again.');
            return;
          }

          setScreen('dashboard');
        }
""", """        try {
          const { data, error } = await supabase.auth.getSession();
          if (error) throw error;
          sessionUser = data.session?.user ?? null;
        } catch (error) {
          clearCorruptLocalState();
          setScreen('login');
          setAuthError(error instanceof Error ? error.message : 'Supabase authentication could not be initialized.');
        }

        if (sessionUser) {
          let parsedUser: { username?: string } | null = null;
          try { parsedUser = storedUser ? JSON.parse(storedUser) as { username?: string } : null; } catch { /* stale local profile; Supabase session remains authoritative */ }
          const usernameValue = String(sessionUser.user_metadata?.username || parsedUser?.username || sessionUser.email?.split('@')[0] || sessionUser.phone || 'omnix_user');
          setCurrentUsername(usernameValue);
          setIdentifier(usernameValue);
          setScreen('dashboard');
        }

        const backendReachable = await probeBackendReachable();
        if (!backendReachable && getConfiguredApiBase()) {
          console.warn('OMNIX backend is unavailable; backend-dependent features will be unavailable until it recovers.');
        }
""")
replace("src/pages/AuthContainer.tsx", "        if (backendReachable && launchPayload?.targetScreen === 'chat') {", "        if (sessionUser && launchPayload?.targetScreen === 'chat') {")
replace("src/pages/AuthContainer.tsx", "        } else if (backendReachable && launchPayload?.targetScreen === 'profile') {", "        } else if (sessionUser && launchPayload?.targetScreen === 'profile') {")
replace("src/pages/AuthContainer.tsx", "        } else if (backendReachable && launchPayload?.targetScreen === 'settings') {", "        } else if (sessionUser && launchPayload?.targetScreen === 'settings') {")
replace("src/pages/AuthContainer.tsx", """          {offlineMode ? (
            <div style={{ marginBottom: '12px', border: '1px solid #f59e0b', background: '#fffbeb', color: '#92400e', borderRadius: '10px', padding: '10px 12px', fontSize: '13px', fontWeight: 700 }}>
              Offline Mode
            </div>
          ) : null}
""", "")
replace("src/pages/AuthContainer.tsx", "        setOfflineMode(true);\n        setAuthError('Offline Mode');", "        setAuthError(error instanceof Error ? error.message : 'OMNIX could not initialize. Please reload.');")

replace("src/utils/socialApi.ts", "const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\\/$/, '');", """const configuredApiBase = String(import.meta.env.VITE_API_BASE_URL || '').trim();
const API_BASE = (configuredApiBase || (import.meta.env.DEV ? 'http://localhost:8000' : '')).replace(/\\/$/, '');

export function getConfiguredApiBase(): string {
  if (!API_BASE) throw new Error('OMNIX API is not configured. Set VITE_API_BASE_URL for this deployment.');
  return API_BASE;
}

export function getApiBase(): string {
  return getConfiguredApiBase();
}""")
replace("src/utils/socialApi.ts", "  const url = new URL(`${API_BASE}${path}`);", "  const url = new URL(`${getConfiguredApiBase()}${path}`);", 2)
replace("src/pages/ChatScreen.tsx", "import { apiJson, API_BASE } from '../utils/socialApi';", "import { apiJson, getApiBase } from '../utils/socialApi';")
replace("src/pages/ChatScreen.tsx", "const source = new EventSource(`${API_BASE}/api/chat/conversations/${activeConversationId}/stream`);", "const source = new EventSource(`${getApiBase()}/api/chat/conversations/${activeConversationId}/stream`);")
replace("src/components/settings/SettingsHub.tsx", "import { apiJson, API_BASE } from '../../utils/socialApi';", "import { apiJson, getApiBase } from '../../utils/socialApi';")
replace("src/components/settings/SettingsHub.tsx", "window.open(`${API_BASE}${overview.latest_export?.download_url}`, '_blank', 'noopener,noreferrer')", "window.open(`${getApiBase()}${overview.latest_export?.download_url}`, '_blank', 'noopener,noreferrer')")
replace("src/pages/AuthContainer.tsx", "import { apiJson, API_BASE, CURRENT_USER_ID } from '../utils/socialApi';", "import { apiJson, getApiBase, getConfiguredApiBase, CURRENT_USER_ID } from '../utils/socialApi';")

env = Path('.env.example')
text = env.read_text()
if 'VITE_API_BASE_URL=' not in text:
    env.write_text("# Browser/Vite build-time values (public; never put service-role credentials here)\nVITE_API_BASE_URL=https://your-backend.example\nVITE_SUPABASE_URL=https://your-project.supabase.co\nVITE_SUPABASE_ANON_KEY=replace_me\n# VITE_SUPABASE_PUBLISHABLE_KEY=replace_me\n\n" + text)

vercel = Path('vercel.json')
cfg = json.loads(vercel.read_text())
rewrites = cfg.setdefault('rewrites', [])
if not any(r.get('source') == '/health' for r in rewrites):
    rewrites.append({'source': '/health', 'destination': '/health.json'})
vercel.write_text(json.dumps(cfg, indent=2) + '\n')
Path('public/health.json').write_text('{"status":"healthy","service":"omnix-frontend"}\n')
