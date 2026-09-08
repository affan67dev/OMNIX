# OMNIX — Private Social Network

A full-stack private social networking app with end-to-end encrypted chat, reels, stories, and secure authentication.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19 + TypeScript + Vite + Tailwind CSS |
| Backend | Python 3.12 + FastAPI |
| Mobile | Kotlin (Android) |
| Database | Supabase (PostgreSQL) |
| Real-time | Pusher Channels |
| Voice/Video | Agora SDK |

## Quick Start

### Prerequisites
- Node.js 20+
- Python 3.11+
- A Supabase project

### 1. Clone and install dependencies

```bash
git clone https://github.com/affan67dev/OMNIX.git
cd OMNIX
npm install
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your actual credentials
```

See `.env.example` for all required variables. **Never commit real credentials.**

### 3. Run database migrations

Apply the SQL files in `supabase/migrations/` to your Supabase project (in timestamp order).

### 4. Start the backend

```bash
uvicorn main:app --reload --port 8000
```

### 5. Start the frontend

```bash
npm run dev
```

The app will be available at `http://localhost:80`.

## Available Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start Vite dev server |
| `npm run build` | Build for production |
| `npm run preview` | Preview production build |
| `npm run lint` | Lint TypeScript source |
| `npm run typecheck` | Run TypeScript diagnostics |

## Android Build

See [ANDROID_NATIVE_SETUP.md](ANDROID_NATIVE_SETUP.md) for full Android build instructions.

```bash
cd android
cp local.properties.example local.properties
# Edit local.properties to set sdk.dir
./gradlew assembleDebug
```

## Environment Variables

All secrets must be provided via environment variables. See `.env.example` for the full list. Key variables:

| Variable | Description |
|----------|-------------|
| `VITE_SUPABASE_URL` | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon/public key |
| `VITE_API_BASE_URL` | Backend API base URL |
| `VITE_PUSHER_APP_KEY` | Pusher channel key |
| `SUPABASE_SERVICE_KEY` | Supabase service role key (backend only) |
| `PUSHER_SECRET` | Pusher secret (backend only) |

## Running Tests

```bash
# Python tests
python3 -m pytest tests/ -v

# TypeScript type check
npm run typecheck
```

## Security Notes

- All secrets are managed via environment variables — no secrets in source code.
- `api-credentials.json` is a **template only** — fill in `.env` instead.
- Rate limiting is applied on all auth and sensitive endpoints.
- Input validation and sanitization on all user-facing APIs.

## Architecture Overview

```
OMNIX/
├── src/              # React/TypeScript frontend
│   ├── pages/        # Page-level components (Auth, Chat, Home)
│   ├── components/   # UI components
│   ├── utils/        # Utilities (auth, crypto, retry, sanitize)
│   └── supabase/     # Supabase client
├── backend/          # FastAPI route/service modules
├── supabase/         # Database migrations
├── android/          # Kotlin Android app
└── tests/            # Python test suite
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Run `npm run typecheck && npm run lint` and `pytest tests/` before committing
4. Open a pull request against `main`

## Known Issues / Beta Notes

- Supabase auth integration is active; ensure your Supabase project has the correct RLS policies applied.
- Voice/video calling (Agora) requires a valid App ID and certificate.
- Push notifications require a configured Firebase project.

## License

Private — all rights reserved.
