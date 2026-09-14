from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
main = ROOT / "main.py"
text = main.read_text(encoding="utf-8")

# Normalize duplicate imports introduced by repeated idempotent hardening passes.
for line in [
    "from backend.routes.stories_v2 import router as stories_v2_router\n",
    "from backend.core.security import hash_otp, verify_otp_hash\n",
    "from backend.routes.reels_v2 import router as reels_v2_router\n",
]:
    text = text.replace(line, "")

# Reinsert exactly once beside the other route/security imports.
anchor = "from backend.routes.auth_v2 import router as auth_v2_router\n"
text = text.replace(anchor, anchor + "from backend.routes.stories_v2 import router as stories_v2_router\nfrom backend.routes.reels_v2 import router as reels_v2_router\nfrom backend.core.security import hash_otp, verify_otp_hash\n", 1)

# Register the router exactly once.
text = re.sub(r"\napp\.include_router\(stories_v2_router\)\n", "\n", text)
text = re.sub(r"\napp\.include_router\(reels_v2_router\)\n", "\n", text)
anchor_router = "app.include_router(auth_v2_router)\n"
text = text.replace(anchor_router, anchor_router + "app.include_router(stories_v2_router)\napp.include_router(reels_v2_router)\n", 1)
main.write_text(text, encoding="utf-8")
print("beta hardening v9 completed")
