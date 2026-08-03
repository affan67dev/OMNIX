import React, { useEffect, useMemo, useState } from 'react';
import { apiJson, API_BASE, getCurrentUserId } from '../../utils/socialApi';
import type { SettingsOverview } from '../../types/settings';
import type { BillingSubscriptionSummary, ProductListing } from '../../types/billing';
import { PremiumPaywallModal } from './PremiumPaywallModal';
import { getPlayProductDetails, launchPlaySubscriptionPurchase, openManageSubscription } from '../../utils/playBilling';

type TabKey = 'premium' | 'account' | 'security' | 'privacy' | 'archive' | 'notifications';

export function SettingsHub({
  onBack,
  onOpenTerms,
  onOpenPrivacy,
}: {
  onBack: () => void;
  onOpenTerms?: () => void;
  onOpenPrivacy?: () => void;
}) {
  const [activeTab, setActiveTab] = useState<TabKey>('premium');
  const [overview, setOverview] = useState<SettingsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [busyKey, setBusyKey] = useState('');
  const [paywallOpen, setPaywallOpen] = useState(false);
  const [productListing, setProductListing] = useState<ProductListing | null>(null);
  const [personalInfo, setPersonalInfo] = useState({ phone_number: '', email: '', gender: '', date_of_birth: '' });
  const [exportScope, setExportScope] = useState({ include_messages: true, include_posts: true, include_profile: true });
  const [passwordForm, setPasswordForm] = useState({ current_password: '', new_password: '' });
  const [resetForm, setResetForm] = useState({ channel: 'email', destination: '', challenge_id: '', otp_code: '', new_password: '' });
  const [twoFactorSetup, setTwoFactorSetup] = useState<{ setup_id: string; method: string; qr_code_url?: string | null; phone_number?: string | null } | null>(null);
  const [twoFactorCode, setTwoFactorCode] = useState('');

  const loadOverview = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiJson<{ success: boolean } & SettingsOverview>('/api/settings/overview');
      const nextOverview: SettingsOverview = {
        account: data.account,
        premium: data.premium,
        security: data.security,
        content_preferences: data.content_preferences,
        story_settings: data.story_settings,
        storage_settings: data.storage_settings,
        notification_settings: data.notification_settings,
        sessions: data.sessions,
        archives: data.archives,
        blocked_accounts: data.blocked_accounts,
        muted_accounts: data.muted_accounts,
        latest_export: data.latest_export,
      };
      setOverview(nextOverview);
      setPersonalInfo({
        phone_number: nextOverview.account.phone_number,
        email: nextOverview.account.email,
        gender: nextOverview.account.gender,
        date_of_birth: nextOverview.account.date_of_birth,
      });
      setResetForm((current) => ({
        ...current,
        destination: current.destination || nextOverview.account.email,
      }));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to load settings');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadOverview();
  }, []);

  useEffect(() => {
    void getPlayProductDetails().then((products) => {
      setProductListing(products[0] ?? null);
    }).catch(() => {
      setProductListing(null);
    });
  }, []);

  const runAction = async (actionKey: string, action: () => Promise<void>) => {
    setBusyKey(actionKey);
    setError('');
    setStatusMessage('');
    try {
      await action();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Action failed');
    } finally {
      setBusyKey('');
    }
  };

  const pauseAllLabel = useMemo(() => {
    if (!overview?.notification_settings.pause_all_until) {
      return 'Not paused';
    }
    return `Paused until ${new Date(overview.notification_settings.pause_all_until).toLocaleString()}`;
  }, [overview?.notification_settings.pause_all_until]);

  const cardStyle: React.CSSProperties = {
    background: 'rgba(15, 23, 42, 0.84)',
    border: '1px solid #1e293b',
    borderRadius: '20px',
    padding: '16px',
  };

  const premiumStatusLabel = useMemo(() => {
    if (!overview) {
      return 'Loading premium state…';
    }
    if (overview.premium.is_premium) {
      return overview.premium.subscription_status === 'cancelled' ? 'Premium ends at period close' : 'Premium member';
    }
    if (overview.premium.subscription_status === 'pending') {
      return 'Purchase pending';
    }
    return 'Free plan';
  }, [overview]);

  const handleVerifyPurchase = async (purchaseToken: string, orderId?: string) => {
    const response = await apiJson<{ success: boolean; subscription: BillingSubscriptionSummary }>('/api/v1/billing/verify-purchase', {
      method: 'POST',
      body: JSON.stringify({
        product_id: 'bytechat_monthly_40',
        purchase_token: purchaseToken,
        package_name: 'com.omnix.app',
        order_id: orderId,
      }),
    });
    setOverview((current) => current ? {
      ...current,
      premium: response.subscription,
      account: {
        ...current.account,
        is_premium: response.subscription.is_premium,
        subscription_expiry_date: response.subscription.subscription_expiry_date,
        subscription_status: response.subscription.subscription_status,
      },
    } : current);
    return response.subscription;
  };

  const handlePurchase = async () => {
    await runAction('purchase-premium', async () => {
      const result = await launchPlaySubscriptionPurchase('bytechat_monthly_40', getCurrentUserId());
      if (result.status === 'cancelled') {
        setStatusMessage('Purchase cancelled before confirmation.');
        return;
      }
      if (result.status === 'pending') {
        setStatusMessage('Purchase is pending. Google Play will finalize once payment completes.');
        if (result.purchaseToken) {
          await handleVerifyPurchase(result.purchaseToken, result.orderId);
        }
        return;
      }
      if (result.status === 'failed' || !result.purchaseToken) {
        throw new Error(result.message || 'Purchase failed before token generation.');
      }
      const subscription = await handleVerifyPurchase(result.purchaseToken, result.orderId);
      setStatusMessage(subscription.is_premium ? 'Premium unlocked successfully.' : 'Purchase verified but premium access is not active yet.');
      setPaywallOpen(false);
    });
  };

  return (
    <div style={{ minHeight: '100vh', background: 'radial-gradient(circle at top, #132238 0%, #020617 62%, #000 100%)', color: '#f8fafc' }}>
      <div style={{ maxWidth: '920px', margin: '0 auto', padding: '20px 16px 80px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <div>
            <div style={{ fontSize: '12px', letterSpacing: '0.18em', color: '#7dd3fc', textTransform: 'uppercase' }}>Settings</div>
            <div style={{ fontSize: '28px', fontWeight: 900 }}>Profile, Security & Preferences</div>
          </div>
          <button type="button" onClick={onBack} style={{ borderRadius: '999px', border: '1px solid #334155', background: 'transparent', color: '#f8fafc', padding: '10px 14px', cursor: 'pointer' }}>
            Back to profile
          </button>
        </div>

        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '16px' }}>
          {([
            ['premium', 'Premium'],
            ['account', 'Account'],
            ['security', 'Security'],
            ['privacy', 'Privacy'],
            ['archive', 'Archive & Storage'],
            ['notifications', 'Notifications'],
          ] as const).map(([tab, label]) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              style={{
                borderRadius: '999px',
                border: activeTab === tab ? '1px solid #22d3ee' : '1px solid #334155',
                background: activeTab === tab ? 'rgba(34, 211, 238, 0.14)' : '#020617',
                color: '#f8fafc',
                padding: '10px 14px',
                cursor: 'pointer',
              }}
            >
              {label}
            </button>
          ))}
        </div>

        <div style={{ borderRadius: '14px', border: '1px solid #1e293b', background: 'rgba(2, 6, 23, 0.88)', padding: '12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px', flexWrap: 'wrap', marginBottom: '16px' }}>
          <div>
            <div style={{ fontSize: '11px', color: '#7dd3fc', textTransform: 'uppercase', letterSpacing: '0.14em' }}>Legal</div>
            <div style={{ fontSize: '13px', color: '#cbd5e1' }}>Review Terms & Conditions and Privacy Policy.</div>
          </div>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <button type="button" onClick={onOpenTerms} style={{ borderRadius: '999px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '9px 12px', cursor: 'pointer' }}>
              Terms & Conditions
            </button>
            <button type="button" onClick={onOpenPrivacy} style={{ borderRadius: '999px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '9px 12px', cursor: 'pointer' }}>
              Privacy Policy
            </button>
          </div>
        </div>

        {loading ? <div style={{ color: '#94a3b8' }}>Loading settings workspace…</div> : null}
        {!loading && error ? <div style={{ color: '#fca5a5', marginBottom: '12px' }}>{error}</div> : null}
        {!loading && statusMessage ? <div style={{ color: '#86efac', marginBottom: '12px' }}>{statusMessage}</div> : null}

        {!loading && overview ? (
          <div style={{ display: 'grid', gap: '14px' }}>
            {activeTab === 'premium' ? (
              <>
                <section style={{ ...cardStyle, background: 'linear-gradient(160deg, rgba(8, 47, 73, 0.86), rgba(30, 41, 59, 0.88))' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
                    <div>
                      <div style={{ fontSize: '12px', color: '#7dd3fc', textTransform: 'uppercase', letterSpacing: '0.16em', marginBottom: '6px' }}>Subscription</div>
                      <div style={{ fontSize: '26px', fontWeight: 900 }}>ByteChat Premium</div>
                      <div style={{ fontSize: '14px', color: '#cbd5e1', marginTop: '8px', lineHeight: 1.55 }}>
                        {premiumStatusLabel}. Unlock ad-free feed, custom badges, and high-quality calling using Google Play billing.
                      </div>
                    </div>
                    <div style={{ minWidth: '220px', textAlign: 'right' }}>
                      <div style={{ fontSize: '12px', color: '#bae6fd', textTransform: 'uppercase' }}>Current plan</div>
                      <div style={{ fontSize: '22px', fontWeight: 900, color: '#67e8f9' }}>{overview.premium.is_premium ? 'Premium Member' : 'Free'}</div>
                      <div style={{ fontSize: '12px', color: '#cbd5e1', marginTop: '6px' }}>
                        {overview.premium.subscription_expiry_date
                          ? `Renews / expires ${new Date(overview.premium.subscription_expiry_date).toLocaleString()}`
                          : 'No active renewal date'}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginTop: '16px' }}>
                    {!overview.premium.is_premium ? (
                      <button type="button" onClick={() => setPaywallOpen(true)} style={{ borderRadius: '999px', border: 'none', background: '#0f766e', color: '#ecfeff', padding: '12px 16px', cursor: 'pointer', fontWeight: 700 }}>
                        Upgrade to Premium
                      </button>
                    ) : null}
                    <button type="button" onClick={() => openManageSubscription(overview.premium.manage_subscription_url)} style={{ borderRadius: '999px', border: '1px solid #475569', background: 'transparent', color: '#f8fafc', padding: '12px 16px', cursor: 'pointer' }}>
                      Manage / Cancel subscription
                    </button>
                  </div>
                </section>

                <section style={cardStyle}>
                  <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>Plan status</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px' }}>
                    <div><div style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'uppercase' }}>Status</div><div>{overview.premium.subscription_status}</div></div>
                    <div><div style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'uppercase' }}>Product</div><div>{overview.premium.subscription_product_id ?? overview.premium.product_id}</div></div>
                    <div><div style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'uppercase' }}>Renewal / expiry</div><div>{overview.premium.subscription_expiry_date ? new Date(overview.premium.subscription_expiry_date).toLocaleString() : 'Not active'}</div></div>
                    <div><div style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'uppercase' }}>Last verified</div><div>{overview.premium.last_verified_at ? new Date(overview.premium.last_verified_at).toLocaleString() : 'Never'}</div></div>
                  </div>
                </section>
              </>
            ) : null}

            {activeTab === 'account' ? (
              <>
                <section style={cardStyle}>
                  <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>Personal information</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '10px' }}>
                    <input value={personalInfo.phone_number} onChange={(event) => setPersonalInfo((current) => ({ ...current, phone_number: event.target.value }))} placeholder="Phone number" style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '10px 12px' }} />
                    <input value={personalInfo.email} onChange={(event) => setPersonalInfo((current) => ({ ...current, email: event.target.value }))} placeholder="Email address" style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '10px 12px' }} />
                    <input value={personalInfo.gender} onChange={(event) => setPersonalInfo((current) => ({ ...current, gender: event.target.value }))} placeholder="Gender" style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '10px 12px' }} />
                    <input type="date" value={personalInfo.date_of_birth} onChange={(event) => setPersonalInfo((current) => ({ ...current, date_of_birth: event.target.value }))} style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '10px 12px' }} />
                  </div>
                  <button type="button" onClick={() => void runAction('save-personal-info', async () => {
                    const response = await apiJson<{ success: boolean; account: SettingsOverview['account'] }>('/api/settings/account/personal-information', {
                      method: 'PATCH',
                      body: JSON.stringify(personalInfo),
                    });
                    setOverview((current) => current ? { ...current, account: response.account } : current);
                    setStatusMessage('Personal information updated.');
                  })} style={{ marginTop: '12px', borderRadius: '999px', border: 'none', background: '#0f766e', color: '#ecfeff', padding: '10px 14px', cursor: 'pointer' }}>
                    {busyKey === 'save-personal-info' ? 'Saving…' : 'Save personal information'}
                  </button>
                </section>

                <section style={cardStyle}>
                  <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>Account history & status</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px' }}>
                    <div><div style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'uppercase' }}>Created</div><div>{new Date(overview.account.account_created_date).toLocaleDateString()}</div></div>
                    <div><div style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'uppercase' }}>First username</div><div>@{overview.account.first_username}</div></div>
                    <div><div style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'uppercase' }}>Status</div><div>{overview.account.account_status}</div></div>
                    <div><div style={{ fontSize: '11px', color: '#94a3b8', textTransform: 'uppercase' }}>Current username</div><div>@{overview.account.current_username}</div></div>
                  </div>
                </section>

                <section style={cardStyle}>
                  <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>Download my data</div>
                  <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '10px' }}>
                    {([
                      ['include_profile', 'Profile'],
                      ['include_posts', 'Posts'],
                      ['include_messages', 'Messages'],
                    ] as const).map(([key, label]) => (
                      <label key={key} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <input type="checkbox" checked={exportScope[key]} onChange={(event) => setExportScope((current) => ({ ...current, [key]: event.target.checked }))} />
                        {label}
                      </label>
                    ))}
                  </div>
                  {overview.latest_export ? (
                    <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '10px' }}>
                      Latest export: {overview.latest_export.status} • requested {new Date(overview.latest_export.requested_at).toLocaleString()}
                    </div>
                  ) : null}
                  <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                    <button type="button" onClick={() => void runAction('request-export', async () => {
                      const response = await apiJson<{ success: boolean; export: NonNullable<SettingsOverview['latest_export']> }>('/api/settings/account/export', {
                        method: 'POST',
                        body: JSON.stringify(exportScope),
                      });
                      setOverview((current) => current ? { ...current, latest_export: response.export } : current);
                      setStatusMessage('Data export is ready for download.');
                    })} style={{ borderRadius: '999px', border: 'none', background: '#2563eb', color: '#eff6ff', padding: '10px 14px', cursor: 'pointer' }}>
                      {busyKey === 'request-export' ? 'Preparing…' : 'Generate export'}
                    </button>
                    {overview.latest_export?.download_url ? (
                      <button type="button" onClick={() => window.open(`${API_BASE}${overview.latest_export?.download_url}`, '_blank', 'noopener,noreferrer')} style={{ borderRadius: '999px', border: '1px solid #475569', background: 'transparent', color: '#f8fafc', padding: '10px 14px', cursor: 'pointer' }}>
                        Download ZIP
                      </button>
                    ) : null}
                  </div>
                </section>

                <section style={cardStyle}>
                  <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>Account actions</div>
                  <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                    <button type="button" onClick={() => void runAction('deactivate-account', async () => {
                      const response = await apiJson<{ success: boolean; account: SettingsOverview['account']; message: string }>('/api/settings/account/deactivate', {
                        method: 'POST',
                        body: JSON.stringify({ reason: 'user_requested_pause' }),
                      });
                      setOverview((current) => current ? { ...current, account: response.account, sessions: [] } : current);
                      setStatusMessage(response.message);
                    })} style={{ borderRadius: '999px', border: 'none', background: '#7c2d12', color: '#fff7ed', padding: '10px 14px', cursor: 'pointer' }}>
                      {busyKey === 'deactivate-account' ? 'Deactivating…' : 'Temporarily deactivate'}
                    </button>
                    <button type="button" onClick={() => void runAction('delete-account', async () => {
                      const response = await apiJson<{ success: boolean; account: SettingsOverview['account'] }>('/api/settings/account/delete', {
                        method: 'POST',
                        body: JSON.stringify({ reason: 'user_requested_deletion' }),
                      });
                      setOverview((current) => current ? { ...current, account: response.account, sessions: [] } : current);
                      setStatusMessage('Account scheduled for deletion with a 30-day restoration window.');
                    })} style={{ borderRadius: '999px', border: 'none', background: '#7f1d1d', color: '#fef2f2', padding: '10px 14px', cursor: 'pointer' }}>
                      {busyKey === 'delete-account' ? 'Scheduling…' : 'Permanently delete'}
                    </button>
                    {overview.account.can_restore_until ? (
                      <button type="button" onClick={() => void runAction('restore-account', async () => {
                        const response = await apiJson<{ success: boolean; account: SettingsOverview['account'] }>('/api/settings/account/restore', { method: 'POST' });
                        setOverview((current) => current ? { ...current, account: response.account } : current);
                        setStatusMessage('Account restored successfully.');
                      })} style={{ borderRadius: '999px', border: '1px solid #475569', background: 'transparent', color: '#f8fafc', padding: '10px 14px', cursor: 'pointer' }}>
                        {busyKey === 'restore-account' ? 'Restoring…' : 'Restore account'}
                      </button>
                    ) : null}
                  </div>
                </section>
              </>
            ) : null}

            {activeTab === 'security' ? (
              <>
                <section style={cardStyle}>
                  <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>Password management</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '10px' }}>
                    <input type="password" value={passwordForm.current_password} onChange={(event) => setPasswordForm((current) => ({ ...current, current_password: event.target.value }))} placeholder="Current password" style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '10px 12px' }} />
                    <input type="password" value={passwordForm.new_password} onChange={(event) => setPasswordForm((current) => ({ ...current, new_password: event.target.value }))} placeholder="New password" style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '10px 12px' }} />
                  </div>
                  <button type="button" onClick={() => void runAction('change-password', async () => {
                    const response = await apiJson<{ success: boolean; security: SettingsOverview['security'] }>('/api/settings/security/change-password', {
                      method: 'POST',
                      body: JSON.stringify(passwordForm),
                    });
                    setOverview((current) => current ? { ...current, security: response.security } : current);
                    setPasswordForm({ current_password: '', new_password: '' });
                    setStatusMessage('Password changed successfully.');
                  })} style={{ marginTop: '12px', borderRadius: '999px', border: 'none', background: '#0f766e', color: '#ecfeff', padding: '10px 14px', cursor: 'pointer' }}>
                    {busyKey === 'change-password' ? 'Updating…' : 'Change password'}
                  </button>
                </section>

                <section style={cardStyle}>
                  <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>Reset or forgot password</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px' }}>
                    <select value={resetForm.channel} onChange={(event) => setResetForm((current) => ({ ...current, channel: event.target.value }))} style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '10px 12px' }}>
                      <option value="email">Email OTP</option>
                      <option value="sms">SMS OTP</option>
                    </select>
                    <input value={resetForm.destination} onChange={(event) => setResetForm((current) => ({ ...current, destination: event.target.value }))} placeholder="Destination" style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '10px 12px' }} />
                    <button type="button" onClick={() => void runAction('request-password-reset', async () => {
                      const response = await apiJson<{ success: boolean; challenge: { challenge_id: string } }>('/api/settings/security/password-reset/request', {
                        method: 'POST',
                        body: JSON.stringify({ channel: resetForm.channel, destination: resetForm.destination }),
                      });
                      setResetForm((current) => ({ ...current, challenge_id: response.challenge.challenge_id }));
                      setStatusMessage('OTP issued for password reset.');
                    })} style={{ borderRadius: '999px', border: 'none', background: '#2563eb', color: '#eff6ff', padding: '10px 14px', cursor: 'pointer' }}>
                      {busyKey === 'request-password-reset' ? 'Sending…' : 'Send OTP'}
                    </button>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px', marginTop: '12px' }}>
                    <input value={resetForm.challenge_id} onChange={(event) => setResetForm((current) => ({ ...current, challenge_id: event.target.value }))} placeholder="Challenge ID" style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '10px 12px' }} />
                    <input value={resetForm.otp_code} onChange={(event) => setResetForm((current) => ({ ...current, otp_code: event.target.value }))} placeholder="OTP code" style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '10px 12px' }} />
                    <input type="password" value={resetForm.new_password} onChange={(event) => setResetForm((current) => ({ ...current, new_password: event.target.value }))} placeholder="New password" style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '10px 12px' }} />
                  </div>
                  <button type="button" onClick={() => void runAction('verify-password-reset', async () => {
                    await apiJson('/api/settings/security/password-reset/verify', {
                      method: 'POST',
                      body: JSON.stringify({ challenge_id: resetForm.challenge_id, otp_code: resetForm.otp_code, new_password: resetForm.new_password }),
                    });
                    setResetForm((current) => ({ ...current, otp_code: '', new_password: '' }));
                    setStatusMessage('Password reset completed.');
                  })} style={{ marginTop: '12px', borderRadius: '999px', border: '1px solid #475569', background: 'transparent', color: '#f8fafc', padding: '10px 14px', cursor: 'pointer' }}>
                    {busyKey === 'verify-password-reset' ? 'Verifying…' : 'Verify OTP & reset password'}
                  </button>
                </section>

                <section style={cardStyle}>
                  <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>Two-factor authentication</div>
                  <div style={{ fontSize: '13px', color: '#cbd5e1', marginBottom: '10px' }}>
                    Current state: {overview.security.two_factor_enabled ? `Enabled via ${overview.security.two_factor_method}` : 'Disabled'}
                  </div>
                  <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                    <button type="button" onClick={() => void runAction('setup-2fa-totp', async () => {
                      const response = await apiJson<{ success: boolean; setup: { setup_id: string; method: string; qr_code_url: string | null } }>('/api/settings/security/2fa/setup', {
                        method: 'POST',
                        body: JSON.stringify({ method: 'totp' }),
                      });
                      setTwoFactorSetup(response.setup);
                      setStatusMessage('TOTP setup created. Verify the code to enable 2FA.');
                    })} style={{ borderRadius: '999px', border: 'none', background: '#6d28d9', color: '#f5f3ff', padding: '10px 14px', cursor: 'pointer' }}>
                      {busyKey === 'setup-2fa-totp' ? 'Creating…' : 'Set up authenticator app'}
                    </button>
                    <button type="button" onClick={() => void runAction('setup-2fa-sms', async () => {
                      const response = await apiJson<{ success: boolean; setup: { setup_id: string; method: string; phone_number: string | null } }>('/api/settings/security/2fa/setup', {
                        method: 'POST',
                        body: JSON.stringify({ method: 'sms' }),
                      });
                      setTwoFactorSetup(response.setup);
                      setStatusMessage('SMS 2FA setup created. Verify the code to enable 2FA.');
                    })} style={{ borderRadius: '999px', border: '1px solid #475569', background: 'transparent', color: '#f8fafc', padding: '10px 14px', cursor: 'pointer' }}>
                      {busyKey === 'setup-2fa-sms' ? 'Creating…' : 'Set up SMS OTP'}
                    </button>
                    {overview.security.two_factor_enabled ? (
                      <button type="button" onClick={() => void runAction('disable-2fa', async () => {
                        const response = await apiJson<{ success: boolean; security: SettingsOverview['security'] }>('/api/settings/security/2fa/disable', { method: 'POST' });
                        setOverview((current) => current ? { ...current, security: response.security } : current);
                        setTwoFactorSetup(null);
                        setStatusMessage('2FA disabled.');
                      })} style={{ borderRadius: '999px', border: 'none', background: '#7f1d1d', color: '#fef2f2', padding: '10px 14px', cursor: 'pointer' }}>
                        {busyKey === 'disable-2fa' ? 'Disabling…' : 'Disable 2FA'}
                      </button>
                    ) : null}
                  </div>
                  {twoFactorSetup ? (
                    <div style={{ marginTop: '12px', borderRadius: '16px', border: '1px solid #334155', background: '#020617', padding: '12px' }}>
                      <div style={{ fontSize: '12px', color: '#7dd3fc', marginBottom: '8px' }}>Setup ID: {twoFactorSetup.setup_id}</div>
                      {twoFactorSetup.qr_code_url ? <div style={{ fontSize: '12px', color: '#94a3b8', wordBreak: 'break-all', marginBottom: '8px' }}>{twoFactorSetup.qr_code_url}</div> : null}
                      {twoFactorSetup.phone_number ? <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '8px' }}>Verification will be sent to {twoFactorSetup.phone_number}</div> : null}
                      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                        <input value={twoFactorCode} onChange={(event) => setTwoFactorCode(event.target.value)} placeholder="Verification code" style={{ flex: 1, minWidth: '180px', borderRadius: '14px', border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', padding: '10px 12px' }} />
                        <button type="button" onClick={() => void runAction('verify-2fa', async () => {
                          const response = await apiJson<{ success: boolean; security: SettingsOverview['security'] }>('/api/settings/security/2fa/verify', {
                            method: 'POST',
                            body: JSON.stringify({ setup_id: twoFactorSetup.setup_id, code: twoFactorCode }),
                          });
                          setOverview((current) => current ? { ...current, security: response.security } : current);
                          setTwoFactorCode('');
                          setTwoFactorSetup(null);
                          setStatusMessage('2FA enabled successfully.');
                        })} style={{ borderRadius: '999px', border: 'none', background: '#0f766e', color: '#ecfeff', padding: '10px 14px', cursor: 'pointer' }}>
                          {busyKey === 'verify-2fa' ? 'Verifying…' : 'Verify setup'}
                        </button>
                      </div>
                    </div>
                  ) : null}
                </section>

                <section style={cardStyle}>
                  <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>Active login sessions</div>
                  <div style={{ display: 'grid', gap: '10px', marginBottom: '12px' }}>
                    {overview.sessions.map((session) => (
                      <div key={session.id} style={{ borderRadius: '16px', border: '1px solid #334155', background: '#020617', padding: '12px', display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                        <div>
                          <div style={{ fontWeight: 700 }}>{session.device_name} {session.current ? '(Current)' : ''}</div>
                          <div style={{ fontSize: '12px', color: '#94a3b8' }}>{session.os} • {session.location} • {session.ip_address}</div>
                          <div style={{ fontSize: '12px', color: session.recognized ? '#86efac' : '#fca5a5' }}>
                            {session.recognized ? 'Recognized device' : 'Unrecognized device'} • Last active {new Date(session.last_active_at).toLocaleString()}
                          </div>
                        </div>
                        {!session.current ? (
                          <button type="button" onClick={() => void runAction(`logout-session-${session.id}`, async () => {
                            await apiJson(`/api/settings/security/sessions/${session.id}`, { method: 'DELETE' });
                            setOverview((current) => current ? { ...current, sessions: current.sessions.filter((item) => item.id !== session.id) } : current);
                            setStatusMessage('Session ended.');
                          })} style={{ borderRadius: '999px', border: '1px solid #475569', background: 'transparent', color: '#f8fafc', padding: '8px 12px', cursor: 'pointer' }}>
                            {busyKey === `logout-session-${session.id}` ? 'Ending…' : 'Log out'}
                          </button>
                        ) : null}
                      </div>
                    ))}
                  </div>
                  <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '12px' }}>
                    <button type="button" onClick={() => void runAction('logout-other-devices', async () => {
                      await apiJson('/api/settings/security/sessions/logout-all-other-devices', { method: 'POST' });
                      setOverview((current) => current ? { ...current, sessions: current.sessions.filter((session) => session.current) } : current);
                      setStatusMessage('All other sessions were revoked.');
                    })} style={{ borderRadius: '999px', border: 'none', background: '#7c2d12', color: '#fff7ed', padding: '10px 14px', cursor: 'pointer' }}>
                      {busyKey === 'logout-other-devices' ? 'Revoking…' : 'Log out from all other devices'}
                    </button>
                  </div>
                  <div style={{ display: 'grid', gap: '10px', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
                    <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      Login alerts
                      <input type="checkbox" checked={overview.security.login_alerts_enabled} onChange={async (event) => {
                        const nextValue = event.target.checked;
                        await runAction('update-security-alerts', async () => {
                          const response = await apiJson<{ success: boolean; security: SettingsOverview['security'] }>('/api/settings/security/alerts', {
                            method: 'PATCH',
                            body: JSON.stringify({
                              login_alerts_enabled: nextValue,
                              unrecognized_device_alerts: overview.security.unrecognized_device_alerts,
                            }),
                          });
                          setOverview((current) => current ? { ...current, security: response.security } : current);
                          setStatusMessage('Security alerts updated.');
                        });
                      }} />
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      New unrecognized device alerts
                      <input type="checkbox" checked={overview.security.unrecognized_device_alerts} onChange={async (event) => {
                        const nextValue = event.target.checked;
                        await runAction('update-security-alerts', async () => {
                          const response = await apiJson<{ success: boolean; security: SettingsOverview['security'] }>('/api/settings/security/alerts', {
                            method: 'PATCH',
                            body: JSON.stringify({
                              login_alerts_enabled: overview.security.login_alerts_enabled,
                              unrecognized_device_alerts: nextValue,
                            }),
                          });
                          setOverview((current) => current ? { ...current, security: response.security } : current);
                          setStatusMessage('Security alerts updated.');
                        });
                      }} />
                    </label>
                  </div>
                </section>
              </>
            ) : null}

            {activeTab === 'privacy' ? (
              <>
                <section style={cardStyle}>
                  <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>Blocked accounts</div>
                  <div style={{ display: 'grid', gap: '10px' }}>
                    {overview.blocked_accounts.map((blocked) => (
                      <div key={blocked.user_id} style={{ borderRadius: '16px', border: '1px solid #334155', background: '#020617', padding: '12px', display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                        <div>
                          <div style={{ fontWeight: 700 }}>{blocked.display_name}</div>
                          <div style={{ fontSize: '12px', color: '#94a3b8' }}>@{blocked.username} • blocked {new Date(blocked.blocked_at).toLocaleString()}</div>
                        </div>
                        <button type="button" onClick={() => void runAction(`unblock-${blocked.user_id}`, async () => {
                          await apiJson(`/api/users/${blocked.user_id}/block`, { method: 'DELETE' });
                          setOverview((current) => current ? { ...current, blocked_accounts: current.blocked_accounts.filter((item) => item.user_id !== blocked.user_id) } : current);
                          setStatusMessage('Blocked account removed.');
                        })} style={{ borderRadius: '999px', border: '1px solid #475569', background: 'transparent', color: '#f8fafc', padding: '8px 12px', cursor: 'pointer' }}>
                          {busyKey === `unblock-${blocked.user_id}` ? 'Updating…' : 'Unblock'}
                        </button>
                      </div>
                    ))}
                    {!overview.blocked_accounts.length ? <div style={{ color: '#94a3b8' }}>No blocked accounts.</div> : null}
                  </div>
                </section>

                <section style={cardStyle}>
                  <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>Muted accounts</div>
                  {(['posts', 'stories', 'chats'] as const).map((group) => (
                    <div key={group} style={{ marginBottom: '12px' }}>
                      <div style={{ fontSize: '12px', color: '#7dd3fc', textTransform: 'uppercase', marginBottom: '8px' }}>{group}</div>
                      <div style={{ display: 'grid', gap: '8px' }}>
                        {overview.muted_accounts[group].map((mute) => (
                          <div key={`${group}-${mute.user_id}`} style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', padding: '10px 12px', display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                            <div>
                              <div style={{ fontWeight: 700 }}>{mute.display_name}</div>
                              <div style={{ fontSize: '12px', color: '#94a3b8' }}>@{mute.username} • expires {mute.expires_at ? new Date(mute.expires_at).toLocaleString() : 'Never'}</div>
                            </div>
                            <button type="button" onClick={() => void runAction(`unmute-${group}-${mute.user_id}`, async () => {
                              const muteType = group === 'chats' ? 'user' : group;
                              await apiJson(`/api/users/${mute.user_id}/mute`, { method: 'DELETE', query: { mute_type: muteType } });
                              setOverview((current) => current ? { ...current, muted_accounts: { ...current.muted_accounts, [group]: current.muted_accounts[group].filter((item) => item.user_id !== mute.user_id) } } : current);
                              setStatusMessage('Mute removed.');
                            })} style={{ borderRadius: '999px', border: '1px solid #475569', background: 'transparent', color: '#f8fafc', padding: '8px 12px', cursor: 'pointer' }}>
                              {busyKey === `unmute-${group}-${mute.user_id}` ? 'Removing…' : 'Unmute'}
                            </button>
                          </div>
                        ))}
                        {!overview.muted_accounts[group].length ? <div style={{ color: '#94a3b8', fontSize: '12px' }}>No muted {group}.</div> : null}
                      </div>
                    </div>
                  ))}
                </section>

                <section style={cardStyle}>
                  <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>Content preferences</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '10px' }}>
                    <select value={overview.content_preferences.sensitive_content_control} onChange={async (event) => {
                      const nextValue = event.target.value as SettingsOverview['content_preferences']['sensitive_content_control'];
                      await runAction('update-content-preferences', async () => {
                        const response = await apiJson<{ success: boolean; content_preferences: SettingsOverview['content_preferences'] }>('/api/settings/privacy/content-preferences', {
                          method: 'PATCH',
                          body: JSON.stringify({ ...overview.content_preferences, sensitive_content_control: nextValue }),
                        });
                        setOverview((current) => current ? { ...current, content_preferences: response.content_preferences } : current);
                        setStatusMessage('Content preferences updated.');
                      });
                    }} style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '10px 12px' }}>
                      <option value="standard">Sensitive content: Standard</option>
                      <option value="less">Sensitive content: Less</option>
                      <option value="more">Sensitive content: More</option>
                    </select>
                    <select value={overview.content_preferences.mention_policy} onChange={async (event) => {
                      const nextValue = event.target.value as SettingsOverview['content_preferences']['mention_policy'];
                      await runAction('update-content-preferences', async () => {
                        const response = await apiJson<{ success: boolean; content_preferences: SettingsOverview['content_preferences'] }>('/api/settings/privacy/content-preferences', {
                          method: 'PATCH',
                          body: JSON.stringify({ ...overview.content_preferences, mention_policy: nextValue }),
                        });
                        setOverview((current) => current ? { ...current, content_preferences: response.content_preferences } : current);
                        setStatusMessage('Mention policy updated.');
                      });
                    }} style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '10px 12px' }}>
                      <option value="everyone">Mention: Everyone</option>
                      <option value="people_you_follow">Mention: People you follow</option>
                      <option value="no_one">Mention: No one</option>
                    </select>
                    <select value={overview.content_preferences.tag_policy} onChange={async (event) => {
                      const nextValue = event.target.value as SettingsOverview['content_preferences']['tag_policy'];
                      await runAction('update-content-preferences', async () => {
                        const response = await apiJson<{ success: boolean; content_preferences: SettingsOverview['content_preferences'] }>('/api/settings/privacy/content-preferences', {
                          method: 'PATCH',
                          body: JSON.stringify({ ...overview.content_preferences, tag_policy: nextValue }),
                        });
                        setOverview((current) => current ? { ...current, content_preferences: response.content_preferences } : current);
                        setStatusMessage('Tag policy updated.');
                      });
                    }} style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '10px 12px' }}>
                      <option value="everyone">Tag: Everyone</option>
                      <option value="people_you_follow">Tag: People you follow</option>
                      <option value="no_one">Tag: No one</option>
                    </select>
                    <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderRadius: '14px', border: '1px solid #334155', background: '#020617', padding: '10px 12px' }}>
                      Hide like & view counts
                      <input type="checkbox" checked={overview.content_preferences.hide_like_view_counts} onChange={async (event) => {
                        const nextValue = event.target.checked;
                        await runAction('update-content-preferences', async () => {
                          const response = await apiJson<{ success: boolean; content_preferences: SettingsOverview['content_preferences'] }>('/api/settings/privacy/content-preferences', {
                            method: 'PATCH',
                            body: JSON.stringify({ ...overview.content_preferences, hide_like_view_counts: nextValue }),
                          });
                          setOverview((current) => current ? { ...current, content_preferences: response.content_preferences } : current);
                          setStatusMessage('Count visibility updated.');
                        });
                      }} />
                    </label>
                  </div>
                </section>
              </>
            ) : null}

            {activeTab === 'archive' ? (
              <>
                <section style={cardStyle}>
                  <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>Archived media</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
                    <div>
                      <div style={{ fontSize: '12px', color: '#7dd3fc', textTransform: 'uppercase', marginBottom: '8px' }}>Archived posts</div>
                      <div style={{ display: 'grid', gap: '8px' }}>
                        {overview.archives.posts.map((item) => (
                          <div key={item.id} style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', padding: '10px 12px' }}>
                            <div style={{ fontWeight: 700 }}>{item.caption}</div>
                            <div style={{ fontSize: '12px', color: '#94a3b8' }}>{new Date(item.archived_at).toLocaleString()}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: '12px', color: '#7dd3fc', textTransform: 'uppercase', marginBottom: '8px' }}>Archived stories</div>
                      <div style={{ display: 'grid', gap: '8px' }}>
                        {overview.archives.stories.map((item) => (
                          <div key={item.id} style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', padding: '10px 12px' }}>
                            <div style={{ fontWeight: 700 }}>{item.title}</div>
                            <div style={{ fontSize: '12px', color: '#94a3b8' }}>{new Date(item.archived_at).toLocaleString()}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </section>

                <section style={cardStyle}>
                  <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>Story settings</div>
                  <div style={{ display: 'grid', gap: '10px' }}>
                    <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      Auto-save stories to archive
                      <input type="checkbox" checked={overview.story_settings.auto_save_to_archive} onChange={async (event) => {
                        const nextValue = event.target.checked;
                        await runAction('update-story-settings', async () => {
                          const response = await apiJson<{ success: boolean; story_settings: SettingsOverview['story_settings'] }>('/api/settings/archive/story-settings', {
                            method: 'PATCH',
                            body: JSON.stringify({
                              auto_save_to_archive: nextValue,
                              save_to_phone_gallery: overview.story_settings.save_to_phone_gallery,
                            }),
                          });
                          setOverview((current) => current ? { ...current, story_settings: response.story_settings } : current);
                          setStatusMessage('Story settings updated.');
                        });
                      }} />
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      Save stories to phone gallery
                      <input type="checkbox" checked={overview.story_settings.save_to_phone_gallery} onChange={async (event) => {
                        const nextValue = event.target.checked;
                        await runAction('update-story-settings', async () => {
                          const response = await apiJson<{ success: boolean; story_settings: SettingsOverview['story_settings'] }>('/api/settings/archive/story-settings', {
                            method: 'PATCH',
                            body: JSON.stringify({
                              auto_save_to_archive: overview.story_settings.auto_save_to_archive,
                              save_to_phone_gallery: nextValue,
                            }),
                          });
                          setOverview((current) => current ? { ...current, story_settings: response.story_settings } : current);
                          setStatusMessage('Story settings updated.');
                        });
                      }} />
                    </label>
                  </div>
                </section>

                <section style={cardStyle}>
                  <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>Data & storage usage</div>
                  <div style={{ display: 'grid', gap: '10px' }}>
                    <div style={{ fontSize: '13px', color: '#cbd5e1' }}>Local cache size: {overview.storage_settings.cache_size_mb} MB</div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '10px' }}>
                      <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderRadius: '14px', border: '1px solid #334155', background: '#020617', padding: '10px 12px' }}>
                        Cellular data saver
                        <input type="checkbox" checked={overview.storage_settings.cellular_data_saver} onChange={async (event) => {
                          const nextValue = event.target.checked;
                          await runAction('update-storage-settings', async () => {
                            const response = await apiJson<{ success: boolean; storage_settings: SettingsOverview['storage_settings'] }>('/api/settings/storage/preferences', {
                              method: 'PATCH',
                              body: JSON.stringify({
                                cellular_data_saver: nextValue,
                                photo_auto_download: overview.storage_settings.photo_auto_download,
                                video_auto_download: overview.storage_settings.video_auto_download,
                              }),
                            });
                            setOverview((current) => current ? { ...current, storage_settings: response.storage_settings } : current);
                            setStatusMessage('Storage preferences updated.');
                          });
                        }} />
                      </label>
                      <select value={overview.storage_settings.photo_auto_download} onChange={async (event) => {
                        const nextValue = event.target.value as SettingsOverview['storage_settings']['photo_auto_download'];
                        await runAction('update-storage-settings', async () => {
                          const response = await apiJson<{ success: boolean; storage_settings: SettingsOverview['storage_settings'] }>('/api/settings/storage/preferences', {
                            method: 'PATCH',
                            body: JSON.stringify({
                              cellular_data_saver: overview.storage_settings.cellular_data_saver,
                              photo_auto_download: nextValue,
                              video_auto_download: overview.storage_settings.video_auto_download,
                            }),
                          });
                          setOverview((current) => current ? { ...current, storage_settings: response.storage_settings } : current);
                          setStatusMessage('Photo download preference updated.');
                        });
                      }} style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '10px 12px' }}>
                        <option value="wifi_only">Photos: Wi-Fi only</option>
                        <option value="mobile_data">Photos: Mobile data</option>
                      </select>
                      <select value={overview.storage_settings.video_auto_download} onChange={async (event) => {
                        const nextValue = event.target.value as SettingsOverview['storage_settings']['video_auto_download'];
                        await runAction('update-storage-settings', async () => {
                          const response = await apiJson<{ success: boolean; storage_settings: SettingsOverview['storage_settings'] }>('/api/settings/storage/preferences', {
                            method: 'PATCH',
                            body: JSON.stringify({
                              cellular_data_saver: overview.storage_settings.cellular_data_saver,
                              photo_auto_download: overview.storage_settings.photo_auto_download,
                              video_auto_download: nextValue,
                            }),
                          });
                          setOverview((current) => current ? { ...current, storage_settings: response.storage_settings } : current);
                          setStatusMessage('Video download preference updated.');
                        });
                      }} style={{ borderRadius: '14px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '10px 12px' }}>
                        <option value="wifi_only">Videos: Wi-Fi only</option>
                        <option value="mobile_data">Videos: Mobile data</option>
                      </select>
                    </div>
                    <button type="button" onClick={() => void runAction('clear-cache', async () => {
                      const response = await apiJson<{ success: boolean; cache_size_mb: number; cleared_mb: number }>('/api/settings/storage/clear-cache', { method: 'POST' });
                      setOverview((current) => current ? { ...current, storage_settings: { ...current.storage_settings, cache_size_mb: response.cache_size_mb } } : current);
                      setStatusMessage(`Cleared ${response.cleared_mb} MB of local cache.`);
                    })} style={{ width: 'fit-content', borderRadius: '999px', border: '1px solid #475569', background: 'transparent', color: '#f8fafc', padding: '10px 14px', cursor: 'pointer' }}>
                      {busyKey === 'clear-cache' ? 'Clearing…' : 'Clear cache'}
                    </button>
                  </div>
                </section>
              </>
            ) : null}

            {activeTab === 'notifications' ? (
              <>
                <section style={cardStyle}>
                  <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>Pause all notifications</div>
                  <div style={{ fontSize: '13px', color: '#cbd5e1', marginBottom: '10px' }}>{pauseAllLabel}</div>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    {(['15m', '1h', '2h', '4h', '8h'] as const).map((duration) => (
                      <button key={duration} type="button" onClick={() => void runAction(`pause-${duration}`, async () => {
                        const response = await apiJson<{ success: boolean; notification_settings: SettingsOverview['notification_settings'] }>('/api/settings/notifications/pause-all', {
                          method: 'POST',
                          body: JSON.stringify({ duration }),
                        });
                        setOverview((current) => current ? { ...current, notification_settings: response.notification_settings } : current);
                        setStatusMessage(`Notifications paused for ${duration}.`);
                      })} style={{ borderRadius: '999px', border: '1px solid #334155', background: '#020617', color: '#f8fafc', padding: '8px 12px', cursor: 'pointer' }}>
                        {duration}
                      </button>
                    ))}
                  </div>
                </section>

                <section style={cardStyle}>
                  <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '12px' }}>Push notification controls</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '10px' }}>
                    {([
                      ['push_likes', 'Likes'],
                      ['push_comments', 'Comments'],
                      ['push_new_followers', 'New followers'],
                      ['push_direct_messages', 'Direct messages'],
                      ['push_calls', 'Calls'],
                      ['push_app_updates', 'App updates & announcements'],
                    ] as const).map(([key, label]) => (
                      <label key={key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderRadius: '14px', border: '1px solid #334155', background: '#020617', padding: '10px 12px' }}>
                        {label}
                        <input type="checkbox" checked={overview.notification_settings[key]} onChange={async (event) => {
                          const nextSettings = { ...overview.notification_settings, [key]: event.target.checked };
                          await runAction('update-notifications', async () => {
                            const response = await apiJson<{ success: boolean; notification_settings: SettingsOverview['notification_settings'] }>('/api/settings/notifications', {
                              method: 'PATCH',
                              body: JSON.stringify({
                                push_likes: nextSettings.push_likes,
                                push_comments: nextSettings.push_comments,
                                push_new_followers: nextSettings.push_new_followers,
                                push_direct_messages: nextSettings.push_direct_messages,
                                push_calls: nextSettings.push_calls,
                                push_app_updates: nextSettings.push_app_updates,
                              }),
                            });
                            setOverview((current) => current ? { ...current, notification_settings: response.notification_settings } : current);
                            setStatusMessage('Notification preferences updated.');
                          });
                        }} />
                      </label>
                    ))}
                  </div>
                </section>
              </>
            ) : null}
          </div>
        ) : null}

        <PremiumPaywallModal
          open={paywallOpen}
          product={productListing}
          subscription={overview?.premium ?? null}
          busy={busyKey === 'purchase-premium'}
          statusMessage={busyKey === 'purchase-premium' ? 'Waiting for Google Play response…' : statusMessage}
          error={error}
          onClose={() => setPaywallOpen(false)}
          onPurchase={handlePurchase}
          onManageSubscription={() => {
            if (overview) {
              openManageSubscription(overview.premium.manage_subscription_url);
            }
          }}
        />
      </div>
    </div>
  );
}