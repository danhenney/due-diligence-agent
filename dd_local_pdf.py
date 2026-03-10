"""Convert dd-local report.md to styled PDF matching the institutional design."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable

# ── Colors — matches the example PDF ────────────────────────────────────────
COLOR_NAVY = colors.HexColor("#1a2332")           # cover bg, headings, table header
COLOR_GOLD = colors.HexColor("#c9a84c")            # cover title, dividers, badge
COLOR_BODY = colors.HexColor("#2c2c2c")            # body text
COLOR_SECONDARY = colors.HexColor("#333333")        # secondary text
COLOR_TBL_SUB = colors.HexColor("#4a4a6b")         # table sub-header
COLOR_ROW_ALT = colors.HexColor("#f8f8fc")          # alternating rows
COLOR_DIV_LIGHT = colors.HexColor("#ededed")        # light dividers
COLOR_DIV_MED = colors.HexColor("#dedede")          # medium dividers
COLOR_MUTED = colors.HexColor("#8a9ab5")            # muted text on cover
COLOR_CALLOUT_BG = colors.HexColor("#f5f6f8")       # callout box background
COLOR_CALLOUT_BORDER = colors.HexColor("#4a5568")   # callout left border
COLOR_INVEST = colors.HexColor("#16a34a")
COLOR_WATCH = colors.HexColor("#d97706")
COLOR_PASS = colors.HexColor("#dc2626")

# ── Font setup ──────────────────────────────────────────────────────────────

_FONT_REGULAR: str | None = None
_FONT_BOLD: str | None = None


def _setup_fonts() -> tuple[str, str]:
    """Register NanumMyeongjo (serif) for Korean, with NanumGothic fallback."""
    global _FONT_REGULAR, _FONT_BOLD
    if _FONT_REGULAR:
        return _FONT_REGULAR, _FONT_BOLD  # type: ignore[return-value]

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_dir = Path("fonts")
    font_dir.mkdir(exist_ok=True)

    # Try NanumMyeongjo first (serif — matches example PDF)
    myeongjo_reg = font_dir / "NanumMyeongjo-Regular.ttf"
    myeongjo_bold = font_dir / "NanumMyeongjo-Bold.ttf"
    _MYEONGJO_URLS = {
        myeongjo_reg: "https://github.com/google/fonts/raw/main/ofl/nanummyeongjo/NanumMyeongjo-Regular.ttf",
        myeongjo_bold: "https://github.com/google/fonts/raw/main/ofl/nanummyeongjo/NanumMyeongjo-Bold.ttf",
    }
    try:
        for dest, url in _MYEONGJO_URLS.items():
            if not dest.exists():
                urllib.request.urlretrieve(url, str(dest))
        if myeongjo_reg.exists():
            pdfmetrics.registerFont(TTFont("NanumMyeongjo", str(myeongjo_reg)))
            pdfmetrics.registerFont(TTFont("NanumMyeongjoBold",
                                           str(myeongjo_bold) if myeongjo_bold.exists() else str(myeongjo_reg)))
            _FONT_REGULAR, _FONT_BOLD = "NanumMyeongjo", "NanumMyeongjoBold"
            return _FONT_REGULAR, _FONT_BOLD
    except Exception:
        pass

    # Fallback: NanumGothic (sans-serif)
    gothic_reg = font_dir / "NanumGothic-Regular.ttf"
    gothic_bold = font_dir / "NanumGothic-Bold.ttf"
    _GOTHIC_URLS = {
        gothic_reg: "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf",
        gothic_bold: "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf",
    }
    try:
        for dest, url in _GOTHIC_URLS.items():
            if not dest.exists():
                urllib.request.urlretrieve(url, str(dest))
        if gothic_reg.exists():
            pdfmetrics.registerFont(TTFont("NanumGothic", str(gothic_reg)))
            pdfmetrics.registerFont(TTFont("NanumGothicBold",
                                           str(gothic_bold) if gothic_bold.exists() else str(gothic_reg)))
            _FONT_REGULAR, _FONT_BOLD = "NanumGothic", "NanumGothicBold"
            return _FONT_REGULAR, _FONT_BOLD
    except Exception:
        pass

    # Last resort
    _FONT_REGULAR, _FONT_BOLD = "Helvetica", "Helvetica-Bold"
    return _FONT_REGULAR, _FONT_BOLD


# ── Style dictionary ────────────────────────────────────────────────────────

def _build_styles(font_regular: str, font_bold: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    s: dict[str, ParagraphStyle] = {}

    # Body headings (## -> H1, ### -> H2, #### -> H3 in body context)
    s["H1"] = ParagraphStyle(
        "H1", parent=base["Normal"],
        fontSize=18, leading=24, fontName=font_bold,
        textColor=COLOR_NAVY, spaceBefore=24, spaceAfter=4,
    )
    s["H2"] = ParagraphStyle(
        "H2", parent=base["Normal"],
        fontSize=14, leading=19, fontName=font_bold,
        textColor=COLOR_NAVY, spaceBefore=18, spaceAfter=4,
    )
    s["H3"] = ParagraphStyle(
        "H3", parent=base["Normal"],
        fontSize=12, leading=16, fontName=font_bold,
        textColor=COLOR_NAVY, spaceBefore=12, spaceAfter=3,
    )
    s["Body"] = ParagraphStyle(
        "Body", parent=base["Normal"],
        fontSize=10, leading=15, fontName=font_regular,
        textColor=COLOR_BODY, alignment=TA_JUSTIFY,
        spaceBefore=2, spaceAfter=3,
    )
    s["Bullet"] = ParagraphStyle(
        "Bullet", parent=base["Normal"],
        fontSize=10, leading=15, fontName=font_regular,
        textColor=COLOR_BODY, leftIndent=18,
        spaceBefore=1, spaceAfter=1,
    )
    s["NumberedItem"] = ParagraphStyle(
        "NumberedItem", parent=base["Normal"],
        fontSize=10, leading=15, fontName=font_regular,
        textColor=COLOR_BODY, leftIndent=18,
        spaceBefore=1, spaceAfter=1,
    )
    s["Callout"] = ParagraphStyle(
        "Callout", parent=base["Normal"],
        fontSize=13, leading=18, fontName=font_bold,
        textColor=colors.white, alignment=TA_CENTER,
        spaceBefore=10, spaceAfter=10,
    )
    s["CalloutBody"] = ParagraphStyle(
        "CalloutBody", parent=base["Normal"],
        fontSize=10, leading=15, fontName=font_regular,
        textColor=COLOR_BODY, alignment=TA_LEFT,
    )

    # Cover page styles
    s["CoverLabel"] = ParagraphStyle(
        "CoverLabel", parent=base["Normal"],
        fontSize=10, leading=14, fontName=font_regular,
        textColor=COLOR_GOLD, alignment=TA_CENTER,
    )
    s["CoverTitle"] = ParagraphStyle(
        "CoverTitle", parent=base["Normal"],
        fontSize=32, leading=40, fontName=font_bold,
        textColor=colors.white, alignment=TA_CENTER,
        spaceBefore=0, spaceAfter=8,
    )
    s["CoverSub"] = ParagraphStyle(
        "CoverSub", parent=base["Normal"],
        fontSize=16, leading=22, fontName=font_regular,
        textColor=colors.HexColor("#cbd5e0"),
        alignment=TA_CENTER,
    )
    s["CoverMeta"] = ParagraphStyle(
        "CoverMeta", parent=base["Normal"],
        fontSize=10, leading=14, fontName=font_regular,
        textColor=COLOR_MUTED, alignment=TA_CENTER,
    )
    s["CoverBadge"] = ParagraphStyle(
        "CoverBadge", parent=base["Normal"],
        fontSize=14, leading=20, fontName=font_bold,
        textColor=COLOR_BODY, alignment=TA_CENTER,
    )
    s["Footer"] = ParagraphStyle(
        "Footer", parent=base["Normal"],
        fontSize=8, leading=10, fontName=font_regular,
        textColor=COLOR_MUTED, alignment=TA_CENTER,
    )
    return s


# ── Inline markdown ─────────────────────────────────────────────────────────

def _md_inline(text: str) -> str:
    """Escape XML then convert **bold** and *italic* to tags."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    return text


def _safe_para(text: str, style: ParagraphStyle) -> Paragraph:
    """Create Paragraph with fallback on XML errors."""
    try:
        return Paragraph(text, style)
    except Exception:
        plain = re.sub(r"<[^>]+>", "", text)
        return Paragraph(plain, style)


# ── Custom flowables ────────────────────────────────────────────────────────

class _CalloutBox(Flowable):
    """Blockquote box with left accent border."""

    def __init__(self, text: str, style: ParagraphStyle, width: float,
                 bg_color=COLOR_CALLOUT_BG, border_color=COLOR_CALLOUT_BORDER,
                 border_width: float = 3):
        super().__init__()
        self.para = Paragraph(text, style)
        self.box_width = width
        self.bg_color = bg_color
        self.border_color = border_color
        self.border_width = border_width
        self._inner_width = width - 24 - border_width

    def wrap(self, availWidth, availHeight):
        w, h = self.para.wrap(self._inner_width, availHeight)
        self.para_height = h
        return self.box_width, h + 20

    def draw(self):
        total_h = self.para_height + 20
        self.canv.saveState()
        self.canv.setFillColor(self.bg_color)
        self.canv.roundRect(0, 0, self.box_width, total_h, 2, fill=True, stroke=False)
        self.canv.setFillColor(self.border_color)
        self.canv.rect(0, 0, self.border_width, total_h, fill=True, stroke=False)
        self.canv.restoreState()
        self.para.drawOn(self.canv, self.border_width + 12, 10)


# ── Bookmark doc template ───────────────────────────────────────────────────

class _BookmarkDocTemplate(BaseDocTemplate):
    """BaseDocTemplate with PDF outline (bookmarks)."""

    def __init__(self, filename: str, **kw):
        self._font_regular = kw.pop("font_regular", "Helvetica")
        self._font_bold = kw.pop("font_bold", "Helvetica-Bold")
        self._company_name = kw.pop("company_name", "")
        super().__init__(filename, **kw)
        self._bookmark_key_counter: dict[str, int] = {}

    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return
        style_name = flowable.style.name
        level_map = {"H1": 0, "H2": 1, "H3": 2}
        level = level_map.get(style_name)
        if level is None:
            return
        # Clamp level to avoid jumps > 1 from current outline level
        if not hasattr(self, '_current_outline_level'):
            self._current_outline_level = -1
        if level > self._current_outline_level + 1:
            level = self._current_outline_level + 1
        self._current_outline_level = level
        text = re.sub(r"<[^>]+>", "", flowable.getPlainText())
        key_base = re.sub(r"\W+", "_", text.lower())[:40]
        count = self._bookmark_key_counter.get(key_base, 0)
        self._bookmark_key_counter[key_base] = count + 1
        key = f"{key_base}_{count}"
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=level, closed=(level > 0))


# ── Page callbacks ──────────────────────────────────────────────────────────

def _cover_page_bg(canvas, doc):
    """Full-page dark navy background for cover."""
    canvas.saveState()
    canvas.setFillColor(COLOR_NAVY)
    canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=True, stroke=False)
    canvas.restoreState()


def _page_header_footer(canvas, doc):
    """Gold header line + company name + page number on body pages."""
    w, h = doc.pagesize
    canvas.saveState()
    page_num = canvas.getPageNumber()

    # Header: thin gold line + company name
    if page_num > 1:
        canvas.setStrokeColor(COLOR_GOLD)
        canvas.setLineWidth(0.5)
        canvas.line(0.9 * inch, h - 0.6 * inch, w - 0.9 * inch, h - 0.6 * inch)

        canvas.setFont(doc._font_regular, 7.5)
        canvas.setFillColor(COLOR_MUTED)
        canvas.drawRightString(w - 0.9 * inch, h - 0.55 * inch, doc._company_name)

    # Footer: page number
    if page_num > 1:
        canvas.setFont(doc._font_regular, 8)
        canvas.setFillColor(COLOR_MUTED)
        canvas.drawCentredString(w / 2, 0.5 * inch, str(page_num))

    canvas.restoreState()


# ── Cover metadata extraction ───────────────────────────────────────────────

def _extract_cover_metadata(lines: list[str]) -> dict:
    """Parse the first ~15 lines + trailing JSON for cover page data."""
    meta: dict = {
        "company_name": "",
        "subtitle": "",
        "date": datetime.now().strftime("%Y. %m. %d"),
        "recommendation": "WATCH",
        "confidence": "",
        "valuation_line": "",
        "disclaimer": "",
    }

    for i, line in enumerate(lines[:15]):
        stripped = line.strip()

        # # Title -> company name
        if stripped.startswith("# ") and not meta["company_name"]:
            meta["company_name"] = stripped[2:].strip()
            continue

        # **subtitle** on its own line
        if re.match(r"^\*\*.+\*\*$", stripped) and not meta["subtitle"]:
            meta["subtitle"] = stripped.strip("*").strip()
            continue

        # **보고서 일자:** or **Date:**
        m = re.match(r"\*\*보고서\s*일자[:\s]*\*\*\s*(.+)", stripped)
        if not m:
            m = re.match(r"\*\*Date[:\s]*\*\*\s*(.+)", stripped, re.IGNORECASE)
        if m:
            meta["date"] = m.group(1).strip()
            continue

        # **투자 판정:** or **Recommendation:**
        m = re.match(r"\*\*투자\s*판정[:\s]*\*\*\s*(.+)", stripped)
        if not m:
            m = re.match(r"\*\*Recommendation[:\s]*\*\*\s*(.+)", stripped, re.IGNORECASE)
        if m:
            rec_text = m.group(1).strip()
            # Extract recommendation keyword
            rec_match = re.search(r"\b(INVEST|WATCH|PASS)\b", rec_text, re.IGNORECASE)
            if rec_match:
                meta["recommendation"] = rec_match.group(1).upper()
            # Extract confidence
            conf_match = re.search(r"신뢰도\s*([\d.]+)|confidence\s*([\d.]+)", rec_text, re.IGNORECASE)
            if conf_match:
                meta["confidence"] = conf_match.group(1) or conf_match.group(2)
            continue

        # Valuation line (Pre-IPO, etc.)
        if "Pre-IPO" in stripped or "Valuation" in stripped or "MOIC" in stripped:
            # Clean markdown bold
            meta["valuation_line"] = re.sub(r"\*\*(.+?)\*\*", r"\1", stripped)
            continue

        # Blockquote disclaimer
        if stripped.startswith(">"):
            meta["disclaimer"] = stripped.lstrip(">").strip()
            # Remove bold markers
            meta["disclaimer"] = re.sub(r"\*\*(.+?)\*\*", r"\1", meta["disclaimer"])
            continue

    # Parse trailing JSON for recommendation override
    json_text = "\n".join(lines)
    m = re.search(r"```json\s*(\{[^}]+\})\s*```\s*$", json_text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            if "recommendation" in data:
                meta["recommendation"] = data["recommendation"].upper()
            if "confidence" in data:
                meta["confidence"] = str(data["confidence"])
        except (json.JSONDecodeError, AttributeError):
            pass

    return meta


def _find_body_start(lines: list[str]) -> int:
    """Find where body content starts (after initial metadata + first ---)."""
    found_title = False
    for i, line in enumerate(lines):
        if line.strip().startswith("# ") and not found_title:
            found_title = True
            continue
        if found_title and line.strip() == "---":
            return i + 1
    return 0


# ── Cover page builder ─────────────────────────────────────────────────────

def _build_cover(meta: dict, styles: dict, page_w: float, page_h: float) -> list:
    """Build dark navy cover page matching the example PDF."""
    rec = meta.get("recommendation", "WATCH").upper()
    company = meta.get("company_name", "Company")
    subtitle = meta.get("subtitle", "Investment Due Diligence")
    date_str = meta.get("date", datetime.now().strftime("%Y. %m. %d"))
    confidence = meta.get("confidence", "")
    valuation = meta.get("valuation_line", "")
    disclaimer = meta.get("disclaimer", "")

    rec_labels = {
        "INVEST": "INVEST",
        "WATCH": "CONDITIONAL PROCEED",
        "PASS": "PASS",
    }
    # Check for "조건부" in the original text
    rec_label = rec_labels.get(rec, rec)

    story: list = []

    story.append(Spacer(1, 2.0 * inch))

    # "DUE DILIGENCE REPORT" in gold, letter-spaced
    story.append(_safe_para(
        '<font letterSpacing="4">D U E &nbsp; D I L I G E N C E &nbsp; R E P O R T</font>',
        styles["CoverLabel"],
    ))
    story.append(Spacer(1, 0.4 * inch))

    # Company name (large white)
    story.append(_safe_para(_md_inline(company), styles["CoverTitle"]))
    story.append(Spacer(1, 0.05 * inch))

    # Subtitle
    story.append(_safe_para(_md_inline(subtitle), styles["CoverSub"]))

    # Gold divider
    story.append(Spacer(1, 0.5 * inch))
    story.append(HRFlowable(
        width="15%", thickness=2,
        color=COLOR_GOLD, hAlign="CENTER",
    ))
    story.append(Spacer(1, 0.4 * inch))

    # Recommendation badge
    rec_color = COLOR_GOLD
    badge_style = ParagraphStyle(
        "CoverBadgeDyn", parent=styles["CoverBadge"],
        textColor=COLOR_GOLD, fontSize=16, leading=22,
    )
    story.append(_safe_para(rec_label, badge_style))

    story.append(Spacer(1, 0.6 * inch))

    # Metadata row: DATE | CLASSIFICATION | TYPE
    meta_text = (
        f'<font size="8" color="#8a9ab5">D A T E</font><br/>'
        f'<font color="#ffffff">{_md_inline(date_str)}</font>'
        f'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
        f'<font size="8" color="#8a9ab5">C L A S S I F I C A T I O N</font><br/>'
        f'<font color="#ffffff">Confidential</font>'
        f'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
        f'<font size="8" color="#8a9ab5">T Y P E</font><br/>'
        f'<font color="#ffffff">Desk Research DD</font>'
    )
    story.append(_safe_para(meta_text, styles["CoverMeta"]))

    story.append(Spacer(1, 0.8 * inch))

    # Bottom disclaimer
    disc_style = ParagraphStyle(
        "CoverDisc", parent=styles["Footer"],
        textColor=COLOR_MUTED, fontSize=7.5,
    )
    story.append(_safe_para("WORKFLOW ARCHITECTED BY DD AGENT", disc_style))
    story.append(Spacer(1, 0.1 * inch))
    if disclaimer:
        story.append(_safe_para(_md_inline(disclaimer), disc_style))
    else:
        story.append(_safe_para(
            "본 문서는 데스크 리서치 기반이며, [ESTIMATE] 태그가 붙은 수치는 검증 전 추정치입니다.",
            disc_style,
        ))

    # Switch to body template
    story.append(NextPageTemplate("main"))
    story.append(PageBreak())
    return story


# ── Table builder ───────────────────────────────────────────────────────────

def _calc_col_widths(rows: list[list[str]], avail_width: float, max_cols: int) -> list[float]:
    """Proportional column widths based on content length."""
    max_lens = [0] * max_cols
    for row in rows:
        for i, cell in enumerate(row):
            if i < max_cols:
                max_lens[i] = max(max_lens[i], len(cell))

    total = sum(max_lens) or 1
    # Minimum 35pt per column
    widths = [max(avail_width * (l / total), 35) for l in max_lens]
    # Normalize to fit avail_width
    w_total = sum(widths)
    if w_total > 0:
        widths = [w * avail_width / w_total for w in widths]
    return widths


def _build_table(table_lines: list[str], styles: dict[str, ParagraphStyle],
                 font_regular: str, font_bold: str, avail_width: float) -> list:
    """Convert markdown table lines to a styled ReportLab Table."""
    rows: list[list[str]] = []
    for line in table_lines:
        cells = [c.strip() for c in line.split("|")]
        if cells and cells[0] == "":
            cells = cells[1:]
        if cells and cells[-1] == "":
            cells = cells[:-1]
        rows.append(cells)

    if not rows:
        return []

    max_cols = max(len(r) for r in rows)

    # Adjust font size for wide tables
    if max_cols >= 5:
        hdr_size, cell_size = 7.5, 7.5
    else:
        hdr_size, cell_size = 8.5, 8.5

    header_style = ParagraphStyle(
        "TblHdr", parent=styles["Body"],
        fontName=font_bold, fontSize=hdr_size, leading=hdr_size + 4,
        textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "TblCell", parent=styles["Body"],
        fontName=font_regular, fontSize=cell_size, leading=cell_size + 4,
        alignment=TA_LEFT, textColor=COLOR_BODY,
    )

    table_data = []
    for row_idx, row in enumerate(rows):
        st = header_style if row_idx == 0 else cell_style
        processed = []
        for c in row:
            processed.append(_safe_para(_md_inline(c), st))
        table_data.append(processed)

    # Pad short rows
    for row in table_data:
        while len(row) < max_cols:
            row.append(_safe_para("", cell_style))

    col_widths = _calc_col_widths(rows, avail_width, max_cols)

    table = Table(table_data, colWidths=col_widths, repeatRows=1)

    style_cmds = [
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        # Alternating rows
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_ROW_ALT]),
        # Padding
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        # Grid
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, COLOR_NAVY),
        ("LINEBELOW", (0, 1), (-1, -2), 0.5, COLOR_DIV_MED),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, COLOR_DIV_MED),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    table.setStyle(TableStyle(style_cmds))

    return [Spacer(1, 6), table, Spacer(1, 8)]


# ── Markdown body parser ────────────────────────────────────────────────────

def _parse_markdown_body(md: str, styles: dict[str, ParagraphStyle],
                         font_regular: str, font_bold: str,
                         page_width: float) -> list:
    """Convert markdown body to ReportLab flowables."""
    flowables = []
    lines = md.splitlines()
    in_code_block = False
    i = 0
    avail_width = page_width - 1.8 * inch

    while i < len(lines):
        line = lines[i]

        # Code fence — skip (including trailing JSON)
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            i += 1
            continue
        if in_code_block:
            i += 1
            continue

        stripped = line.strip()

        # Horizontal rule --- → gold divider
        if stripped == "---":
            flowables.append(Spacer(1, 6))
            flowables.append(HRFlowable(
                width="100%", thickness=1,
                color=COLOR_GOLD, spaceAfter=6,
            ))
            i += 1
            continue

        # ## Section → H1 (18pt) with gold rule
        if line.startswith("## "):
            text = _md_inline(line[3:].strip())
            flowables.append(_safe_para(text, styles["H1"]))
            flowables.append(HRFlowable(
                width="100%", thickness=1.5,
                color=COLOR_GOLD, spaceAfter=8,
            ))
            i += 1
            # Skip --- immediately after ## heading
            if i < len(lines) and lines[i].strip() == "---":
                i += 1
            continue

        # ### Subsection → H2 (14pt)
        if line.startswith("### "):
            text = _md_inline(line[4:].strip())
            flowables.append(_safe_para(text, styles["H2"]))
            flowables.append(HRFlowable(
                width="100%", thickness=0.5,
                color=COLOR_DIV_LIGHT, spaceAfter=4,
            ))
            i += 1
            continue

        # #### Sub-subsection → H3 (12pt)
        if line.startswith("#### "):
            text = _md_inline(line[5:].strip())
            flowables.append(_safe_para(text, styles["H3"]))
            i += 1
            continue

        # Blockquote
        if stripped.startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            quote_text = _md_inline(" ".join(quote_lines))
            flowables.append(Spacer(1, 4))
            flowables.append(_CalloutBox(quote_text, styles["CalloutBody"], avail_width))
            flowables.append(Spacer(1, 6))
            continue

        # Markdown table
        if "|" in line and stripped.startswith("|"):
            table_lines = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip().startswith("|"):
                s = lines[i].strip()
                # Skip separator row (|---|---|)
                if not re.match(r"^\|[\s\-:|]+\|$", s):
                    table_lines.append(s)
                i += 1
            if table_lines:
                flowables.extend(_build_table(
                    table_lines, styles, font_regular, font_bold, avail_width,
                ))
            continue

        # Bullet list
        if stripped.startswith("- ") or stripped.startswith("* "):
            content = stripped[2:].strip()
            flowables.append(_safe_para(f"• {_md_inline(content)}", styles["Bullet"]))
            i += 1
            continue

        # Numbered list
        m = re.match(r"^(\d+)\.\s+(.+)", stripped)
        if m:
            num = m.group(1)
            content = m.group(2).strip()
            flowables.append(_safe_para(
                f"{num}. {_md_inline(content)}", styles["NumberedItem"],
            ))
            i += 1
            continue

        # Blank line
        if not stripped:
            flowables.append(Spacer(1, 4))
            i += 1
            continue

        # Plain text paragraph
        text = _md_inline(stripped)
        if text:
            flowables.append(_safe_para(text, styles["Body"]))
        i += 1

    return flowables


# ── Main entry point ────────────────────────────────────────────────────────

def generate_local_pdf(report_md_path: str, output_path: str | None = None) -> str:
    """Generate styled PDF from a dd-local report.md file."""
    md_path = Path(report_md_path)
    if not md_path.exists():
        raise FileNotFoundError(f"Report not found: {md_path}")

    md_text = md_path.read_text(encoding="utf-8")
    lines = md_text.splitlines()

    # Extract cover metadata
    meta = _extract_cover_metadata(lines)

    # Setup fonts
    font_regular, font_bold = _setup_fonts()
    styles = _build_styles(font_regular, font_bold)

    # Output path
    if output_path is None:
        output_path = str(md_path.parent / (md_path.stem + ".pdf"))

    # Build document
    page_size = A4
    doc = _BookmarkDocTemplate(
        output_path,
        pagesize=page_size,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        title=f"Due Diligence — {meta.get('company_name', 'Company')}",
        author="DD Agent",
        subject=f"Investment recommendation: {meta.get('recommendation', 'WATCH')}",
        font_regular=font_regular,
        font_bold=font_bold,
        company_name=meta.get("company_name", ""),
    )

    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height, id="normal",
    )
    cover_frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height, id="cover",
    )
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=cover_frame, onPage=_cover_page_bg),
        PageTemplate(id="main", frames=frame, onPage=_page_header_footer),
    ])

    story: list = []

    # Cover page
    story.extend(_build_cover(meta, styles, page_size[0], page_size[1]))

    # Body: skip cover metadata, parse rest
    body_start = _find_body_start(lines)
    body_lines = lines[body_start:]

    # Remove trailing JSON block
    body_md = "\n".join(body_lines)
    body_md = re.sub(r"```json\s*\{[^}]*\}\s*```\s*$", "", body_md, flags=re.DOTALL)

    story.extend(_parse_markdown_body(
        body_md, styles, font_regular, font_bold, page_size[0],
    ))

    doc.build(story)
    return os.path.abspath(output_path)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Convert dd-local report.md to styled PDF")
    parser.add_argument("report_path", help="Path to report.md")
    parser.add_argument("-o", "--output", help="Output PDF path")
    args = parser.parse_args()
    result = generate_local_pdf(args.report_path, args.output)
    print(f"PDF generated: {result}")
