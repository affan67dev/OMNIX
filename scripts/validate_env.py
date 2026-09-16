from __future__ import annotations

import os
import sys


REQUIRED_PRODUCTION = (
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "ADMIN_API_KEY",
    "OMNIX_JWT_SECRET",
)
PLACEHOLDERS = {
    "",
    "change-me-in-prod",
    "replace_with_a_second_long_random_secret",
    "your-project.supabase.co",
    "your-anon-key",
    "your-service-role-key",
    "your-admin-api-key",
}


def main() -> int:
    environment = os.getenv("ENVIRONMENT", "development").lower()
    if environment not in {"production", "prod"}:
        print(f"Environment validation: {environment} (production secrets not required).")
        return 0

    missing: list[str] = []
    invalid: list[str] = []
    for name in REQUIRED_PRODUCTION:
        value = os.getenv(name)
        if value is None:
            missing.append(name)
        elif value.strip().lower() in PLACEHOLDERS:
            invalid.append(name)

    if missing or invalid:
        if missing:
            print("Missing required production environment variables:", ", ".join(missing), file=sys.stderr)
        if invalid:
            print("Placeholder/unsafe production values found for:", ", ".join(invalid), file=sys.stderr)
        return 1

    if not os.getenv("VITE_SUPABASE_URL") or not os.getenv("VITE_SUPABASE_ANON_KEY"):
        print("Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY for the web client.", file=sys.stderr)
        return 1

    if os.getenv("VITE_SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_SERVICE_KEY"):
        print("Privileged Supabase credentials must never be exposed as VITE_* variables.", file=sys.stderr)
        return 1

    print("Production environment configuration passed structural validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
