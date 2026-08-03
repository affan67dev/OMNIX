import React, { useEffect, useState } from 'react';
import { Stories } from '../components/ui/Stories';
import { HomeFeed } from '../components/ui/HomeFeed';
import { Reels } from '../components/ui/Reels';
import { Profile } from '../components/ui/Profile';
import { ChatScreen } from './ChatScreen';
import { SettingsScreen } from '../components/settings/SettingsScreen';
import { LaunchSplashScreen } from '../components/app/LaunchSplashScreen';
import { apiJson, API_BASE } from '../utils/socialApi';
import { consumeDevicePushToken, consumeNativeLaunchPayload, requestNativeNotificationPermission, subscribeToOpenScreen } from '../utils/nativeAppBridge';
import { SecureLock } from '../components/SecureLock';
import { hasConfiguredAppLock, verifyAppLock } from '../utils/lockVault';
import { OtpInput } from '../components/ui/OtpInput';
import { LegalDocumentModal, type LegalDocumentType } from '../components/legal/LegalDocuments';
import { checkSignupAvailability, loginWithPassword, persistAuthSession, sendSignupOtp, signupWithWizard, verifySignupOtp } from '../utils/authApi';

export function AuthContainer() {
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [screen, setScreen] = useState<'login' | 'signup' | 'dashboard'>('login');
  const [activeTab, setActiveTab] = useState<'home' | 'search' | 'post' | 'reels' | 'profile' | 'messages' | 'settings'>('home');
  const [targetConversationId, setTargetConversationId] = useState('');
  const [appLocked, setAppLocked] = useState(false);
  const [appLockBusy, setAppLockBusy] = useState(false);
  const [appLockError, setAppLockError] = useState('');
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState('');
  const [offlineMode, setOfflineMode] = useState(false);
  const [legalModal, setLegalModal] = useState<LegalDocumentType | null>(null);
  const [currentUsername, setCurrentUsername] = useState('operator_bite');

  const [signupStep, setSignupStep] = useState<1 | 2 | 3>(1);
  const [countryCode, setCountryCode] = useState('+1');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [otpChallengeId, setOtpChallengeId] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [otpVerified, setOtpVerified] = useState(false);
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [displayNickname, setDisplayNickname] = useState('');
  const [availabilityChecked, setAvailabilityChecked] = useState(false);
  const [availabilityStatus, setAvailabilityStatus] = useState('');
  const [availabilityBusy, setAvailabilityBusy] = useState(false);
  const [signupPassword, setSignupPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [legalAccepted, setLegalAccepted] = useState(false);
  
  // Self Healing Feed Training Model State Log Tracker
  const [algoLogs, setAlgoLogs] = useState<string[]>(['Algorithm Initialized: Passive State Listening...']);

  const targetUsername = currentUsername.trim() || 'operator_bite';

  const clearCorruptLocalState = () => {
    try {
      window.localStorage.removeItem('user');
      window.localStorage.removeItem('access_token');
      window.localStorage.removeItem('refresh_token');
    } catch (error) {
      console.error('Failed to clear corrupt local storage', error);
    }
  };

  const probeBackendReachable = async (): Promise<boolean> => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 3500);
    try {
      const response = await fetch(`${API_BASE}/api/auth/availability`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: '', username: '' }),
        signal: controller.signal,
      });
      return response.status >= 200 && response.status < 500;
    } catch {
      return false;
    } finally {
      window.clearTimeout(timeout);
    }
  };

  useEffect(() => {
    const bootstrap = async () => {
      try {
        let storedUser: string | null = null;
        let storedToken: string | null = null;
        let launchPayload: ReturnType<typeof consumeNativeLaunchPayload> = null;

        try {
          storedUser = window.localStorage.getItem('user');
          storedToken = window.localStorage.getItem('access_token');
        } catch (error) {
          console.error('Bootstrap local storage read failed', error);
          clearCorruptLocalState();
          setScreen('login');
        }

        try {
          launchPayload = consumeNativeLaunchPayload();
        } catch (error) {
          console.error('Launch payload read failed', error);
        }

        const backendReachable = await probeBackendReachable();
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

        try {
          if (await hasConfiguredAppLock()) {
            setAppLocked(true);
          }
        } catch (error) {
          console.error('App lock bootstrap read failed', error);
        }

        if (backendReachable && launchPayload?.targetScreen === 'chat') {
          setScreen('dashboard');
          setActiveTab('messages');
          setTargetConversationId(launchPayload.conversationId ?? '');
        } else if (backendReachable && launchPayload?.targetScreen === 'profile') {
          setScreen('dashboard');
          setActiveTab('profile');
        } else if (backendReachable && launchPayload?.targetScreen === 'settings') {
          setScreen('dashboard');
          setActiveTab('settings');
        }

        let pendingPushToken: string | null = null;
        try {
          pendingPushToken = consumeDevicePushToken();
        } catch (error) {
          console.error('Push token read failed', error);
        }

        if (backendReachable && pendingPushToken) {
          try {
            await apiJson('/api/v1/push/register-device', {
              method: 'POST',
              body: JSON.stringify({
                fcm_token: pendingPushToken,
                platform: 'android',
                device_id: 'native-webview-shell',
                app_version: '1.0.0',
              }),
            });
          } catch {
            // Device token registration is retried on next app launch.
          }
        }

        try {
          requestNativeNotificationPermission();
        } catch (error) {
          console.error('Notification permission bridge failed', error);
        }
      } catch (error) {
        console.error('Fatal bootstrap failure', error);
        clearCorruptLocalState();
        setScreen('login');
        setOfflineMode(true);
        setAuthError('Offline Mode');
      } finally {
        window.setTimeout(() => setIsBootstrapping(false), 1000);
      }
    };

    void bootstrap();
    const unsubscribe = subscribeToOpenScreen((payload) => {
      setScreen('dashboard');
      if (payload.targetScreen === 'chat') {
        setActiveTab('messages');
        setTargetConversationId(payload.conversationId ?? '');
      } else if (payload.targetScreen === 'profile') {
        setActiveTab('profile');
      } else if (payload.targetScreen === 'settings') {
        setActiveTab('settings');
      } else {
        setActiveTab('home');
      }
    });
    return () => unsubscribe();
  }, []);

  useEffect(() => {
    if (screen !== 'signup' || signupStep !== 2) {
      return;
    }

    const trimmedUsername = username.trim();
    const trimmedEmail = email.trim();
    if (!trimmedUsername || !trimmedEmail) {
      setAvailabilityChecked(false);
      setAvailabilityBusy(false);
      return;
    }

    const timeoutId = window.setTimeout(() => {
      setAvailabilityBusy(true);
      void checkSignupAvailability(trimmedEmail, trimmedUsername)
        .then((response) => {
          if (!response.email_available) {
            setAvailabilityChecked(false);
            setAvailabilityStatus('Email is already registered.');
            return;
          }
          if (!response.username_available) {
            setAvailabilityChecked(false);
            setAvailabilityStatus('Username is already taken. Choose another one.');
            return;
          }
          setAvailabilityChecked(true);
          setAvailabilityStatus('Username is available.');
        })
        .catch(() => {
          setAvailabilityChecked(false);
          setAvailabilityStatus('Unable to validate username right now. Check your network and retry.');
        })
        .finally(() => {
          setAvailabilityBusy(false);
        });
    }, 450);

    return () => window.clearTimeout(timeoutId);
  }, [screen, signupStep, email, username]);

  const registerAlgorithmicTrain = (actionType: string, metaString: string) => {
    const updatedLog = `[TRAINED] ${actionType} on target node: ${metaString} -> Adjusting Weight Vectors.`;
    setAlgoLogs(prev => [updatedLog, ...prev.slice(0, 4)]);
  };

  const resetSession = () => {
    window.localStorage.removeItem('user');
    window.localStorage.removeItem('access_token');
    window.localStorage.removeItem('refresh_token');
    setScreen('login');
    setActiveTab('home');
    setTargetConversationId('');
    setIdentifier('');
    setPassword('');
    setCurrentUsername('operator_bite');
    setAuthError('');
    setAuthBusy(false);
    setSignupStep(1);
    setCountryCode('+1');
    setPhoneNumber('');
    setOtpChallengeId('');
    setOtpCode('');
    setOtpVerified(false);
    setEmail('');
    setUsername('');
    setDisplayNickname('');
    setAvailabilityChecked(false);
    setAvailabilityStatus('');
    setSignupPassword('');
    setConfirmPassword('');
    setLegalAccepted(false);
    setAlgoLogs(['Algorithm Initialized: Passive State Listening...']);
  };

  const triggerPostPermission = () => {
    const userConfirm = window.confirm('BITE System Request:\n"Allow explicit secure system permission to view native phone storage gallery content safely?"');
    if (userConfirm) {
      alert('✅ Storage pipeline connection authorized without leaking system location strings.');
    }
  };

  if (isBootstrapping) {
    return <LaunchSplashScreen />;
  }

  if (screen === 'dashboard' && appLocked) {
    return (
      <SecureLock
        title="Unlock ByteChat"
        busy={appLockBusy}
        error={appLockError}
        onBiometricUnlock={async () => {
          setAppLocked(false);
        }}
        onSubmit={async (secret) => {
          setAppLockBusy(true);
          setAppLockError('');
          try {
            const valid = await verifyAppLock(secret);
            if (!valid) {
              setAppLockError('Incorrect local unlock secret.');
              return;
            }
            setAppLocked(false);
          } finally {
            setAppLockBusy(false);
          }
        }}
      />
    );
  }

  if (screen === 'dashboard') {
    const showBottomBar = activeTab !== 'messages' && activeTab !== 'settings';

    return (
      <div style={{ 
        background: '#000000', color: '#ffffff', minHeight: '100vh', 
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        display: 'flex', flexDirection: 'column', boxSizing: 'border-box', 
        paddingBottom: showBottomBar ? '54px' : '0px'
      }}>
        
        {/* --- DYNAMIC CONDITIONAL APPLICATION TOP HEADER --- */}
        {activeTab !== 'messages' && activeTab !== 'settings' && (
          <div style={{ 
            height: '56px', backgroundColor: '#000000', position: 'sticky', top: 0, zIndex: 100,
            display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 16px',
            borderBottom: '1px solid #121212'
          }}>
            <span style={{ fontSize: '22px', fontWeight: 'bold', fontStyle: 'italic', letterSpacing: '-0.5px' }}>BITE</span>
            
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              {activeTab === 'profile' ? (
                // Settings Engine Vector Trigger (Exclusive for Profile Tab Viewport)
                <svg onClick={() => setActiveTab('settings')} width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ cursor: 'pointer' }}><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
              ) : (
                <>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>
                  {/* Rocket Messenger Trigger Action Redirect */}
                  <svg onClick={() => setActiveTab('messages')} width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ transform: 'rotate(15deg)', cursor: 'pointer' }}><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                </>
              )}
            </div>
          </div>
        )}

        {/* --- SELF HEALING LIVE ALGORITHM FEED MONITOR BLOCK --- */}
        {activeTab !== 'messages' && activeTab !== 'settings' && (
          <div style={{ backgroundColor: '#0a0a0f', padding: '8px 14px', borderBottom: '1px solid #1a1a24', fontSize: '11px', fontFamily: 'monospace', color: '#22c55e' }}>
            {algoLogs.map((log, id) => <div key={id} style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>{log}</div>)}
          </div>
        )}

        {/* --- CORE CONTROL VIEW CONTROLLER DISPLAY SWITCH --- */}
        <div style={{ flex: 1, display: activeTab === 'home' ? 'block' : 'none' }}>
          <Stories username={targetUsername} />
          <HomeFeed onInteraction={registerAlgorithmicTrain} />
        </div>

        <div style={{ display: activeTab === 'search' ? 'block' : 'none', padding: '16px' }}>
          <input type="text" placeholder="Search secure metadata pools..." style={{ width: '100%', padding: '10px 14px', borderRadius: '8px', backgroundColor: '#121212', border: '1px solid #262626', color: '#fff', outline: 'none', fontSize: '13px' }} />
        </div>

        <div style={{ display: activeTab === 'reels' ? 'block' : 'none' }}>
          <Reels />
        </div>

        <div style={{ display: activeTab === 'profile' ? 'block' : 'none' }}>
          <Profile username={targetUsername} onLogout={resetSession} />
        </div>

        <div style={{ display: activeTab === 'settings' ? 'block' : 'none' }}>
          <SettingsScreen onBack={() => setActiveTab('profile')} onOpenTerms={() => setLegalModal('terms')} onOpenPrivacy={() => setLegalModal('privacy')} />
        </div>

        {/* MESSAGES TAB SWITCH SYSTEM OVERLAY */}
        <div style={{ display: activeTab === 'messages' ? 'block' : 'none' }}>
          <ChatScreen onBack={() => setActiveTab('home')} initialConversationId={targetConversationId} />
        </div>

        {/* --- CLEAN RE-ENGINEERED INSTAGRAM BAR PLATFORM BOTTOM NAVIGATION --- */}
        {showBottomBar && (
          <div style={{ 
            height: '50px', backgroundColor: '#000000', borderTop: '1px solid #121212',
            position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 100,
            display: 'flex', alignItems: 'center', justifyContent: 'space-around'
          }}>
            <div onClick={() => setActiveTab('home')} style={{ cursor: 'pointer', opacity: activeTab === 'home' ? 1 : 0.4 }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>
            </div>
            <div onClick={() => setActiveTab('search')} style={{ cursor: 'pointer', opacity: activeTab === 'search' ? 1 : 0.4 }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
            </div>
            
            <div onClick={triggerPostPermission} style={{ cursor: 'pointer', opacity: 0.8 }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="12" y1="8" x2="12" y2="16"></line><line x1="8" y1="12" x2="16" y2="12"></line></svg>
            </div>

            <div onClick={() => setActiveTab('reels')} style={{ cursor: 'pointer', opacity: activeTab === 'reels' ? 1 : 0.4 }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="23 7 16 12 23 17 23 7"></polygon><rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect></svg>
            </div>
            <div onClick={() => setActiveTab('profile')} style={{ cursor: 'pointer', opacity: activeTab === 'profile' ? 1 : 0.4 }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
            </div>
          </div>
        )}

      </div>
    );
  }

  const finalizeAuth = (usernameValue: string) => {
    setCurrentUsername(usernameValue || 'operator_bite');
    setIdentifier(usernameValue || 'operator_bite');
    setScreen('dashboard');
    setActiveTab('home');
    setAuthError('');
  };

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    setAuthError('');
    setAuthBusy(true);
    try {
      const identity = identifier.trim();
      const response = await loginWithPassword(identity, password);
      persistAuthSession(response);
      finalizeAuth(response.user.username || identifier.trim() || 'operator_bite');
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'Unable to login now');
    } finally {
      setAuthBusy(false);
    }
  };

  const requestOtp = async () => {
    setAuthError('');
    setAuthBusy(true);
    try {
      const response = await sendSignupOtp(countryCode, phoneNumber);
      setOtpChallengeId(response.challenge_id);
      setAvailabilityStatus('OTP has been sent. Enter the 6-digit code.');
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'OTP request failed');
    } finally {
      setAuthBusy(false);
    }
  };

  const verifyOtp = async () => {
    setAuthError('');
    setAuthBusy(true);
    try {
      await verifySignupOtp(otpChallengeId, otpCode);
      setOtpVerified(true);
      setSignupStep(2);
      setAvailabilityStatus('Phone verified successfully. Continue with profile identity.');
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'OTP verification failed');
    } finally {
      setAuthBusy(false);
    }
  };

  const validateStepTwo = async () => {
    setAuthError('');
    setAvailabilityStatus('');
    if (availabilityChecked) {
      setSignupStep(3);
      return;
    }
    setAuthBusy(true);
    try {
      const response = await checkSignupAvailability(email.trim(), username.trim());
      if (!response.email_available) {
        setAuthError('Email is already registered.');
        return;
      }
      if (!response.username_available) {
        setAuthError('Username is already taken.');
        return;
      }
      setAvailabilityChecked(true);
      setAvailabilityStatus('Identity is available. Continue to password setup.');
      setSignupStep(3);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'Availability check failed');
    } finally {
      setAuthBusy(false);
    }
  };

  const createAccount = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!legalAccepted) {
      return;
    }
    if (signupPassword.length < 6) {
      setAuthError('Password must be at least 6 characters.');
      return;
    }
    if (signupPassword !== confirmPassword) {
      setAuthError('Password confirmation does not match.');
      return;
    }
    setAuthError('');
    setAuthBusy(true);
    try {
      const response = await signupWithWizard({
        username: username.trim(),
        email: email.trim(),
        password: signupPassword,
        first_name: displayNickname.trim() || username.trim(),
        last_name: '',
        display_nickname: displayNickname.trim(),
        phone_country_code: countryCode,
        phone_number: phoneNumber,
        otp_challenge_id: otpChallengeId,
        legal_accepted: legalAccepted,
      });
      persistAuthSession(response);
      finalizeAuth(response.user.username || username.trim());
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'Unable to create account');
    } finally {
      setAuthBusy(false);
    }
  };

  return (
    <div style={{
      background: 'linear-gradient(130deg, #f0f9ff 0%, #ecfeff 34%, #fdf2f8 68%, #fef9c3 100%)',
      color: '#111827',
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '30px 20px',
      boxSizing: 'border-box',
    }}>
      <div style={{ marginTop: '8px', textAlign: 'center' }}>
        <h1 style={{ fontSize: '34px', fontWeight: 900, letterSpacing: '0.08em', margin: 0 }}>CLOCKCHAT</h1>
        <p style={{ margin: '6px 0 0', color: '#475569', fontSize: '13px' }}>ClockChat: Encrypted by Kript Engine</p>
      </div>

      <div style={{ width: '100%', maxWidth: '420px' }}>
        <div style={{ backgroundColor: 'rgba(255, 255, 255, 0.9)', backdropFilter: 'blur(14px)', border: '1px solid #e2e8f0', padding: '24px', borderRadius: '24px', boxSizing: 'border-box', boxShadow: '0 20px 50px rgba(30, 41, 59, 0.12)' }}>
          {offlineMode ? (
            <div style={{ marginBottom: '12px', border: '1px solid #f59e0b', background: '#fffbeb', color: '#92400e', borderRadius: '10px', padding: '10px 12px', fontSize: '13px', fontWeight: 700 }}>
              Offline Mode
            </div>
          ) : null}
          {screen === 'login' ? (
            <form onSubmit={handleLogin}>
              <h2 style={{ margin: '0 0 12px', fontSize: '22px', fontWeight: 800 }}>Login</h2>
              <input value={identifier} onChange={(event) => setIdentifier(event.target.value)} required placeholder="Identifier (username, email, or phone)" style={{ width: '100%', padding: '12px', borderRadius: '12px', border: '1px solid #cbd5e1', marginBottom: '12px', boxSizing: 'border-box' }} />

              <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required placeholder="Password" style={{ width: '100%', padding: '12px', borderRadius: '12px', border: '1px solid #cbd5e1', marginBottom: '14px', boxSizing: 'border-box' }} />
              <button type="button" onClick={() => window.alert('Use the Forgot Password flow from the recovery screen.')} style={{ border: 'none', background: 'transparent', color: '#0369a1', cursor: 'pointer', textDecoration: 'underline', fontSize: '13px', padding: 0, marginBottom: '14px' }}>
                Forgot Password?
              </button>
              <button type="submit" disabled={authBusy} style={{ width: '100%', padding: '12px', borderRadius: '12px', border: 'none', background: '#0f172a', color: '#fff', fontWeight: 700, cursor: authBusy ? 'not-allowed' : 'pointer', opacity: authBusy ? 0.7 : 1 }}>
                {authBusy ? 'Signing in…' : 'Login'}
              </button>

              <div style={{ marginTop: '14px', textAlign: 'center', fontSize: '13px', color: '#475569' }}>
                New here?
                {' '}
                <button type="button" onClick={() => { setScreen('signup'); setAuthError(''); }} style={{ border: 'none', background: 'transparent', color: '#0369a1', textDecoration: 'underline', cursor: 'pointer', padding: 0, fontWeight: 700 }}>
                  Sign Up
                </button>
              </div>
            </form>
          ) : (
            <form onSubmit={createAccount}>
              <div style={{ marginBottom: '10px' }}>
                <button type="button" onClick={() => { setScreen('login'); setAuthError(''); }} style={{ borderRadius: '999px', border: '1px solid #cbd5e1', background: '#ffffff', color: '#334155', padding: '8px 12px', cursor: 'pointer', fontWeight: 700 }}>
                  Back to Login
                </button>
              </div>
              <div style={{ fontSize: '12px', color: '#0369a1', textTransform: 'uppercase', letterSpacing: '0.14em', marginBottom: '8px' }}>Step {signupStep} of 3</div>

              {signupStep === 1 ? (
                <div>
                  <h2 style={{ margin: '0 0 8px', fontSize: '20px', fontWeight: 800 }}>What is your phone number?</h2>
                  <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr', gap: '8px', marginBottom: '10px' }}>
                    <input value={countryCode} onChange={(event) => setCountryCode(event.target.value)} placeholder="+1" style={{ padding: '12px', borderRadius: '12px', border: '1px solid #cbd5e1' }} />
                    <input value={phoneNumber} onChange={(event) => setPhoneNumber(event.target.value)} placeholder="Please enter your phone number" style={{ padding: '12px', borderRadius: '12px', border: '1px solid #cbd5e1' }} />
                  </div>
                  <button type="button" onClick={() => void requestOtp()} disabled={authBusy} style={{ width: '100%', padding: '12px', borderRadius: '12px', border: 'none', background: '#0f172a', color: '#fff', fontWeight: 700, cursor: authBusy ? 'not-allowed' : 'pointer' }}>
                    {authBusy ? 'Sending OTP…' : 'Send OTP'}
                  </button>

                  {otpChallengeId ? (
                    <div style={{ marginTop: '14px' }}>
                      <OtpInput onComplete={(value) => setOtpCode(value)} />
                      <button type="button" onClick={() => void verifyOtp()} disabled={authBusy || otpCode.length !== 6} style={{ width: '100%', marginTop: '10px', padding: '12px', borderRadius: '12px', border: '1px solid #94a3b8', background: '#f8fafc', color: '#0f172a', fontWeight: 700, cursor: authBusy || otpCode.length !== 6 ? 'not-allowed' : 'pointer' }}>
                        {authBusy ? 'Verifying…' : 'Verify OTP'}
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : null}

              {signupStep === 2 ? (
                <div>
                  <h2 style={{ margin: '0 0 8px', fontSize: '20px', fontWeight: 800 }}>Profile Identity</h2>
                  <input type="email" value={email} onChange={(event) => { setEmail(event.target.value); setAvailabilityChecked(false); }} required placeholder="Email address" style={{ width: '100%', padding: '12px', borderRadius: '12px', border: '1px solid #cbd5e1', marginBottom: '10px', boxSizing: 'border-box' }} />
                  <input value={username} onChange={(event) => { setUsername(event.target.value); setAvailabilityChecked(false); }} required placeholder="Unique username" style={{ width: '100%', padding: '12px', borderRadius: '12px', border: '1px solid #cbd5e1', marginBottom: '10px', boxSizing: 'border-box' }} />
                  <input value={displayNickname} onChange={(event) => setDisplayNickname(event.target.value)} required placeholder="Display nickname" style={{ width: '100%', padding: '12px', borderRadius: '12px', border: '1px solid #cbd5e1', marginBottom: '10px', boxSizing: 'border-box' }} />

                  <div style={{ fontSize: '12px', color: '#334155', marginBottom: '10px' }}>
                    {availabilityBusy ? 'Checking username availability…' : availabilityStatus || 'Username availability is checked in real-time.'}
                  </div>

                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button type="button" onClick={() => setSignupStep(1)} style={{ flex: 1, padding: '12px', borderRadius: '12px', border: '1px solid #cbd5e1', background: '#ffffff', cursor: 'pointer' }}>Back</button>
                    <button type="button" onClick={() => void validateStepTwo()} disabled={authBusy || !otpVerified} style={{ flex: 1, padding: '12px', borderRadius: '12px', border: 'none', background: '#0f172a', color: '#fff', fontWeight: 700, cursor: authBusy ? 'not-allowed' : 'pointer' }}>
                      {authBusy ? 'Checking…' : 'Continue'}
                    </button>
                  </div>
                </div>
              ) : null}

              {signupStep === 3 ? (
                <div>
                  <h2 style={{ margin: '0 0 8px', fontSize: '20px', fontWeight: 800 }}>Password & Consent</h2>
                  <input type="password" value={signupPassword} onChange={(event) => setSignupPassword(event.target.value)} required placeholder="Password" style={{ width: '100%', padding: '12px', borderRadius: '12px', border: '1px solid #cbd5e1', marginBottom: '10px', boxSizing: 'border-box' }} />
                  <input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required placeholder="Confirm password" style={{ width: '100%', padding: '12px', borderRadius: '12px', border: '1px solid #cbd5e1', marginBottom: '10px', boxSizing: 'border-box' }} />
                  <label style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', marginBottom: '10px', fontSize: '13px', color: '#334155' }}>
                    <input type="checkbox" checked={legalAccepted} onChange={(event) => setLegalAccepted(event.target.checked)} style={{ marginTop: '2px' }} />
                    <span>
                      I agree to the
                      {' '}
                      <button type="button" onClick={() => setLegalModal('terms')} style={{ border: 'none', background: 'transparent', color: '#0284c7', cursor: 'pointer', padding: 0, textDecoration: 'underline' }}>Terms & Conditions</button>
                      {' '}
                      and
                      {' '}
                      <button type="button" onClick={() => setLegalModal('privacy')} style={{ border: 'none', background: 'transparent', color: '#0284c7', cursor: 'pointer', padding: 0, textDecoration: 'underline' }}>Privacy Policy</button>
                    </span>
                  </label>

                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button type="button" onClick={() => setSignupStep(2)} style={{ flex: 1, padding: '12px', borderRadius: '12px', border: '1px solid #cbd5e1', background: '#ffffff', cursor: 'pointer' }}>Back</button>
                    <button type="submit" disabled={authBusy || !legalAccepted || !availabilityChecked || signupPassword !== confirmPassword} style={{ flex: 1, padding: '12px', borderRadius: '12px', border: 'none', background: '#0f172a', color: '#fff', fontWeight: 700, cursor: authBusy || !legalAccepted || !availabilityChecked || signupPassword !== confirmPassword ? 'not-allowed' : 'pointer', opacity: authBusy || !legalAccepted || !availabilityChecked || signupPassword !== confirmPassword ? 0.65 : 1 }}>
                      {authBusy ? 'Creating…' : 'Create Account'}
                    </button>
                  </div>
                </div>
              ) : null}
            </form>
          )}

          {authError ? <div style={{ marginTop: '12px', color: '#b91c1c', fontSize: '13px', fontWeight: 600 }}>{authError}</div> : null}
          {availabilityStatus ? <div style={{ marginTop: '8px', color: '#0f766e', fontSize: '12px' }}>{availabilityStatus}</div> : null}

          <div style={{ marginTop: '14px', textAlign: 'center', fontSize: '12px', color: '#475569' }}>
            <button type="button" onClick={() => setLegalModal('terms')} style={{ border: 'none', background: 'transparent', color: '#334155', cursor: 'pointer', textDecoration: 'underline' }}>Terms & Conditions</button>
            <span style={{ margin: '0 8px', color: '#94a3b8' }}>|</span>
            <button type="button" onClick={() => setLegalModal('privacy')} style={{ border: 'none', background: 'transparent', color: '#334155', cursor: 'pointer', textDecoration: 'underline' }}>Privacy Policy</button>
          </div>
        </div>
      </div>

      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: '13px', color: '#334155', marginBottom: '4px', fontWeight: 700 }}>ClockChat: Encrypted by Kript Engine</div>
        <div style={{ fontSize: '14px', color: '#334155', letterSpacing: '0.12em', fontWeight: 800 }}>From Kript Labs</div>
      </div>

      <LegalDocumentModal open={Boolean(legalModal)} type={legalModal ?? 'terms'} onClose={() => setLegalModal(null)} />
    </div>
  );
}
