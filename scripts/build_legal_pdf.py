from pathlib import Path
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "legal" / "OMNIX-Legal-Policies.pdf"


def markdown_to_flowables(text: str, styles):
    story = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            story.append(Spacer(1, 3 * mm))
        elif line.startswith("# "):
            story.append(Paragraph(line[2:], styles["Title"]))
        elif line.startswith("## "):
            story.append(Paragraph(line[3:], styles["Heading2"]))
        elif line.startswith("**") and line.endswith("**"):
            story.append(Paragraph(line.replace("**", ""), styles["Heading3"]))
        else:
            safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            safe = safe.replace("**", "<b>", 1) if "**" in safe else safe
            # Keep simple markdown readable without requiring a full parser.
            safe = safe.replace("**", "</b>")
            story.append(Paragraph(safe, styles["BodyText"]))
    return story


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="LegalTitle", parent=styles["Title"], alignment=TA_CENTER, spaceAfter=10 * mm))
    terms = (ROOT / "legal" / "TERMS_OF_SERVICE.md").read_text(encoding="utf-8")
    privacy = (ROOT / "legal" / "PRIVACY_POLICY.md").read_text(encoding="utf-8")
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm, title="OMNIX Legal Policies")
    story = [Paragraph("OMNIX — Legal Policies", styles["LegalTitle"]), Paragraph("Terms of Service and Privacy Policy", styles["Heading2"]), Spacer(1, 6 * mm)]
    story += markdown_to_flowables(terms, styles)
    story.append(PageBreak())
    story += markdown_to_flowables(privacy, styles)
    doc.build(story)
    print(OUT)


if __name__ == "__main__":
    main()
