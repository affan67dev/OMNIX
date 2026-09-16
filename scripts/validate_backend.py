from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request


def main() -> int:
    env = os.environ.copy()
    env.setdefault("ENVIRONMENT", "test")
    env.setdefault("SUPABASE_URL", "https://example.supabase.co")
    env.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
    env.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
    env.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    env.setdefault("ADMIN_API_KEY", "test-admin-key")

    compile_result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "main.py", "backend", "scripts"],
        env=env,
        check=False,
    )
    if compile_result.returncode != 0:
        return compile_result.returncode

    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8765"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                with urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=2) as response:
                    if response.status != 200:
                        return 1
                    return 0
            except Exception:
                if process.poll() is not None:
                    stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
                    print(stderr, file=sys.stderr)
                    return process.returncode or 1
                time.sleep(0.5)
        return 1
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
