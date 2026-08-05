# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x (Beta) | ✅ Active |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Please report security issues by emailing the project maintainer directly. Include:

1. Description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Suggested fix (optional)

You will receive a response within 48 hours. If the issue is confirmed, a patch will be released and you will be credited (unless you prefer anonymity).

## Security Hardening Applied

The following security controls are implemented:

### Authentication
- JWT-based session tokens via Supabase Auth
- Passwords hashed with bcrypt (work factor ≥ 12)
- Phone 2FA OTP for signup verification
- Session tokens stored in `localStorage` (not cookies — XSS risk mitigated by CSP)
- `EXPOSE_DEV_OTP` env var must be set to `false` in production

### Authorization
- Row Level Security (RLS) enabled on all Supabase tables
- Every API route validates user identity via `X-User-Id` + `Authorization: Bearer` header
- Admin routes require `X-Role: admin` header (enforced server-side)

### Rate Limiting
- Login: 5 requests/minute per IP
- Signup: 3 requests/minute per IP
- OTP send: 3 requests/minute per IP
- Forgot password: 2 requests/minute per IP
- Availability check: 10 requests/minute per IP

### Input Validation
- All request bodies validated via Pydantic models
- Post content: non-empty, max 5000 characters
- Username: alphanumeric + underscore, 3–30 characters
- Email: RFC-5322 validated via `email-validator`
- Auto content moderation flags spam/hate/phishing keywords

### Infrastructure
- All secrets loaded from environment variables — never from source code
- `api-credentials.json` is a template only; no real values
- CORS origins explicitly restricted
- HTTPS required in production (TLS terminated at reverse proxy)

## Known Limitations (Beta)

- Token refresh is implemented but session revocation list is not yet persisted across restarts (in-memory only).
- The `database/users.db` SQLite fallback is for local development only; always configure Supabase in production.
- Rate limit state is in-memory; restart clears limits. Use Redis-backed SlowAPI for production.

## Dependency Security

Run `pip audit` and `npm audit` before deploying to check for known CVEs in dependencies.
