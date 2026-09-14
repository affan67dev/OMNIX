from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# v7 inserted media_type from the upload result but left the original property behind.
# Remove only that exact duplicate so the object has one authoritative media type.
stories = ROOT / "src/components/ui/Stories.tsx"
text = stories.read_text(encoding="utf-8")
duplicate = "          media_type: upload.media_type,\n          media_type: selectedMediaType,\n"
if duplicate in text:
    text = text.replace(duplicate, "          media_type: upload.media_type,\n", 1)
stories.write_text(text, encoding="utf-8")
print("beta hardening v8 completed")
