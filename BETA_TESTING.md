# OMNIX Beta Testing Guide

Welcome to the OMNIX beta program! This guide helps you set up, test, and report issues.

## Prerequisites

- Android device running Android 8.0+ (API 26+), or a modern web browser
- A Supabase account (free tier is fine)
- Node.js 20+ and Python 3.12+ for local backend

## Setup (Local / Web)

1. **Clone and install**
   ```bash
   git clone https://github.com/affan67dev/OMNIX.git
   cd OMNIX
   npm install
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Fill in VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY, VITE_API_BASE_URL
   ```

3. **Apply database migrations**
   - Open your Supabase project → SQL Editor
   - Run files in `supabase/migrations/` in timestamp order

4. **Start backend**
   ```bash
   uvicorn main:app --reload --port 8000
   ```

5. **Start frontend**
   ```bash
   npm run dev
   ```
   Open `http://localhost:80` in your browser.

## Docker (Recommended)

```bash
cp .env.example .env  # Fill in values
npm run build         # Build frontend into dist/
docker compose up
```

## Test Coverage Areas

Please focus beta testing on these critical flows:

### Authentication
- [ ] Signup with email + phone OTP verification
- [ ] Login with email/password
- [ ] Login with username
- [ ] Forgot password (email + phone reset)
- [ ] Token expiry and auto-refresh
- [ ] Logout from all sessions

### Chat
- [ ] Send text messages
- [ ] Receive real-time messages (Pusher)
- [ ] Offline message queuing (disable network, send, re-enable)
- [ ] Typing indicator
- [ ] Message read receipts
- [ ] End-to-end encryption (zero-knowledge mode)
- [ ] Chat lock (biometric/PIN protection)

### Feed & Social
- [ ] Post creation with text and image
- [ ] Feed ranking (engagement-based)
- [ ] Like, comment, share
- [ ] Follow / unfollow users
- [ ] Private account follow requests
- [ ] Search users

### Profile
- [ ] Edit profile (name, bio, profile pic)
- [ ] View public vs private profiles
- [ ] Verified badge display

### Security Features
- [ ] DM lock (conversation-level PIN)
- [ ] Ghost mode (OneWayGhost)
- [ ] Session reaper (auto-logout on inactivity)
- [ ] Blur shield on screenshots

### Performance
- [ ] App startup time (< 3 seconds)
- [ ] Message send latency (< 1 second on good network)
- [ ] Feed load time (< 2 seconds)
- [ ] Offline handling (graceful degraded mode)

## Reporting Bugs

Please open a GitHub Issue with:

1. **Title**: Short description (e.g., "Login: OTP not received on +91 numbers")
2. **Steps to reproduce**: Numbered list
3. **Expected behavior**
4. **Actual behavior**
5. **Device / browser / OS version**
6. **Screenshot or screen recording** (if applicable)
7. **Logs** (browser console or Android logcat)

**Label** your issue: `bug`, `beta-feedback`, `performance`, `security` as appropriate.

## Known Issues

| Issue | Severity | Status |
|-------|----------|--------|
| Rate limit state resets on server restart | Low | Won't fix (beta) |
| Token revocation not persisted across restarts | Medium | Planned |
| SQLite fallback for dev only | Low | By design |
| Agora voice/video requires valid App Certificate | High | Config required |
| Firebase push notifications require Google Services setup | High | Config required |

## Production Deployment Notes

For the production deployment:

1. Set `EXPOSE_DEV_OTP=false` — never expose OTP codes in responses
2. Set `ENABLE_DOCS=false` — disable Swagger UI in production
3. Use a strong random `SECRET_KEY` (32+ characters)
4. Configure CORS origins to your actual frontend URL
5. Use a Redis-backed rate limiter for multi-instance deployments
6. Enable HTTPS (TLS) via a reverse proxy (nginx, Caddy, or cloud load balancer)

## Feedback

All feedback is appreciated! Create an issue or reach out to the maintainer directly.

Thank you for being an OMNIX beta tester! 🚀
