from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
main = ROOT / "main.py"
text = main.read_text(encoding="utf-8")
if "from pydantic import BaseModel, EmailStr, Field, field_validator" not in text:
    old = "from pydantic import BaseModel, EmailStr, field_validator"
    if old not in text:
        raise SystemExit("Expected pydantic import was not found")
    text = text.replace(old, "from pydantic import BaseModel, EmailStr, Field, field_validator", 1)
    main.write_text(text, encoding="utf-8")
print("beta hardening v3 completed")
