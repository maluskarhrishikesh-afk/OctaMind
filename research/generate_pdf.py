"""
Generate a properly formatted academic PDF from LLM_DAG_ORCHESTRATION.md
for arXiv submission using ReportLab Platypus.
"""

import re
import os
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Preformatted, HRFlowable, KeepTogether, PageBreak, Flowable, Image
)
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Output path ───────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_MD   = os.path.join(SCRIPT_DIR, "LLM_DAG_ORCHESTRATION.md")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "LLM_DAG_ORCHESTRATION.pdf")

# ── Page geometry ─────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = LETTER
LEFT_MARGIN   = 1.25 * inch
RIGHT_MARGIN  = 1.25 * inch
TOP_MARGIN    = 1.0  * inch
BOTTOM_MARGIN = 1.0  * inch

# ── Colour palette ────────────────────────────────────────────────────────────
DARK_BLUE  = colors.HexColor("#1a3a5c")
MID_BLUE   = colors.HexColor("#2c5f8a")
LIGHT_GREY = colors.HexColor("#f0f0f0")
CODE_BG    = colors.HexColor("#f5f5f5")
BORDER     = colors.HexColor("#cccccc")
BLACK      = colors.black

# ── Styles ────────────────────────────────────────────────────────────────────
def build_styles() -> dict:
    base = getSampleStyleSheet()
    s = {}

    s["paper_title"] = ParagraphStyle(
        "paper_title",
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=24,
        alignment=TA_CENTER,
        textColor=DARK_BLUE,
        spaceAfter=6,
    )
    s["authors"] = ParagraphStyle(
        "authors",
        fontName="Helvetica",
        fontSize=11,
        leading=16,
        alignment=TA_CENTER,
        textColor=MID_BLUE,
        spaceAfter=3,
    )
    s["meta"] = ParagraphStyle(
        "meta",
        fontName="Helvetica-Oblique",
        fontSize=10,
        leading=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
        spaceAfter=3,
    )
    s["abstract_heading"] = ParagraphStyle(
        "abstract_heading",
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=16,
        alignment=TA_CENTER,
        spaceAfter=4,
        spaceBefore=10,
    )
    s["abstract_body"] = ParagraphStyle(
        "abstract_body",
        fontName="Times-Roman",
        fontSize=10,
        leading=15,
        alignment=TA_JUSTIFY,
        leftIndent=36,
        rightIndent=36,
        spaceAfter=14,
    )
    s["h1"] = ParagraphStyle(
        "h1",
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=DARK_BLUE,
        spaceBefore=18,
        spaceAfter=6,
        keepWithNext=1,
    )
    s["h2"] = ParagraphStyle(
        "h2",
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=MID_BLUE,
        spaceBefore=12,
        spaceAfter=4,
        keepWithNext=1,
    )
    s["h3"] = ParagraphStyle(
        "h3",
        fontName="Helvetica-BoldOblique",
        fontSize=11,
        leading=15,
        textColor=MID_BLUE,
        spaceBefore=10,
        spaceAfter=3,
        keepWithNext=1,
    )
    s["body"] = ParagraphStyle(
        "body",
        fontName="Times-Roman",
        fontSize=10.5,
        leading=16,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
    )
    s["blockquote"] = ParagraphStyle(
        "blockquote",
        fontName="Times-Italic",
        fontSize=10.5,
        leading=16,
        alignment=TA_JUSTIFY,
        leftIndent=24,
        rightIndent=24,
        spaceAfter=6,
        spaceBefore=6,
    )
    s["bullet"] = ParagraphStyle(
        "bullet",
        fontName="Times-Roman",
        fontSize=10.5,
        leading=16,
        leftIndent=24,
        bulletIndent=6,
        spaceAfter=2,
    )
    s["code"] = ParagraphStyle(
        "code",
        fontName="Courier",
        fontSize=8.5,
        leading=13,
        leftIndent=12,
        rightIndent=12,
        spaceAfter=0,
    )
    s["caption"] = ParagraphStyle(
        "caption",
        fontName="Times-Italic",
        fontSize=9,
        leading=13,
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    s["ref_entry"] = ParagraphStyle(
        "ref_entry",
        fontName="Times-Roman",
        fontSize=10,
        leading=15,
        leftIndent=24,
        firstLineIndent=-24,
        spaceAfter=5,
    )
    return s


# ── Unicode / emoji substitution map ────────────────────────────────────────
# Replace characters outside standard PS Type-1 font range with styled XML
_UNICODE_SUBS = [
    # Emoji check / cross
    ("\u2705", '<font color="#1a7a3c"><b>Yes</b></font>'),   # ✅
    ("\u274c", '<font color="#cc2200"><b>No</b></font>'),    # ❌
    ("\u2714", '<font color="#1a7a3c"><b>Yes</b></font>'),   # ✔
    ("\u2716", '<font color="#cc2200"><b>No</b></font>'),    # ✖
    ("\u2713", '<font color="#1a7a3c">&#x2713;</font>'),    # ✓  (Latin Extended)
    ("\u2717", '<font color="#cc2200">&#x2717;</font>'),    # ✗
    # Arrows / math that are safe in Latin-1
    ("\u2192", "&#x2192;"),   # →
    ("\u2190", "&#x2190;"),   # ←
    ("\u2014", "&#x2014;"),   # —  em-dash
    ("\u2013", "&#x2013;"),   # –  en-dash
    ("\u2026", "..."),         # …
]


# ── Inline markdown → ReportLab XML ──────────────────────────────────────────
def inline(text: str) -> str:
    """Convert inline markdown (bold, italic, backtick) to ReportLab XML."""
    # Swap emoji/special Unicode BEFORE XML escaping so placeholders survive
    placeholders = {}
    for ch, replacement in _UNICODE_SUBS:
        if ch in text:
            key = f"__PH{len(placeholders)}__"
            text = text.replace(ch, key)
            placeholders[key] = replacement

    # Escape XML special chars
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Restore placeholders (they contain valid XML)
    for key, val in placeholders.items():
        text = text.replace(key, val)

    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # Italic
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    # Inline code → courier
    text = re.sub(r"`([^`]+)`", r'<font name="Courier" size="9">\1</font>', text)
    # Links — strip, keep text
    text = re.sub(r"\[(.+?)\]\(https?://[^\)]+\)", r"\1", text)
    return text


# ── Table helpers ─────────────────────────────────────────────────────────────
def parse_md_table(lines: list[str], styles: dict) -> Table:
    """Parse a markdown table and return a ReportLab Table flowable."""
    rows = []
    col_count = 0
    for line in lines:
        line = line.strip()
        if re.match(r"^[\|\s\-:]+$", line):          # separator row
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        col_count = max(col_count, len(cells))
        rows.append(cells)

    if not rows:
        return None

    # Normalize column count
    norm = []
    for row in rows:
        while len(row) < col_count:
            row.append("")
        norm.append(row)

    # Determine column widths — give the first (label) column more room
    usable = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN
    if col_count >= 5:
        first_col_w  = usable * 0.30
        rest_col_w   = (usable - first_col_w) / (col_count - 1)
        col_widths   = [first_col_w] + [rest_col_w] * (col_count - 1)
        tbl_font     = 8.5
    elif col_count == 4:
        first_col_w  = usable * 0.28
        rest_col_w   = (usable - first_col_w) / 3
        col_widths   = [first_col_w] + [rest_col_w] * 3
        tbl_font     = 9.0
    elif col_count == 3:
        first_col_w  = usable * 0.32
        rest_col_w   = (usable - first_col_w) / 2
        col_widths   = [first_col_w] + [rest_col_w] * 2
        tbl_font     = 9.5
    else:
        col_widths   = [usable / col_count] * col_count
        tbl_font     = 9.5

    # Build cell style with correct font size
    cell_style = ParagraphStyle(
        "tbl_cell",
        parent=styles["body"],
        fontSize=tbl_font,
        leading=tbl_font * 1.35,
    )

    # First row = header
    tbl_data = []
    for r_idx, row in enumerate(norm):
        para_row = []
        for c_idx, cell in enumerate(row):
            if r_idx == 0:
                para_row.append(Paragraph(f"<b>{inline(cell)}</b>", cell_style))
            else:
                para_row.append(Paragraph(inline(cell), cell_style))
        tbl_data.append(para_row)

    tbl = Table(tbl_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dce8f5")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), DARK_BLUE),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), tbl_font),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ("GRID",       (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    return tbl


# ── Page template ─────────────────────────────────────────────────────────────
def on_first_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.HexColor("#888888"))
    canvas.drawCentredString(PAGE_W / 2, 0.6 * inch, "arXiv preprint — March 2026")
    canvas.restoreState()


def on_later_pages(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.HexColor("#888888"))
    # Running head
    canvas.drawString(LEFT_MARGIN, PAGE_H - 0.7 * inch,
                      "LLM-Driven DAG Planning for Multi-Agent AI Orchestration")
    # Page number
    canvas.drawRightString(PAGE_W - RIGHT_MARGIN, PAGE_H - 0.7 * inch,
                           f"Page {doc.page}")
    # Footer
    canvas.drawCentredString(PAGE_W / 2, 0.6 * inch, "arXiv preprint — March 2026")
    canvas.restoreState()


# ── Main parse loop ───────────────────────────────────────────────────────────
def md_to_flowables(md_text: str, styles: dict) -> list:
    lines   = md_text.splitlines()
    story   = []
    i       = 0
    n       = len(lines)

    # Header block state
    in_abstract  = False
    abstract_buf = []
    header_done  = False
    title_lines  = []
    author_lines = []
    meta_lines   = []

    def flush_abstract():
        nonlocal in_abstract, abstract_buf
        if abstract_buf:
            text = " ".join(abstract_buf).strip()
            story.append(Paragraph("Abstract", styles["abstract_heading"]))
            story.append(Paragraph(inline(text), styles["abstract_body"]))
            story.append(HRFlowable(width="100%", thickness=0.5,
                                    color=BORDER, spaceAfter=8))
            abstract_buf = []
            in_abstract  = False

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # ── Title (first # heading) ──────────────────────────────────────────
        if stripped.startswith("# ") and not header_done:
            title_text = stripped[2:].strip()
            story.append(Spacer(1, 0.2 * inch))
            story.append(Paragraph(inline(title_text), styles["paper_title"]))
            story.append(Spacer(1, 0.08 * inch))
            i += 1
            # Collect author/meta block (**key:** value lines)
            while i < n and lines[i].strip() != "---":
                l = lines[i].strip()
                if l.startswith("**Authors:**") or l.startswith("**Author:**"):
                    val = re.sub(r"\*\*.*?\*\*\s*", "", l).strip().lstrip(":")
                    story.append(Paragraph(inline(val), styles["authors"]))
                elif l.startswith("**Date:**"):
                    val = l.replace("**Date:**", "").strip()
                    story.append(Paragraph(val, styles["meta"]))
                elif l.startswith("**Project:**"):
                    val = l.replace("**Project:**", "").strip()
                    story.append(Paragraph(val, styles["meta"]))
                elif l.startswith("**Repository:**"):
                    val = l.replace("**Repository:**", "").strip()
                    story.append(Paragraph(val, styles["meta"]))
                i += 1
            story.append(Spacer(1, 0.1 * inch))
            header_done = True
            continue

        # ── Horizontal rule → spacer+line ───────────────────────────────────
        if re.match(r"^-{3,}$", stripped):
            if in_abstract:
                flush_abstract()
            else:
                story.append(Spacer(1, 4))
                story.append(HRFlowable(width="100%", thickness=0.5,
                                        color=BORDER, spaceAfter=4))
            i += 1
            continue

        # ── Abstract heading ─────────────────────────────────────────────────
        if re.match(r"^## Abstract$", stripped, re.IGNORECASE):
            in_abstract = True
            i += 1
            continue

        if in_abstract:
            if stripped.startswith("## ") or stripped.startswith("# "):
                flush_abstract()
                # fall through to handle this heading normally
            elif stripped == "---":
                flush_abstract()
                story.append(HRFlowable(width="100%", thickness=0.5,
                                        color=BORDER, spaceAfter=8))
                i += 1
                continue
            else:
                if stripped:
                    abstract_buf.append(stripped)
                i += 1
                continue

        # ── Section headings ─────────────────────────────────────────────────
        m = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if m:
            level = len(m.group(1))
            text  = m.group(2)
            if level == 1:
                story.append(Paragraph(inline(text), styles["h1"]))
            elif level == 2:
                story.append(Paragraph(inline(text), styles["h2"]))
            else:
                story.append(Paragraph(inline(text), styles["h3"]))
            i += 1
            continue
        # ── Inline image: ![alt](path.png) ─────────────────────────────────────
        m_img = re.match(r'^!\[([^\]]*)\]\(([^)]+)\)$', stripped)
        if m_img:
            alt_text = m_img.group(1)
            img_rel  = m_img.group(2)
            img_path = os.path.join(SCRIPT_DIR, img_rel)
            if os.path.exists(img_path):
                usable = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN
                # Preserve aspect ratio: read actual image size and scale proportionally
                try:
                    from PIL import Image as _PILImage
                    with _PILImage.open(img_path) as _im:
                        _iw, _ih = _im.size
                    _max_w  = min(usable * 0.82, 5.5 * inch)  # max 82% of column or 5.5"
                    _scale  = _max_w / _iw
                    _img_h  = _ih * _scale
                    img_flow = Image(img_path, width=_max_w, height=_img_h)
                except Exception:
                    # Fallback: let ReportLab scale width only (preserves ratio natively)
                    img_flow = Image(img_path, width=min(usable * 0.82, 5.5 * inch))
                # Centre the image by wrapping in a 1-cell table
                img_table = Table([[img_flow]], colWidths=[usable])
                img_table.setStyle(TableStyle([
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('LEFTPADDING', (0,0), (-1,-1), 0),
                    ('RIGHTPADDING', (0,0), (-1,-1), 0),
                    ('TOPPADDING', (0,0), (-1,-1), 0),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ]))
                story.append(Spacer(1, 14))
                story.append(img_table)
                story.append(Paragraph(f"<i>{alt_text}</i>", styles["caption"]))
                story.append(Spacer(1, 14))
            i += 1
            continue
        # ── Code block ───────────────────────────────────────────────────────
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            i += 1
            code_lines = []
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # consume closing ```
            # Wrap long lines so they don't overflow the page (~82 chars at 8.5pt Courier)
            MAX_CODE_CHARS = 82
            wrapped_lines = []
            for cl in code_lines:
                if len(cl) <= MAX_CODE_CHARS:
                    wrapped_lines.append(cl)
                else:
                    # Find a sensible break point (space, comma, quote) near the limit
                    while len(cl) > MAX_CODE_CHARS:
                        break_at = MAX_CODE_CHARS
                        for sep in (' ', ',', '+', '"', "'"):
                            idx = cl.rfind(sep, MAX_CODE_CHARS - 20, MAX_CODE_CHARS)
                            if idx != -1:
                                break_at = idx + 1
                                break
                        wrapped_lines.append(cl[:break_at])
                        cl = '    ' + cl[break_at:]  # indent continuation
                    wrapped_lines.append(cl)
            code_text = "\n".join(wrapped_lines)
            # Build a table-based code block with background
            usable = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN
            code_para = Preformatted(code_text, styles["code"])
            code_table = Table(
                [[code_para]],
                colWidths=[usable],
                style=TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
                    ("BOX",        (0, 0), (-1, -1), 0.5, BORDER),
                    ("TOPPADDING",    (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
                ])
            )
            story.append(Spacer(1, 4))
            story.append(code_table)
            story.append(Spacer(1, 8))
            continue

        # ── Table ────────────────────────────────────────────────────────────
        if stripped.startswith("|") and stripped.endswith("|"):
            tbl_lines = []
            while i < n and lines[i].strip().startswith("|"):
                tbl_lines.append(lines[i])
                i += 1
            tbl = parse_md_table(tbl_lines, styles)
            if tbl:
                story.append(Spacer(1, 4))
                story.append(tbl)
                story.append(Spacer(1, 8))
            continue

        # ── Mermaid / Architecture Box ──────────────────────────────────────
        if stripped.startswith("```mermaid"):
             # Consume the mermaid block
             i += 1
             while i < n and not lines[i].strip().startswith("```"):
                 i += 1
             i += 1 # consume ending ```
             # Prefer embedding a prepared PNG/SVG image if available; otherwise draw a Flowable
             usable = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN

             # Try to embed an external diagram image (PNG). If not present, attempt to convert SVG->PNG
             svg_path = os.path.join(SCRIPT_DIR, 'diagram.svg')
             png_candidates = [
                 os.path.join(SCRIPT_DIR, 'diagram.png'),
                 os.path.join(SCRIPT_DIR, 'DAG.png'),
             ]
             found_png = None
             for pth in png_candidates:
                 if os.path.exists(pth):
                     found_png = pth
                     break
             if found_png:
                 img = Image(found_png, width=usable)
                 story.append(Spacer(1, 12))
                 story.append(img)
                 story.append(Paragraph("<i>Figure 1: Two-Level DAG Orchestration Architecture.</i>", styles["caption"]))
                 story.append(Spacer(1, 12))
                 continue
             # attempt on-the-fly conversion from SVG -> PNG using cairosvg if available
             if os.path.exists(svg_path):
                 try:
                     import importlib
                     if importlib.util.find_spec('cairosvg'):
                         import cairosvg
                         cairosvg.svg2png(url=svg_path, write_to=png_path, output_width=int(usable))
                         if os.path.exists(png_path):
                             img = Image(png_path, width=usable)
                             story.append(Spacer(1, 12))
                             story.append(img)
                             story.append(Paragraph("<i>Figure 1: Two-Level DAG Orchestration Architecture.</i>", styles["caption"]))
                             story.append(Spacer(1, 12))
                             continue
                 except Exception:
                     # fall-through to drawn diagram
                     pass

             # Insert a drawn diagram Flowable for crisp vector graphics in the PDF (fallback)
             class DiagramFlowable(Flowable):
                 def __init__(self, width, height=220):
                     super().__init__()
                     self.width = width
                     self.height = height

                 def wrap(self, availWidth, availHeight):
                     return (self.width, self.height)

                 def draw(self):
                     c = self.canv
                     w = self.width
                     h = self.height
                     # Colors
                     stroke = colors.HexColor("#1a3a5c")
                     fill1  = colors.HexColor("#e7f3ff")
                     fill2  = colors.HexColor("#e9f7ee")
                     c.saveState()
                     c.setStrokeColor(stroke)
                     c.setLineWidth(1.25)

                     # Macro planner box
                     box_w = w * 0.7
                     box_h = 56
                     x0 = (w - box_w) / 2
                     y0 = h - 40 - box_h
                     c.setFillColor(fill1)
                     c.roundRect(x0, y0, box_w, box_h, 6, stroke=1, fill=1)
                     c.setFillColor(colors.black)
                     c.setFont("Helvetica-Bold", 11)
                     c.drawCentredString(x0 + box_w/2, y0 + box_h/2 - 4, "MACRO DAG PLANNER (dag_planner.py)")
                     c.setFont("Helvetica", 9)
                     c.drawCentredString(x0 + box_w/2, y0 + box_h/2 - 18, "Single LLM call → JSON DAG Plan → Kahn's Topological Sort")

                     # Agents row
                     agent_y = y0 - 70
                     agent_w = box_w / 4
                     agent_h = 40
                     agents = ["FILES Agent", "EMAIL Agent", "DRIVE Agent"]
                     for i, name in enumerate(agents):
                         ax = x0 + i * (agent_w + 10)
                         ay = agent_y
                         c.setFillColor(colors.white)
                         c.roundRect(ax, ay, agent_w, agent_h, 4, stroke=1, fill=1)
                         c.setFont("Helvetica-Bold", 9)
                         c.drawCentredString(ax + agent_w/2, ay + agent_h/2 - 4, name)

                     # Arrows from macro box down to agents
                     arrow_y0 = y0
                     for i in range(3):
                         ax = x0 + (i+0.5)*(agent_w + 10)
                         c.setLineWidth(1)
                         c.line(x0 + box_w/2, arrow_y0, ax + agent_w/2, agent_y + agent_h)
                         # arrow head
                         c.line(ax + agent_w/2 - 4, agent_y + agent_h + 6, ax + agent_w/2, agent_y + agent_h)
                         c.line(ax + agent_w/2 + 4, agent_y + agent_h + 6, ax + agent_w/2, agent_y + agent_h)

                     # Micro engine box
                     micro_y = agent_y - 100
                     micro_w = box_w
                     micro_h = 66
                     c.setFillColor(fill2)
                     c.roundRect(x0, micro_y, micro_w, micro_h, 6, stroke=1, fill=1)
                     c.setFont("Helvetica-Bold", 11)
                     c.drawCentredString(x0 + micro_w/2, micro_y + micro_h/2 + 6, "MICRO DAG ENGINE (skill_dag_engine.py)")
                     c.setFont("Helvetica", 9)
                     c.drawCentredString(x0 + micro_w/2, micro_y + micro_h/2 - 6, "LLM: Plan → Deterministic Exec → Synthesize")

                     # Arrows from agents to micro engine
                     for i in range(3):
                         ax = x0 + (i+0.5)*(agent_w + 10)
                         c.line(ax + agent_w/2, agent_y, x0 + micro_w/2 - 60 + i*30, micro_y + micro_h)

                     c.restoreState()

             story.append(Spacer(1, 12))
             story.append(DiagramFlowable(usable, height=260))
             story.append(Paragraph("<i>Figure 1: Two-Level DAG Orchestration Architecture. The macro planner routes tasks across agents via topological sort, while the micro engine executes tool-level sequences with fixed LLM overhead.</i>", styles["caption"]))
             story.append(Spacer(1, 12))
             continue

        # ── Blockquote ───────────────────────────────────────────────────────
        if stripped.startswith("> "):
            text = stripped[2:].strip()
            story.append(Paragraph(inline(text), styles["blockquote"]))
            i += 1
            continue

        # ── Bullet list ──────────────────────────────────────────────────────
        if re.match(r"^[-*]\s+", stripped):
            while i < n and re.match(r"^[-*]\s+", lines[i].strip()):
                item_text = re.sub(r"^[-*]\s+", "", lines[i].strip())
                story.append(Paragraph(f"• &nbsp;{inline(item_text)}",
                                       styles["bullet"]))
                i += 1
            story.append(Spacer(1, 4))
            continue

        # ── Numbered list ────────────────────────────────────────────────────
        if re.match(r"^\d+\.\s+", stripped):
            num = 1
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                item_text = re.sub(r"^\d+\.\s+", "", lines[i].strip())
                story.append(Paragraph(f"{num}.&nbsp; {inline(item_text)}",
                                       styles["bullet"]))
                num += 1
                i += 1
            story.append(Spacer(1, 4))
            continue

        # ── Table heading row (| Field | ... ) already handled above ─────────

        # ── Definition list style ( **Key:** value ) ─────────────────────────
        if re.match(r"^\*\*[A-Za-z ]+:\*\*", stripped):
            story.append(Paragraph(inline(stripped), styles["body"]))
            i += 1
            continue

        # ── Empty line → small spacer ─────────────────────────────────────────
        if stripped == "":
            story.append(Spacer(1, 4))
            i += 1
            continue

        # ── Regular paragraph ─────────────────────────────────────────────────
        # Accumulate continuation lines (same paragraph until blank or special)
        para_lines = [stripped]
        i += 1
        while i < n:
            next_strip = lines[i].strip()
            # Stop at structural elements
            if (next_strip == ""
                or next_strip.startswith("#")
                or next_strip.startswith("|")
                or next_strip.startswith("```")
                or next_strip.startswith("> ")
                or re.match(r"^[-*]\s+", next_strip)
                or re.match(r"^\d+\.\s+", next_strip)
                or re.match(r"^-{3,}$", next_strip)):
                break
            para_lines.append(next_strip)
            i += 1
        text = " ".join(para_lines)
        story.append(Paragraph(inline(text), styles["body"]))

    if in_abstract:
        flush_abstract()

    return story


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    print(f"Reading: {INPUT_MD}")
    with open(INPUT_MD, encoding="utf-8") as f:
        md_text = f.read()

    styles = build_styles()
    story  = md_to_flowables(md_text, styles)

    doc = SimpleDocTemplate(
        OUTPUT_PDF,
        pagesize=LETTER,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title="LLM-Driven DAG Planning with Topological Execution for Multi-Agent AI Orchestration",
        author="Hrishikesh Maluskar",
        subject="Multi-Agent AI Orchestration, DAG Planning, LLM",
        keywords="LLM, DAG, multi-agent, orchestration, topological sort, ReAct",
        creator="OctaMind Research",
    )

    doc.build(
        story,
        onFirstPage=on_first_page,
        onLaterPages=on_later_pages,
    )
    print(f"\nPDF written to: {OUTPUT_PDF}")
    size_kb = os.path.getsize(OUTPUT_PDF) // 1024
    print(f"File size: {size_kb} KB")


if __name__ == "__main__":
    main()
