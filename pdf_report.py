"""ReportLab PDF report generator — institutional-grade styling."""
from __future__ import annotations

import os
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
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

# ── Colors (reference palette) ───────────────────────────────────────────────
COLOR_NAVY = colors.HexColor("#1e293b")         # dark navy cover / accents
COLOR_NAVY_LIGHT = colors.HexColor("#2d3a4e")   # slightly lighter navy
COLOR_GOLD = colors.HexColor("#c8a961")          # gold accent lines
COLOR_CHARCOAL = colors.HexColor("#3b4456")      # table header bg
COLOR_BODY_TEXT = colors.HexColor("#1e293b")      # body text
COLOR_MUTED = colors.HexColor("#64748b")          # secondary text
COLOR_SECTION_RULE = colors.HexColor("#d4a74a")   # gold rule under H1
COLOR_HR = colors.HexColor("#e2e8f0")             # light dividers
COLOR_TABLE_ALT = colors.HexColor("#f7f8fa")      # alternating row bg
COLOR_TABLE_BORDER = colors.HexColor("#e5e7eb")   # table grid lines
COLOR_CALLOUT_BG = colors.HexColor("#f5f6f8")     # callout box background
COLOR_CALLOUT_BORDER = colors.HexColor("#4a5568")  # callout left border
COLOR_INVEST = colors.HexColor("#16a34a")
COLOR_WATCH = colors.HexColor("#d97706")
COLOR_PASS = colors.HexColor("#dc2626")
COLOR_LIGHT_GREEN = colors.HexColor("#dcfce7")
COLOR_LIGHT_AMBER = colors.HexColor("#fef3c7")
COLOR_LIGHT_RED = colors.HexColor("#fee2e2")

# ── CJK font support ────────────────────────────────────────────────────────

_CJK_FONT_REGULAR: str | None = None
_CJK_FONT_BOLD:    str | None = None


def _setup_korean_fonts() -> tuple[str, str]:
    """Register a Korean-capable TTF font pair and return (regular, bold) names."""
    global _CJK_FONT_REGULAR, _CJK_FONT_BOLD
    if _CJK_FONT_REGULAR:
        return _CJK_FONT_REGULAR, _CJK_FONT_BOLD  # type: ignore[return-value]

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

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

    try:
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
        _CJK_FONT_REGULAR, _CJK_FONT_BOLD = "HYSMyeongJo-Medium", "HYSMyeongJo-Medium"
        return _CJK_FONT_REGULAR, _CJK_FONT_BOLD
    except Exception:
        pass

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


# ── Custom flowables ─────────────────────────────────────────────────────────

class _FullPageBackground(Flowable):
    """Zero-height flowable — actual background drawn by the cover page template."""

    def __init__(self):
        super().__init__()
        self.width = 0
        self.height = 0

    def draw(self):
        pass


class _CalloutBox(Flowable):
    """A callout box with left accent border — like the reference PDF insight boxes."""

    def __init__(self, text: str, style: ParagraphStyle, width: float,
                 bg_color=COLOR_CALLOUT_BG, border_color=COLOR_CALLOUT_BORDER,
                 border_width: float = 3):
        super().__init__()
        self.para = Paragraph(text, style)
        self.box_width = width
        self.bg_color = bg_color
        self.border_color = border_color
        self.border_width = border_width
        self._inner_width = width - 24 - border_width  # padding left+right + border

    def wrap(self, availWidth, availHeight):
        w, h = self.para.wrap(self._inner_width, availHeight)
        self.para_height = h
        return self.box_width, h + 20  # 10pt top + 10pt bottom padding

    def draw(self):
        total_h = self.para_height + 20
        # Background
        self.canv.saveState()
        self.canv.setFillColor(self.bg_color)
        self.canv.setStrokeColor(self.bg_color)
        self.canv.roundRect(0, 0, self.box_width, total_h, 2, fill=True, stroke=False)
        # Left accent border
        self.canv.setFillColor(self.border_color)
        self.canv.rect(0, 0, self.border_width, total_h, fill=True, stroke=False)
        self.canv.restoreState()
        # Text
        self.para.drawOn(self.canv, self.border_width + 12, 10)


# ── Bookmark doc template ────────────────────────────────────────────────────

class _BookmarkDocTemplate(BaseDocTemplate):
    """Extends BaseDocTemplate to add PDF outline (bookmark) entries."""

    def __init__(self, filename: str, **kw):
        super().__init__(filename, **kw)
        self._bookmark_key_counter: dict[str, int] = {}
        self._font_regular = kw.pop("font_regular", "Helvetica")
        self._font_bold = kw.pop("font_bold", "Helvetica-Bold")

    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return
        style_name = flowable.style.name
        level_map = {"H1": 0, "H2": 1, "H3": 2}
        level = level_map.get(style_name)
        if level is None:
            return
        text = re.sub(r"<[^>]+>", "", flowable.getPlainText())
        key_base = re.sub(r"\W+", "_", text.lower())[:40]
        count = self._bookmark_key_counter.get(key_base, 0)
        self._bookmark_key_counter[key_base] = count + 1
        key = f"{key_base}_{count}"
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=level, closed=(level > 0))


def _cover_page_bg(canvas, doc):
    """Draw full-page navy background on the cover page."""
    canvas.saveState()
    canvas.setFillColor(COLOR_NAVY)
    canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=True, stroke=False)
    canvas.restoreState()


def _page_footer(canvas, doc):
    """Draw page number footer on body pages."""
    canvas.saveState()
    canvas.setFont(doc._font_regular, 8)
    canvas.setFillColor(COLOR_MUTED)
    page_num = canvas.getPageNumber()
    if page_num > 1:
        canvas.drawCentredString(
            doc.pagesize[0] / 2, 0.5 * inch,
            f"{page_num}"
        )
    canvas.restoreState()


# ── Style helpers ────────────────────────────────────────────────────────────

def _build_styles(font_regular: str = "Helvetica",
                  font_bold: str = "Helvetica-Bold") -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {}

    styles["H1"] = ParagraphStyle(
        "H1",
        parent=base["Normal"],
        fontSize=20,
        leading=26,
        fontName=font_bold,
        textColor=COLOR_BODY_TEXT,
        spaceBefore=24,
        spaceAfter=4,
    )
    styles["H2"] = ParagraphStyle(
        "H2",
        parent=base["Normal"],
        fontSize=14,
        leading=19,
        fontName=font_bold,
        textColor=COLOR_BODY_TEXT,
        spaceBefore=18,
        spaceAfter=4,
    )
    styles["H3"] = ParagraphStyle(
        "H3",
        parent=base["Normal"],
        fontSize=11.5,
        leading=15,
        fontName=font_bold,
        textColor=COLOR_BODY_TEXT,
        spaceBefore=12,
        spaceAfter=3,
    )
    styles["Body"] = ParagraphStyle(
        "Body",
        parent=base["Normal"],
        fontSize=9.5,
        leading=14,
        fontName=font_regular,
        textColor=COLOR_BODY_TEXT,
        alignment=TA_JUSTIFY,
        spaceBefore=2,
        spaceAfter=3,
    )
    styles["BulletRisk"] = ParagraphStyle(
        "BulletRisk",
        parent=base["Normal"],
        fontSize=9.5,
        leading=14,
        fontName=font_regular,
        textColor=COLOR_BODY_TEXT,
        backColor=COLOR_LIGHT_RED,
        leftIndent=10,
        rightIndent=8,
        spaceBefore=2,
        spaceAfter=2,
        borderPad=5,
    )
    styles["BulletStrength"] = ParagraphStyle(
        "BulletStrength",
        parent=base["Normal"],
        fontSize=9.5,
        leading=14,
        fontName=font_regular,
        textColor=COLOR_BODY_TEXT,
        backColor=COLOR_LIGHT_GREEN,
        leftIndent=10,
        rightIndent=8,
        spaceBefore=2,
        spaceAfter=2,
        borderPad=5,
    )
    styles["Bullet"] = ParagraphStyle(
        "Bullet",
        parent=base["Normal"],
        fontSize=9.5,
        leading=14,
        fontName=font_regular,
        textColor=COLOR_BODY_TEXT,
        leftIndent=10,
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
    styles["CalloutBody"] = ParagraphStyle(
        "CalloutBody",
        parent=base["Normal"],
        fontSize=9.5,
        leading=14,
        fontName=font_regular,
        textColor=COLOR_BODY_TEXT,
        alignment=TA_LEFT,
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
    # Cover page styles — white text on dark background
    styles["CoverLabel"] = ParagraphStyle(
        "CoverLabel",
        parent=base["Normal"],
        fontSize=12,
        leading=16,
        fontName=font_regular,
        textColor=colors.HexColor("#a0aec0"),  # light gray
        alignment=TA_CENTER,
        letterSpacing=3,
    )
    styles["CoverTitle"] = ParagraphStyle(
        "CoverTitle",
        parent=base["Normal"],
        fontSize=34,
        leading=42,
        fontName=font_bold,
        textColor=colors.white,
        alignment=TA_CENTER,
        spaceBefore=0,
        spaceAfter=8,
    )
    styles["CoverSub"] = ParagraphStyle(
        "CoverSub",
        parent=base["Normal"],
        fontSize=16,
        leading=22,
        fontName=font_regular,
        textColor=colors.HexColor("#cbd5e0"),  # muted white
        alignment=TA_CENTER,
    )
    styles["CoverMeta"] = ParagraphStyle(
        "CoverMeta",
        parent=base["Normal"],
        fontSize=10,
        leading=14,
        fontName=font_regular,
        textColor=colors.HexColor("#a0aec0"),
        alignment=TA_CENTER,
    )
    styles["CoverBadge"] = ParagraphStyle(
        "CoverBadge",
        parent=base["Normal"],
        fontSize=14,
        leading=20,
        fontName=font_bold,
        textColor=COLOR_BODY_TEXT,
        alignment=TA_CENTER,
    )
    return styles


# ── Inline markdown helper ───────────────────────────────────────────────────

def _md_inline(text: str) -> str:
    """Escape XML special chars then convert **bold** and *italic* to tags."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    return text


def _safe_para(text: str, style: ParagraphStyle) -> Paragraph:
    """Create a Paragraph, falling back to plain text if XML is invalid."""
    try:
        return Paragraph(text, style)
    except Exception:
        plain = re.sub(r"<[^>]+>", "", text)
        return Paragraph(plain, style)


# ── Markdown table helper ────────────────────────────────────────────────────

def _build_table(table_lines: list[str], styles: dict[str, ParagraphStyle],
                 font_regular: str, font_bold: str) -> list:
    """Convert parsed markdown table lines into a styled ReportLab Table."""
    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.split("|")]
        if cells and cells[0] == "":
            cells = cells[1:]
        if cells and cells[-1] == "":
            cells = cells[:-1]
        rows.append(cells)

    if not rows:
        return []

    # Header style: white text on dark background
    header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Body"],
        fontName=font_bold,
        fontSize=8.5,
        leading=12,
        textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Body"],
        fontSize=8.5,
        leading=12,
        alignment=TA_LEFT,
        textColor=COLOR_BODY_TEXT,
    )

    table_data = []
    for row_idx, row in enumerate(rows):
        style = header_style if row_idx == 0 else cell_style
        table_data.append([_safe_para(_md_inline(c), style) for c in row])

    max_cols = max(len(r) for r in table_data)
    for row in table_data:
        while len(row) < max_cols:
            row.append(_safe_para("", cell_style))

    avail_width = 6.5 * inch
    col_widths = [avail_width / max_cols] * max_cols

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        # Dark header row
        ("BACKGROUND",    (0, 0), (-1, 0), COLOR_CHARCOAL),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        # Alternating rows
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_TABLE_ALT]),
        # Padding
        ("TOPPADDING",    (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING",    (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        # Grid lines — subtle
        ("LINEBELOW",     (0, 0), (-1, 0), 1.0, COLOR_CHARCOAL),
        ("LINEBELOW",     (0, 1), (-1, -2), 0.5, COLOR_TABLE_BORDER),
        ("LINEBELOW",     (0, -1), (-1, -1), 0.5, COLOR_TABLE_BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))

    return [Spacer(1, 6), table, Spacer(1, 8)]


# ── Markdown parser ──────────────────────────────────────────────────────────

def _parse_markdown(md: str, styles: dict[str, ParagraphStyle],
                    font_regular: str, font_bold: str,
                    page_width: float) -> list:
    """Convert markdown string to a list of ReportLab flowables."""
    flowables = []
    lines = md.splitlines()
    in_code_block = False
    i = 0
    avail_width = page_width - 1.8 * inch  # minus margins

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

        # H1 — with gold horizontal rule
        if line.startswith("# "):
            text = _md_inline(line[2:].strip())
            flowables.append(_safe_para(text, styles["H1"]))
            flowables.append(HRFlowable(
                width="100%", thickness=2,
                color=COLOR_SECTION_RULE, spaceAfter=8,
            ))
            i += 1
            continue

        # H2 — with thin gray rule
        if line.startswith("## "):
            text = _md_inline(line[3:].strip())
            flowables.append(_safe_para(text, styles["H2"]))
            flowables.append(HRFlowable(
                width="100%", thickness=0.5,
                color=COLOR_HR, spaceAfter=4,
            ))
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

        # Callout block: lines starting with > (blockquote)
        if line.strip().startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            quote_text = _md_inline(" ".join(quote_lines))
            flowables.append(Spacer(1, 4))
            flowables.append(_CalloutBox(
                quote_text, styles["CalloutBody"], avail_width,
            ))
            flowables.append(Spacer(1, 6))
            continue

        # Markdown table
        if "|" in line and line.strip().startswith("|"):
            table_lines = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip().startswith("|"):
                stripped = lines[i].strip()
                if not re.match(r"^\|[\s\-:|]+\|$", stripped):
                    table_lines.append(stripped)
                i += 1
            if table_lines:
                flowables.extend(_build_table(table_lines, styles,
                                              font_regular, font_bold))
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
            flowables.append(Spacer(1, 6))
            i += 1
            continue

        # Plain text
        text = _md_inline(line.strip())
        if text:
            flowables.append(_safe_para(text, styles["Body"]))
        i += 1

    return flowables


# ── Cover page builder ───────────────────────────────────────────────────────

def _build_cover(company: str, recommendation: str, styles: dict,
                 page_width: float, page_height: float,
                 language: str = "English") -> list:
    """Build a dark navy cover page matching the reference design."""
    rec = (recommendation or "WATCH").upper()

    rec_labels_en = {
        "INVEST": "INVEST",
        "WATCH": "CONDITIONAL PROCEED",
        "PASS": "PASS",
    }
    rec_labels_ko = {
        "INVEST": "INVEST",
        "WATCH": "CONDITIONAL PROCEED",
        "PASS": "PASS",
    }
    rec_labels = rec_labels_ko if language.lower() == "korean" else rec_labels_en
    rec_label = rec_labels.get(rec, rec)

    title_label = "DUE DILIGENCE REPORT"
    subtitle = "투자 검토 보고서" if language.lower() == "korean" else "Investment Due Diligence"

    from reportlab.platypus import NextPageTemplate

    flowables: list = []

    flowables.append(Spacer(1, 2.2 * inch))

    # "DUE DILIGENCE REPORT" label
    flowables.append(_safe_para(
        f'<font letterSpacing="4">{title_label}</font>',
        styles["CoverLabel"],
    ))
    flowables.append(Spacer(1, 0.3 * inch))

    # Large company name / subtitle
    flowables.append(_safe_para(subtitle, styles["CoverTitle"]))
    flowables.append(Spacer(1, 0.1 * inch))
    flowables.append(_safe_para(company, styles["CoverSub"]))

    # Gold divider line
    flowables.append(Spacer(1, 0.5 * inch))
    flowables.append(HRFlowable(
        width="15%", thickness=2,
        color=COLOR_GOLD, hAlign="CENTER",
    ))
    flowables.append(Spacer(1, 0.5 * inch))

    # Recommendation badge (white bg box)
    badge_style = ParagraphStyle(
        "CoverBadgeDyn",
        parent=styles["CoverBadge"],
        backColor=colors.HexColor("#f7f8fa"),
        borderPad=14,
        textColor=COLOR_BODY_TEXT,
    )
    flowables.append(_safe_para(rec_label, badge_style))

    flowables.append(Spacer(1, 0.8 * inch))

    # Metadata row: DATE | CLASSIFICATION | TYPE
    now = datetime.now()
    date_str = now.strftime("%Y. %m. %d")
    meta_text = (
        f'<font size="8" color="#8a9ab5">DATE</font><br/>{date_str}'
        f'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
        f'<font size="8" color="#8a9ab5">CLASSIFICATION</font><br/>Confidential'
        f'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
        f'<font size="8" color="#8a9ab5">TYPE</font><br/>Desk Research DD'
    )
    flowables.append(_safe_para(meta_text, styles["CoverMeta"]))

    flowables.append(Spacer(1, 1.0 * inch))

    # Bottom attribution
    disclaimer_style = ParagraphStyle(
        "CoverDisclaimer",
        parent=styles["Footer"],
        textColor=colors.HexColor("#8a9ab5"),
        fontSize=7.5,
    )
    flowables.append(_safe_para(
        "WORKFLOW ARCHITECTED BY DD AGENT",
        disclaimer_style,
    ))
    flowables.append(Spacer(1, 0.1 * inch))
    if language.lower() == "korean":
        flowables.append(_safe_para(
            "본 문서는 데스크 리서치 기반이며, [ESTIMATE] 태그가 붙은 수치는 검증 전 추정치입니다.",
            disclaimer_style,
        ))
    else:
        flowables.append(_safe_para(
            "This document is based on desk research. Figures tagged [ESTIMATE] are unverified.",
            disclaimer_style,
        ))

    # Switch to body page template after cover, then page break
    flowables.append(NextPageTemplate("main"))
    flowables.append(PageBreak())
    return flowables


# ── Main entry point ─────────────────────────────────────────────────────────

def generate_pdf(state: dict[str, Any], job_id: str, output_dir: str | None = None) -> str:
    """Generate a PDF report from the completed due diligence state."""
    reports_dir = Path(output_dir) if output_dir else Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(reports_dir / f"{job_id}.pdf")

    company = state.get("company_name") or "Unknown Company"
    recommendation = state.get("recommendation") or "WATCH"
    final_report_md = state.get("final_report") or ""
    language = state.get("language", "English")

    if language.lower() == "korean":
        font_regular, font_bold = _setup_korean_fonts()
    else:
        font_regular, font_bold = "Helvetica", "Helvetica-Bold"

    styles = _build_styles(font_regular, font_bold)

    page_size = A4
    doc = _BookmarkDocTemplate(
        output_path,
        pagesize=page_size,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        title=f"Due Diligence — {company}",
        author="Due Diligence Agent",
        subject=f"Investment recommendation: {recommendation}",
        font_regular=font_regular,
        font_bold=font_bold,
    )

    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id="normal",
    )
    cover_frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id="cover",
    )
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=cover_frame, onPage=_cover_page_bg),
        PageTemplate(id="main", frames=frame, onPage=_page_footer),
    ])

    story = []

    # Cover page
    story.extend(_build_cover(
        company, recommendation, styles,
        page_size[0], page_size[1], language,
    ))

    # Body: parse markdown report
    if final_report_md.strip():
        story.extend(_parse_markdown(
            final_report_md, styles,
            font_regular, font_bold, page_size[0],
        ))
    else:
        story.append(_safe_para("No report content was generated.", styles["Body"]))

    doc.build(story)
    return os.path.abspath(output_path)
