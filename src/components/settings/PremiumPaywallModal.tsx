import React from 'react';
import type { BillingSubscriptionSummary, ProductListing } from '../../types/billing';

type Props = {
  open: boolean;
  product: ProductListing | null;
  subscription: BillingSubscriptionSummary | null;
  busy: boolean;
  statusMessage: string;
  error: string;
  onClose: () => void;
  onPurchase: () => Promise<void>;
  onManageSubscription: () => void;
};

const featureCards = [
  {
    title: 'Ad-Free',
    description: 'Remove interruptions across feed, chat, and profile views.',
  },
  {
    title: 'Custom Badges',
    description: 'Display premium identity flair and profile-level recognition.',
  },
  {
    title: 'HQ Calls',
    description: 'Unlock high quality audio and video calling presets.',
  },
];

export function PremiumPaywallModal({ open, product, subscription, busy, statusMessage, error, onClose, onPurchase, onManageSubscription }: Props) {
  if (!open) {
    return null;
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(2, 6, 23, 0.9)', backdropFilter: 'blur(14px)', zIndex: 90, overflowY: 'auto' }}>
      <div style={{ maxWidth: '680px', margin: '32px auto', padding: '0 16px' }}>
        <div style={{ background: 'linear-gradient(160deg, rgba(8, 47, 73, 0.96), rgba(30, 41, 59, 0.96))', border: '1px solid rgba(125, 211, 252, 0.28)', borderRadius: '28px', padding: '22px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
            <div>
              <div style={{ fontSize: '12px', letterSpacing: '0.18em', color: '#7dd3fc', textTransform: 'uppercase' }}>Premium</div>
              <div style={{ fontSize: '28px', fontWeight: 900, color: '#f8fafc' }}>Upgrade to OMNIX Premium</div>
            </div>
            <button type="button" onClick={onClose} style={{ borderRadius: '999px', border: '1px solid #475569', background: 'transparent', color: '#f8fafc', width: '42px', height: '42px', cursor: 'pointer' }}>
              ✕
            </button>
          </div>

          <div style={{ fontSize: '14px', color: '#cbd5e1', marginBottom: '18px', lineHeight: 1.55 }}>
            Unlock a premium calling, identity, and messaging experience with Google Play subscription billing.
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '12px', marginBottom: '18px' }}>
            {featureCards.map((feature) => (
              <div key={feature.title} style={{ borderRadius: '20px', border: '1px solid rgba(148, 163, 184, 0.22)', background: 'rgba(15, 23, 42, 0.78)', padding: '14px' }}>
                <div style={{ fontSize: '15px', fontWeight: 800, color: '#f8fafc', marginBottom: '8px' }}>{feature.title}</div>
                <div style={{ fontSize: '13px', color: '#cbd5e1', lineHeight: 1.5 }}>{feature.description}</div>
              </div>
            ))}
          </div>

          <div style={{ borderRadius: '20px', border: '1px solid rgba(125, 211, 252, 0.24)', background: 'rgba(8, 47, 73, 0.48)', padding: '16px', marginBottom: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: '18px', fontWeight: 800, color: '#f8fafc' }}>{product?.title ?? 'OMNIX Premium'}</div>
                <div style={{ fontSize: '13px', color: '#cbd5e1' }}>{product?.description ?? 'Monthly subscription billed via Google Play.'}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '24px', fontWeight: 900, color: '#67e8f9' }}>{product?.price ?? '$0.40/month'}</div>
                <div style={{ fontSize: '11px', color: '#bae6fd' }}>{product?.billingPeriod ?? 'P1M'}</div>
              </div>
            </div>
          </div>

          {statusMessage ? <div style={{ color: '#86efac', marginBottom: '10px' }}>{statusMessage}</div> : null}
          {error ? <div style={{ color: '#fca5a5', marginBottom: '10px' }}>{error}</div> : null}

          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <button type="button" onClick={() => void onPurchase()} style={{ borderRadius: '999px', border: 'none', background: '#0f766e', color: '#ecfeff', padding: '12px 16px', cursor: 'pointer', fontWeight: 700 }}>
              {busy ? 'Processing…' : 'Continue with Google Play'}
            </button>
            {subscription?.is_premium ? (
              <button type="button" onClick={onManageSubscription} style={{ borderRadius: '999px', border: '1px solid #475569', background: 'transparent', color: '#f8fafc', padding: '12px 16px', cursor: 'pointer' }}>
                Manage / Cancel subscription
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}