from __future__ import annotations

import os
import sys
from urllib.parse import urlparse


REQUIRED_SERVER = (
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "ADMIN_API_KEY",
    "OMNIX_JWT_SECRET",
)
REQUIRED_WEB = (
    "VITE_SUPABASE_URL",
    "VITE_SUPABASE_ANON_KEY",
    "VITE_API_BASE_URL",
)
PLACEHOLDERS = {
    "",
    "change-me-in-prod",
    "replace_with_a_second_long_random_secret",
    "your-project.supabase.co",
    "your-anon-key",
    "your-service-role-key",
    "your-admin-api-key",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}


def is_placeholder(value: str | None) -> bool:
    return value is None or value.strip().lower() in PLACEHOLDERS


def validate_url(name: str, value: str | None, invalid: list[str]) -> None:
    if is_placeholder(value):
        invalid.append(name)
        return
    parsed = urlparse(value or "")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        invalid.append(name)


def main() -> int:
    environment = os.getenv("ENVIRONMENT", "development").lower()
    if environment not in {"production", "prod"}:
        print(f"Environment validation: {environment} (production secrets not required).")
        return 0

    missing: list[str] = []
    invalid: list[str] = []
    for name in REQUIRED_SERVER + REQUIRED_WEB:
        value = os.getenv(name)
        if value is None:
            missing.append(name)
        elif is_placeholder(value):
            invalid.append(name)

    for name in ("SUPABASE_URL", "VITE_SUPABASE_URL", "VITE_API_BASE_URL"):
        validate_url(name, os.getenv(name), invalid)

    api_base = os.getenv("VITE_API_BASE_URL", "").strip().lower()
    if api_base.startswith(("http://localhost", "http://127.0.0.1", "https://localhost", "https://127.0.0.1")):
        invalid.append("VITE_API_BASE_URL")

    if os.getenv("VITE_SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_SERVICE_KEY"):
        invalid.append("privileged VITE_* Supabase credential")

    if missing or invalid:
        if missing:
            print("Missing required production environment variables:", ", ".join(sorted(set(missing))), file=sys.stderr)
        if invalid:
            print("Invalid/placeholder production configuration:", ", ".join(sorted(set(invalid))), file=sys.stderr)
        return 1

    print("Production environment configuration passed structural validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
