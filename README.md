# OMNIX

OMNIX is a React/Vite web client with a FastAPI backend and Supabase/Postgres data layer. The repository also contains Android packaging and an admin application suite.

## Architecture

- Web: React + Vite + TypeScript
- Backend: FastAPI (`main:app`)
- Database/auth: Supabase/Postgres
- Android wrapper: Gradle/Kotlin under `android/`
- Web deployment: Vercel configuration is present in `vercel.json`
- Backend hosting: no single production provider is configured in this repository; it must be supplied separately before backend production deployment can be verified.

## Local development

1. Copy `.env.example` to `.env` and fill the required local values.
2. Install web dependencies with `npm ci`.
3. Install Python dependencies with `python -m pip install -r requirements.txt`.
4. Run the web client with `npm run dev`.
5. Run the backend with `python -m uvicorn main:app --reload --port 8000`.

The browser requires these public variables:

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY` (or `VITE_SUPABASE_PUBLISHABLE_KEY`)
- `VITE_API_BASE_URL`

Do not use `localhost` or `127.0.0.1` as `VITE_API_BASE_URL` in a deployed environment. The production browser must point at the real deployed FastAPI service.

## Validation

```bash
npm ci
npm run lint
npm run typecheck
npm test
npm run validate:backend
npm run validate:env
npm run validate:web-env
npm run build
```

`validate:env` enforces the exact server-side production variable names used by the backend. `validate:web-env` enforces the browser-side production contract and rejects localhost API URLs.

## Supabase

The browser uses only `VITE_SUPABASE_URL` plus the public anon/publishable key. Never expose `SUPABASE_SERVICE_ROLE_KEY` through a `VITE_*` variable.

The existing browser Supabase adapter performs authentication and REST operations against the configured Supabase project. It does not contain a fake offline authentication implementation. If the public Supabase variables are absent from the Vercel **Production** environment, authentication cannot work and the deployment must be treated as misconfigured.

Database changes live under `supabase/migrations/`. Review migrations for backward compatibility before applying them to production. This repository does not claim automatic database rollback.

## CI/CD

### Pull requests

`.github/workflows/ci.yml` runs lint, TypeScript typecheck, Python syntax checks, tests, backend startup/health validation, environment-contract validation, and the production frontend build. A failing check prevents a successful CI result.

`.github/workflows/android-build.yml` separately validates the Android debug build.

### Production web deployment

`.github/workflows/deploy-vercel.yml` runs only after the `CI` workflow succeeds for `main`. It:

1. checks out the exact CI-verified commit;
2. pulls the Vercel production environment;
3. validates the browser-side production environment contract;
4. builds a production artifact;
5. creates a staged production deployment without changing live traffic;
6. smoke-tests `/health`;
7. promotes the verified deployment;
8. checks production `/health`;
9. uses Vercel's native rollback if the post-promotion health check fails.

`vercel.json` disables automatic Git deployments so production traffic is controlled by the gated GitHub Actions workflow.

Required GitHub **production environment** secrets:

- `VERCEL_TOKEN`
- `VERCEL_ORG_ID`
- `VERCEL_PROJECT_ID`

The Vercel **Production** environment must also contain the actual web variables listed above. Their values are intentionally never stored in Git.

## Health checks

The web deployment exposes `/health`, backed by a static `health.json`. This verifies the deployed web artifact is being served; it does **not** prove that an externally hosted FastAPI backend or Supabase instance is healthy.

The backend exposes `/api/health` and is checked during CI startup validation.

## Deployment safety

- Production deployments are traceable to the Git commit SHA and GitHub Actions run.
- Production traffic is not changed until the staged Vercel deployment passes its smoke test.
- A failed build/test never reaches the deploy job.
- A failed post-promotion health check requests a native Vercel rollback.
- Database rollback is not represented as automatic; production migrations must be reviewed separately.

## Secrets

Do not commit `.env`, service-account JSON, keystores, database files, or API credential files. If a real credential has ever been committed, rotate/revoke it at the provider even if the file is later deleted from Git.
