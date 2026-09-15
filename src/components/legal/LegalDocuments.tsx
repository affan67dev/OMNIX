import React from 'react';

export type LegalDocumentType = 'terms' | 'privacy';

function legalCardStyle(): React.CSSProperties {
  return {
    width: '100%',
    maxWidth: '860px',
    maxHeight: '85vh',
    overflowY: 'auto',
    borderRadius: '22px',
    padding: '22px',
    background: 'linear-gradient(170deg, #ffffff 0%, #f8fafc 100%)',
    color: '#111827',
    border: '1px solid #e2e8f0',
    boxShadow: '0 24px 60px rgba(15, 23, 42, 0.28)',
  };
}

export function LegalDocumentView({ type }: { type: LegalDocumentType }) {
  if (type === 'privacy') {
    return (
      <div>
        <h1 style={{ margin: 0, fontSize: '28px', fontWeight: 900 }}>Privacy Policy</h1>
        <p style={{ color: '#475569', marginTop: '8px' }}>Last updated: 2026-07-21</p>

        <h2 style={{ marginTop: '18px', fontSize: '17px' }}>1. What We Collect</h2>
        <p>We collect account identity information required to operate OMNIX, including username, email, verified phone metadata, authentication artifacts, and security settings.</p>

        <h2 style={{ marginTop: '18px', fontSize: '17px' }}>2. How We Use Data</h2>
        <p>Data is processed for account access, messaging delivery, fraud prevention, abuse moderation, legal compliance, subscription verification, and service quality improvement.</p>

        <h2 style={{ marginTop: '18px', fontSize: '17px' }}>3. Encryption & Security</h2>
        <p>OMNIX applies transport encryption and secure storage controls. End-to-end encrypted payload handling and local lock controls are implemented where supported by your device.</p>

        <h2 style={{ marginTop: '18px', fontSize: '17px' }}>4. App Store & Platform Compliance</h2>
        <p>For Google Play and Apple App Store distribution, we process only data required for app functionality, security, billing validation, and policy enforcement. Platform account and payment services are governed by their own terms.</p>

        <h2 style={{ marginTop: '18px', fontSize: '17px' }}>5. Content, Safety & Enforcement</h2>
        <p>To protect users, we may process abuse signals, reports, and moderation actions. Illegal content, harassment, impersonation, fraud, and exploitation are prohibited and may result in suspension or deletion.</p>

        <h2 style={{ marginTop: '18px', fontSize: '17px' }}>6. User-Generated Content & Copyright Processing</h2>
        <p>You control your uploads, captions, mentions, comments, and story overlays, but you are responsible for rights ownership and lawful publishing. We may process copyright notices, repeat infringement signals, and takedown requests under applicable law and app-store policy.</p>

        <h2 style={{ marginTop: '18px', fontSize: '17px' }}>7. Data Sharing</h2>
        <p>We do not sell personal data. Data may be shared with infrastructure providers or legal authorities only when required to operate the service, investigate abuse, comply with law, or protect rights and safety.</p>

        <h2 style={{ marginTop: '18px', fontSize: '17px' }}>8. Retention & Deletion</h2>
        <p>Data is retained for operational and legal obligations. Account deletion requests follow platform and legal retention windows, including abuse prevention and financial records where applicable.</p>

        <h2 style={{ marginTop: '18px', fontSize: '17px' }}>9. Your Rights</h2>
        <p>Where applicable, you may request data access, correction, export, restriction, or deletion through in-app settings or support channels.</p>
      </div>
    );
  }

  return (
    <div>
      <h1 style={{ margin: 0, fontSize: '28px', fontWeight: 900 }}>Terms & Conditions</h1>
      <p style={{ color: '#475569', marginTop: '8px' }}>Last updated: 2026-07-21</p>

      <h2 style={{ marginTop: '18px', fontSize: '17px' }}>1. Acceptance of Terms</h2>
      <p>By creating an account or using OMNIX (OMNIX), you agree to these terms and our Privacy Policy. If you do not agree, do not use the service.</p>

      <h2 style={{ marginTop: '18px', fontSize: '17px' }}>2. Eligibility & Account Responsibility</h2>
      <p>You are responsible for your credentials, account activity, and lawful use. You must provide accurate registration information and keep it updated.</p>

      <h2 style={{ marginTop: '18px', fontSize: '17px' }}>3. Acceptable Use & Content Guidelines</h2>
      <p>Prohibited behavior includes illegal activity, hateful or violent threats, child exploitation, non-consensual sexual content, malware distribution, impersonation, and coordinated abuse.</p>

      <h2 style={{ marginTop: '18px', fontSize: '17px' }}>4. User-Generated Content License</h2>
      <p>You retain ownership of your content but grant OMNIX a limited, worldwide, royalty-free license to host, process, moderate, and display content for service operation, abuse prevention, and legal compliance.</p>

      <h2 style={{ marginTop: '18px', fontSize: '17px' }}>5. Moderation & Enforcement</h2>
      <p>We may remove content, restrict features, suspend sessions, or terminate accounts to enforce safety, legal duties, and platform policy compliance.</p>

      <h2 style={{ marginTop: '18px', fontSize: '17px' }}>6. Copyright & IP Complaints</h2>
      <p>If you believe content infringes your rights, you may submit a notice with proof of ownership and contact details. We may remove challenged content, warn users, and terminate repeat infringers where required.</p>

      <h2 style={{ marginTop: '18px', fontSize: '17px' }}>7. Subscriptions & Billing</h2>
      <p>Premium subscriptions purchased through Google Play or Apple App Store are managed by those platforms. Renewal, cancellation, refunds, and taxes follow the applicable store policies.</p>

      <h2 style={{ marginTop: '18px', fontSize: '17px' }}>8. App Store Distribution & Liability Boundaries</h2>
      <p>Apple and Google are not responsible for service content, support obligations, dispute handling, or claims arising from platform misuse. App-store terms apply separately to purchases and device-level permissions.</p>

      <h2 style={{ marginTop: '18px', fontSize: '17px' }}>9. Liability Limitations</h2>
      <p>To the maximum extent allowed by law, OMNIX is provided on an "as is" basis without warranties. We are not liable for indirect, incidental, consequential, or punitive damages arising from your use.</p>

      <h2 style={{ marginTop: '18px', fontSize: '17px' }}>10. User Liability & Indemnity</h2>
      <p>You are solely responsible for content and actions on your account and agree to indemnify OMNIX against claims, losses, and legal costs resulting from your misuse or policy violations.</p>

      <h2 style={{ marginTop: '18px', fontSize: '17px' }}>11. Policy Updates</h2>
      <p>We may update these terms for product, legal, or safety reasons. Continued use after updates constitutes acceptance of the revised terms.</p>
    </div>
  );
}

export function LegalDocumentModal({
  open,
  type,
  onClose,
}: {
  open: boolean;
  type: LegalDocumentType;
  onClose: () => void;
}) {
  if (!open) {
    return null;
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 300,
        background: 'rgba(2, 6, 23, 0.82)',
        backdropFilter: 'blur(3px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
      }}
    >
      <div style={legalCardStyle()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
          <div style={{ fontSize: '12px', color: '#0369a1', textTransform: 'uppercase', letterSpacing: '0.14em', fontWeight: 700 }}>
            Legal
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              borderRadius: '999px',
              border: '1px solid #cbd5e1',
              background: '#ffffff',
              color: '#0f172a',
              padding: '8px 12px',
              cursor: 'pointer',
              fontWeight: 700,
            }}
          >
            Close
          </button>
        </div>
        <LegalDocumentView type={type} />
      </div>
    </div>
  );
}
