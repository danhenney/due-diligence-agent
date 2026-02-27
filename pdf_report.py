"""ReportLab PDF report generator with bookmarks and colored highlights."""
from __future__ import annotations

import os
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable

# ── Colors ────────────────────────────────────────────────────────────────────
COLOR_INVEST = colors.HexColor("#16a34a")   # green-600
COLOR_WATCH = colors.HexColor("#d97706")    # amber-600
COLOR_PASS = colors.HexColor("#dc2626")     # red-600
COLOR_LIGHT_GREEN = colors.HexColor("#dcfce7")
COLOR_LIGHT_AMBER = colors.HexColor("#fef3c7")
COLOR_LIGHT_RED = colors.HexColor("#fee2e2")
COLOR_BODY_TEXT = colors.HexColor("#1e293b")
COLOR_MUTED = colors.HexColor("#64748b")
COLOR_HR = colors.HexColor("#e2e8f0")
COLOR_CODE_BG = colors.HexColor("#f1f5f9")

# ── CJK font support ──────────────────────────────────────────────────────────

_CJK_FONT_REGULAR: str | None = None
_CJK_FONT_BOLD:    str | None = None


def _setup_korean_fonts() -> tuple[str, str]:
    """Register a Korean-capable TTF font pair and return (regular, bold) names.

    Strategy (first that succeeds):
    1. System font installed by packages.txt (fonts-nanum on Streamlit Cloud)
    2. Cached download of NanumGothic from Google Fonts GitHub
    3. ReportLab built-in CID Korean font
    4. Helvetica fallback (shows boxes but won't crash)
    """
    global _CJK_FONT_REGULAR, _CJK_FONT_BOLD
    if _CJK_FONT_REGULAR:
        return _CJK_FONT_REGULAR, _CJK_FONT_BOLD  # type: ignore[return-value]

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # 1 — System font paths (Ubuntu/Debian with fonts-nanum)
    candidates = [
        ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
         "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
        ("/usr/share/fonts/truetype/nanum/NanumGothicRegular.ttf",
         "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
    ]
    for reg_path, bold_path in candidates:
        if os.path.exists(reg_path):
            try:
                pdfmetrics.registerFont(TTFont("KoreanRegular", reg_path))
                bold = bold_path if os.path.exists(bold_path) else reg_path
                pdfmetrics.registerFont(TTFont("KoreanBold", bold))
                _CJK_FONT_REGULAR, _CJK_FONT_BOLD = "KoreanRegular", "KoreanBold"
                return _CJK_FONT_REGULAR, _CJK_FONT_BOLD
            except Exception:
                continue

    # 2 — Download NanumGothic and cache locally
    font_dir = Path("fonts")
    font_dir.mkdir(exist_ok=True)
    reg_cache  = font_dir / "NanumGothic-Regular.ttf"
    bold_cache = font_dir / "NanumGothic-Bold.ttf"
    _NANUM_URLS = {
        reg_cache:  "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf",
        bold_cache: "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf",
    }
    try:
        for dest, url in _NANUM_URLS.items():
            if not dest.exists():
                urllib.request.urlretrieve(url, str(dest))
        if reg_cache.exists():
            pdfmetrics.registerFont(TTFont("NanumGothic",     str(reg_cache)))
            pdfmetrics.registerFont(TTFont("NanumGothicBold", str(bold_cache) if bold_cache.exists() else str(reg_cache)))
            _CJK_FONT_REGULAR, _CJK_FONT_BOLD = "NanumGothic", "NanumGothicBold"
            return _CJK_FONT_REGULAR, _CJK_FONT_BOLD
    except Exception:
        pass

    # 3 — ReportLab built-in CID Korean font
    try:
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
        _CJK_FONT_REGULAR, _CJK_FONT_BOLD = "HYSMyeongJo-Medium", "HYSMyeongJo-Medium"
        return _CJK_FONT_REGULAR, _CJK_FONT_BOLD
    except Exception:
        pass

    # 4 — Graceful fallback (Latin only — boxes for Korean, but won't crash)
    _CJK_FONT_REGULAR, _CJK_FONT_BOLD = "Helvetica", "Helvetica-Bold"
    return _CJK_FONT_REGULAR, _CJK_FONT_BOLD


RISK_KEYWORDS = {
    "risk", "threat", "concern", "weakness", "challenge", "litigation",
    "lawsuit", "regulatory", "penalty", "decline", "loss", "debt",
    "competitive pressure", "churn", "fraud", "investigation",
}
STRENGTH_KEYWORDS = {
    "strength", "opportunity", "growth", "moat", "advantage", "leader",
    "dominant", "profitable", "innovation", "patent", "expansion",
    "revenue growth", "margin", "cash flow",
}


def _rec_color(recommendation: str) -> colors.Color:
    rec = (recommendation or "").upper()
    if "INVEST" in rec:
        return COLOR_INVEST
    if "WATCH" in rec:
        return COLOR_WATCH
    return COLOR_PASS


def _rec_bg(recommendation: str) -> colors.Color:
    rec = (recommendation or "").upper()
    if "INVEST" in rec:
        return COLOR_LIGHT_GREEN
    if "WATCH" in rec:
        return COLOR_LIGHT_AMBER
    return COLOR_LIGHT_RED


# ── Bookmark doc template ─────────────────────────────────────────────────────

class _BookmarkDocTemplate(BaseDocTemplate):
    """Extends BaseDocTemplate to add PDF outline (bookmark) entries."""

    def __init__(self, filename: str, **kw):
        super().__init__(filename, **kw)
        self._bookmark_key_counter: dict[str, int] = {}

    def afterFlowable(self, flowable):
        """Called after each flowable is rendered — adds outline entries."""
        if not isinstance(flowable, Paragraph):
            return
        style_name = flowable.style.name
        level_map = {
            "H1": 0,
            "H2": 1,
            "H3": 2,
        }
        level = level_map.get(style_name)
        if level is None:
            return

        # Strip HTML tags to get plain text for the bookmark label
        text = re.sub(r"<[^>]+>", "", flowable.getPlainText())
        key_base = re.sub(r"\W+", "_", text.lower())[:40]
        count = self._bookmark_key_counter.get(key_base, 0)
        self._bookmark_key_counter[key_base] = count + 1
        key = f"{key_base}_{count}"

        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=level, closed=(level > 0))


# ── Style helpers ─────────────────────────────────────────────────────────────

def _build_styles(font_regular: str = "Helvetica",
                  font_bold: str = "Helvetica-Bold") -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {}

    styles["H1"] = ParagraphStyle(
        "H1",
        parent=base["Normal"],
        fontSize=22,
        leading=28,
        fontName=font_bold,
        textColor=COLOR_BODY_TEXT,
        spaceBefore=18,
        spaceAfter=4,
    )
    styles["H2"] = ParagraphStyle(
        "H2",
        parent=base["Normal"],
        fontSize=15,
        leading=20,
        fontName=font_bold,
        textColor=COLOR_BODY_TEXT,
        spaceBefore=14,
        spaceAfter=2,
    )
    styles["H3"] = ParagraphStyle(
        "H3",
        parent=base["Normal"],
        fontSize=12,
        leading=16,
        fontName=font_bold,
        textColor=COLOR_BODY_TEXT,
        spaceBefore=10,
        spaceAfter=2,
    )
    styles["Body"] = ParagraphStyle(
        "Body",
        parent=base["Normal"],
        fontSize=10,
        leading=14,
        fontName=font_regular,
        textColor=COLOR_BODY_TEXT,
        alignment=TA_JUSTIFY,
        spaceBefore=2,
        spaceAfter=2,
    )
    styles["BulletRisk"] = ParagraphStyle(
        "BulletRisk",
        parent=base["Normal"],
        fontSize=10,
        leading=14,
        fontName=font_regular,
        textColor=COLOR_BODY_TEXT,
        backColor=COLOR_LIGHT_RED,
        leftIndent=8,
        rightIndent=8,
        spaceBefore=2,
        spaceAfter=2,
        borderPad=4,
    )
    styles["BulletStrength"] = ParagraphStyle(
        "BulletStrength",
        parent=base["Normal"],
        fontSize=10,
        leading=14,
        fontName=font_regular,
        textColor=COLOR_BODY_TEXT,
        backColor=COLOR_LIGHT_GREEN,
        leftIndent=8,
        rightIndent=8,
        spaceBefore=2,
        spaceAfter=2,
        borderPad=4,
    )
    styles["Bullet"] = ParagraphStyle(
        "Bullet",
        parent=base["Normal"],
        fontSize=10,
        leading=14,
        fontName=font_regular,
        textColor=COLOR_BODY_TEXT,
        leftIndent=8,
        spaceBefore=1,
        spaceAfter=1,
    )
    styles["Callout"] = ParagraphStyle(
        "Callout",
        parent=base["Normal"],
        fontSize=13,
        leading=18,
        fontName=font_bold,
        textColor=colors.white,
        alignment=TA_CENTER,
        spaceBefore=10,
        spaceAfter=10,
    )
    styles["Footer"] = ParagraphStyle(
        "Footer",
        parent=base["Normal"],
        fontSize=8,
        leading=10,
        fontName=font_regular,
        textColor=COLOR_MUTED,
        alignment=TA_CENTER,
    )
    styles["CoverTitle"] = ParagraphStyle(
        "CoverTitle",
        parent=base["Normal"],
        fontSize=32,
        leading=40,
        fontName=font_bold,
        textColor=COLOR_BODY_TEXT,
        alignment=TA_CENTER,
        spaceBefore=0,
        spaceAfter=8,
    )
    styles["CoverSub"] = ParagraphStyle(
        "CoverSub",
        parent=base["Normal"],
        fontSize=14,
        leading=20,
        fontName=font_regular,
        textColor=COLOR_MUTED,
        alignment=TA_CENTER,
    )
    return styles


# ── Inline markdown helper ────────────────────────────────────────────────────

def _md_inline(text: str) -> str:
    """Escape XML special chars then convert **bold** and *italic* to tags."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # Italic (not already inside bold)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    return text


def _safe_para(text: str, style: ParagraphStyle) -> Paragraph:
    """Create a Paragraph, falling back to plain text if XML is invalid."""
    try:
        return Paragraph(text, style)
    except Exception:
        plain = re.sub(r"<[^>]+>", "", text)
        return Paragraph(plain, style)


# ── Markdown parser ───────────────────────────────────────────────────────────

def _parse_markdown(md: str, styles: dict[str, ParagraphStyle]) -> list:
    """Convert markdown string to a list of ReportLab flowables."""
    flowables = []
    lines = md.splitlines()
    in_code_block = False
    i = 0

    while i < len(lines):
        line = lines[i]

        # Code fence — skip
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            i += 1
            continue
        if in_code_block:
            i += 1
            continue

        # H1
        if line.startswith("# "):
            text = _md_inline(line[2:].strip())
            flowables.append(_safe_para(text, styles["H1"]))
            flowables.append(HRFlowable(width="100%", thickness=1, color=COLOR_HR, spaceAfter=4))
            i += 1
            continue

        # H2
        if line.startswith("## "):
            text = _md_inline(line[3:].strip())
            flowables.append(_safe_para(text, styles["H2"]))
            i += 1
            continue

        # H3
        if line.startswith("### "):
            text = _md_inline(line[4:].strip())
            flowables.append(_safe_para(text, styles["H3"]))
            i += 1
            continue

        # Recommendation callout line
        if re.search(r"\*\*Recommendation[:\s]\*\*", line, re.IGNORECASE) or \
           re.search(r"recommendation.*:\s*(INVEST|WATCH|PASS)", line, re.IGNORECASE):
            rec_match = re.search(r"\b(INVEST|WATCH|PASS)\b", line, re.IGNORECASE)
            rec = rec_match.group(1).upper() if rec_match else "WATCH"
            bg = _rec_bg(rec)
            fg = _rec_color(rec)
            style = ParagraphStyle(
                "CalloutDyn",
                parent=styles["Callout"],
                backColor=bg,
                textColor=fg,
            )
            flowables.append(Spacer(1, 6))
            flowables.append(_safe_para(f"Recommendation: {rec}", style))
            flowables.append(Spacer(1, 6))
            i += 1
            continue

        # Bullet
        if line.startswith("- ") or line.startswith("* "):
            content = line[2:].strip()
            lower = content.lower()
            inline = _md_inline(content)
            if any(k in lower for k in RISK_KEYWORDS):
                flowables.append(_safe_para(f"• {inline}", styles["BulletRisk"]))
            elif any(k in lower for k in STRENGTH_KEYWORDS):
                flowables.append(_safe_para(f"• {inline}", styles["BulletStrength"]))
            else:
                flowables.append(_safe_para(f"• {inline}", styles["Bullet"]))
            i += 1
            continue

        # Blank line → small spacer
        if not line.strip():
            flowables.append(Spacer(1, 4))
            i += 1
            continue

        # Plain text
        text = _md_inline(line.strip())
        if text:
            flowables.append(_safe_para(text, styles["Body"]))
        i += 1

    return flowables


# ── Cover page builder ────────────────────────────────────────────────────────

def _build_cover(company: str, recommendation: str, styles: dict) -> list:
    """Build the cover page flowables."""
    rec = (recommendation or "WATCH").upper()
    badge_color = _rec_color(rec)
    badge_bg = _rec_bg(rec)

    rec_labels = {
        "INVEST": "Strong Investment Opportunity",
        "WATCH": "Monitor — Further Diligence Recommended",
        "PASS": "Do Not Invest at This Time",
    }
    rec_label = rec_labels.get(rec, rec)

    flowables = [
        Spacer(1, 1.5 * inch),
        _safe_para("Due Diligence Report", styles["CoverSub"]),
        Spacer(1, 0.25 * inch),
        _safe_para(company, styles["CoverTitle"]),
        Spacer(1, 0.4 * inch),
        HRFlowable(width="60%", thickness=2, color=COLOR_HR, hAlign="CENTER"),
        Spacer(1, 0.4 * inch),
    ]

    # Large recommendation badge
    badge_style = ParagraphStyle(
        "Badge",
        parent=styles["Callout"],
        fontSize=28,
        leading=36,
        backColor=badge_bg,
        textColor=badge_color,
        borderRadius=8,
        borderPad=12,
    )
    flowables.append(_safe_para(rec, badge_style))
    flowables.append(Spacer(1, 0.15 * inch))
    flowables.append(_safe_para(rec_label, styles["CoverSub"]))
    flowables.append(Spacer(1, 0.6 * inch))
    flowables.append(HRFlowable(width="40%", thickness=1, color=COLOR_HR, hAlign="CENTER"))
    flowables.append(Spacer(1, 0.3 * inch))
    flowables.append(_safe_para(
        f"Generated: {datetime.now().strftime('%B %d, %Y')}",
        styles["CoverSub"],
    ))
    flowables.append(Spacer(1, 0.2 * inch))
    flowables.append(_safe_para("Confidential — For Internal Use Only", styles["Footer"]))
    flowables.append(PageBreak())
    return flowables


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_pdf(state: dict[str, Any], job_id: str) -> str:
    """Generate a PDF report from the completed due diligence state.

    Args:
        state: The merged LangGraph state dict (includes final_report, recommendation, etc.)
        job_id: Unique job identifier used to name the output file.

    Returns:
        Absolute path to the generated PDF file.
    """
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    output_path = str(reports_dir / f"{job_id}.pdf")

    company = state.get("company_name") or "Unknown Company"
    recommendation = state.get("recommendation") or "WATCH"
    final_report_md = state.get("final_report") or ""
    language = state.get("language", "English")

    # Set up fonts — use Korean-capable font when needed
    if language.lower() == "korean":
        font_regular, font_bold = _setup_korean_fonts()
    else:
        font_regular, font_bold = "Helvetica", "Helvetica-Bold"

    styles = _build_styles(font_regular, font_bold)

    doc = _BookmarkDocTemplate(
        output_path,
        pagesize=LETTER,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        title=f"Due Diligence — {company}",
        author="Due Diligence Agent",
        subject=f"Investment recommendation: {recommendation}",
    )

    # Single page template
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id="normal",
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=frame)])

    story = []

    # Cover page
    story.extend(_build_cover(company, recommendation, styles))

    # Body: parse markdown report
    if final_report_md.strip():
        story.extend(_parse_markdown(final_report_md, styles))
    else:
        story.append(_safe_para("No report content was generated.", styles["Body"]))

    doc.build(story)
    return os.path.abspath(output_path)
