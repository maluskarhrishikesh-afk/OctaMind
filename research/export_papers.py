"""Export research markdown papers to PDF and ODT.

Usage:
    python research/export_papers.py
    python research/export_papers.py research/LLM_DAG_ORCHESTRATION.md
    python research/export_papers.py --pdf-only
    python research/export_papers.py --odt-only research/MARKDOWN_NATIVE_MEMORY_FAISS_ARCHITECTURE.md
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from odf.opendocument import OpenDocumentText
from odf.style import ParagraphProperties, Style, TextProperties
from odf.text import H, List, ListItem, P
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Image, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUTS = [
    SCRIPT_DIR / "LLM_DAG_ORCHESTRATION.md",
    SCRIPT_DIR / "MARKDOWN_NATIVE_MEMORY_FAISS_ARCHITECTURE.md",
]

PAGE_W, PAGE_H = LETTER
LEFT_MARGIN = 1.25 * inch
RIGHT_MARGIN = 1.25 * inch
TOP_MARGIN = 1.0 * inch
BOTTOM_MARGIN = 1.0 * inch

DARK_BLUE = colors.HexColor("#1a3a5c")
MID_BLUE = colors.HexColor("#2c5f8a")
LIGHT_GREY = colors.HexColor("#f0f0f0")
CODE_BG = colors.HexColor("#f5f5f5")
BORDER = colors.HexColor("#cccccc")

UNICODE_SUBS = [
    ("\u2705", '<font color="#1a7a3c"><b>Yes</b></font>'),
    ("\u274c", '<font color="#cc2200"><b>No</b></font>'),
    ("\u2714", '<font color="#1a7a3c"><b>Yes</b></font>'),
    ("\u2716", '<font color="#cc2200"><b>No</b></font>'),
    ("\u2713", '<font color="#1a7a3c">&#x2713;</font>'),
    ("\u2717", '<font color="#cc2200">&#x2717;</font>'),
    ("\u2192", "&#x2192;"),
    ("\u2190", "&#x2190;"),
    ("\u2014", "&#x2014;"),
    ("\u2013", "&#x2013;"),
    ("\u2026", "..."),
]


def build_pdf_styles() -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    out: dict[str, ParagraphStyle] = {}

    out["paper_title"] = ParagraphStyle(
        "paper_title",
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=24,
        alignment=TA_CENTER,
        textColor=DARK_BLUE,
        spaceAfter=6,
    )
    out["authors"] = ParagraphStyle(
        "authors",
        fontName="Helvetica",
        fontSize=11,
        leading=16,
        alignment=TA_CENTER,
        textColor=MID_BLUE,
        spaceAfter=3,
    )
    out["meta"] = ParagraphStyle(
        "meta",
        fontName="Helvetica-Oblique",
        fontSize=10,
        leading=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
        spaceAfter=3,
    )
    out["abstract_heading"] = ParagraphStyle(
        "abstract_heading",
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=16,
        alignment=TA_CENTER,
        spaceAfter=4,
        spaceBefore=10,
    )
    out["abstract_body"] = ParagraphStyle(
        "abstract_body",
        fontName="Times-Roman",
        fontSize=10,
        leading=15,
        alignment=TA_JUSTIFY,
        leftIndent=36,
        rightIndent=36,
        spaceAfter=14,
    )
    out["h1"] = ParagraphStyle(
        "h1",
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=DARK_BLUE,
        spaceBefore=18,
        spaceAfter=6,
        keepWithNext=1,
    )
    out["h2"] = ParagraphStyle(
        "h2",
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=MID_BLUE,
        spaceBefore=12,
        spaceAfter=4,
        keepWithNext=1,
    )
    out["h3"] = ParagraphStyle(
        "h3",
        fontName="Helvetica-BoldOblique",
        fontSize=11,
        leading=15,
        textColor=MID_BLUE,
        spaceBefore=10,
        spaceAfter=3,
        keepWithNext=1,
    )
    out["body"] = ParagraphStyle(
        "body",
        fontName="Times-Roman",
        fontSize=10.5,
        leading=16,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
    )
    out["blockquote"] = ParagraphStyle(
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
    out["bullet"] = ParagraphStyle(
        "bullet",
        fontName="Times-Roman",
        fontSize=10.5,
        leading=16,
        leftIndent=24,
        bulletIndent=6,
        spaceAfter=2,
    )
    out["code"] = ParagraphStyle(
        "code",
        fontName="Courier",
        fontSize=8.5,
        leading=13,
        leftIndent=12,
        rightIndent=12,
        spaceAfter=0,
    )
    out["caption"] = ParagraphStyle(
        "caption",
        fontName="Times-Italic",
        fontSize=9,
        leading=13,
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    out["table_cell"] = ParagraphStyle(
        "table_cell",
        parent=styles["BodyText"],
        fontName="Times-Roman",
        fontSize=9.5,
        leading=12,
    )
    return out


def inline_pdf(text: str) -> str:
    placeholders: dict[str, str] = {}
    for ch, replacement in UNICODE_SUBS:
        if ch in text:
            key = f"__PH{len(placeholders)}__"
            text = text.replace(ch, key)
            placeholders[key] = replacement

    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for key, value in placeholders.items():
        text = text.replace(key, value)

    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier" size="9">\1</font>', text)
    text = re.sub(r"\[(.+?)\]\(([^)]+)\)", r"\1", text)
    return text


def plain_text(text: str) -> str:
    text = re.sub(r"\[(.+?)\]\(([^)]+)\)", r"\1", text)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    return text.strip()


def parse_front_matter(md_text: str) -> tuple[str, list[tuple[str, str]]]:
    lines = md_text.splitlines()
    title = "Untitled Paper"
    meta: list[tuple[str, str]] = []
    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            idx += 1
            break
        idx += 1

    while idx < len(lines):
        stripped = lines[idx].strip()
        if stripped == "---":
            break
        match = re.match(r"^\*\*(.+?):\*\*\s*(.*)$", stripped)
        if match:
            meta.append((match.group(1).strip(), match.group(2).strip()))
        idx += 1
    return title, meta


def parse_md_table(lines: list[str], styles: dict[str, ParagraphStyle]) -> Table | None:
    rows: list[list[str]] = []
    col_count = 0
    for line in lines:
        stripped = line.strip()
        if re.match(r"^[\|\s\-:]+$", stripped):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        col_count = max(col_count, len(cells))
        rows.append(cells)

    if not rows:
        return None

    normalized: list[list[str]] = []
    for row in rows:
        while len(row) < col_count:
            row.append("")
        normalized.append(row)

    usable = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN
    if col_count >= 5:
        first_col_w = usable * 0.30
        rest_col_w = (usable - first_col_w) / (col_count - 1)
        col_widths = [first_col_w] + [rest_col_w] * (col_count - 1)
    elif col_count == 4:
        first_col_w = usable * 0.28
        rest_col_w = (usable - first_col_w) / 3
        col_widths = [first_col_w] + [rest_col_w] * 3
    elif col_count == 3:
        first_col_w = usable * 0.32
        rest_col_w = (usable - first_col_w) / 2
        col_widths = [first_col_w] + [rest_col_w] * 2
    else:
        col_widths = [usable / col_count] * col_count

    data = []
    for row_index, row in enumerate(normalized):
        paragraph_row = []
        for cell in row:
            content = inline_pdf(cell)
            if row_index == 0:
                content = f"<b>{content}</b>"
            paragraph_row.append(Paragraph(content, styles["table_cell"]))
        data.append(paragraph_row)

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dce8f5")),
                ("TEXTCOLOR", (0, 0), (-1, 0), DARK_BLUE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
                ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def md_to_pdf_flowables(md_text: str, styles: dict[str, ParagraphStyle], base_dir: Path) -> list:
    lines = md_text.splitlines()
    story = []
    idx = 0
    in_abstract = False
    abstract_buf: list[str] = []
    header_done = False

    def flush_abstract() -> None:
        nonlocal in_abstract, abstract_buf
        if abstract_buf:
            story.append(Paragraph("Abstract", styles["abstract_heading"]))
            story.append(Paragraph(inline_pdf(" ".join(abstract_buf).strip()), styles["abstract_body"]))
            story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=8))
            abstract_buf = []
        in_abstract = False

    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()

        if stripped.startswith("# ") and not header_done:
            story.append(Spacer(1, 0.2 * inch))
            story.append(Paragraph(inline_pdf(stripped[2:].strip()), styles["paper_title"]))
            story.append(Spacer(1, 0.08 * inch))
            idx += 1
            while idx < len(lines) and lines[idx].strip() != "---":
                meta_line = lines[idx].strip()
                match = re.match(r"^\*\*(.+?):\*\*\s*(.*)$", meta_line)
                if match:
                    label = match.group(1).strip()
                    value = match.group(2).strip()
                    if label.lower() in {"authors", "author"}:
                        story.append(Paragraph(inline_pdf(value), styles["authors"]))
                    else:
                        story.append(Paragraph(inline_pdf(f"**{label}:** {value}"), styles["meta"]))
                idx += 1
            story.append(Spacer(1, 0.1 * inch))
            header_done = True
            continue

        if re.match(r"^-{3,}$", stripped):
            if in_abstract:
                flush_abstract()
            else:
                story.append(Spacer(1, 4))
                story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=4))
            idx += 1
            continue

        if re.match(r"^## Abstract$", stripped, re.IGNORECASE):
            in_abstract = True
            idx += 1
            continue

        if in_abstract:
            if stripped.startswith("## ") or stripped.startswith("# "):
                flush_abstract()
            elif stripped == "---":
                flush_abstract()
                idx += 1
                continue
            else:
                if stripped:
                    abstract_buf.append(stripped)
                idx += 1
                continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2)
            if level == 1:
                story.append(Paragraph(inline_pdf(text), styles["h1"]))
            elif level == 2:
                story.append(Paragraph(inline_pdf(text), styles["h2"]))
            else:
                story.append(Paragraph(inline_pdf(text), styles["h3"]))
            idx += 1
            continue

        image_match = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", stripped)
        if image_match:
            alt_text = image_match.group(1)
            image_path = base_dir / image_match.group(2)
            if image_path.exists():
                usable = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN
                story.append(Spacer(1, 12))
                story.append(Image(str(image_path), width=min(usable * 0.82, 5.5 * inch)))
                story.append(Paragraph(f"<i>{inline_pdf(alt_text)}</i>", styles["caption"]))
                story.append(Spacer(1, 12))
            idx += 1
            continue

        if stripped.startswith("```"):
            idx += 1
            code_lines = []
            while idx < len(lines) and not lines[idx].strip().startswith("```"):
                code_lines.append(lines[idx])
                idx += 1
            idx += 1
            usable = PAGE_W - LEFT_MARGIN - RIGHT_MARGIN
            code_block = Table(
                [[Preformatted("\n".join(code_lines), styles["code"])]],
                colWidths=[usable],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
                        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ]
                ),
            )
            story.append(Spacer(1, 4))
            story.append(code_block)
            story.append(Spacer(1, 8))
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines = []
            while idx < len(lines) and lines[idx].strip().startswith("|"):
                table_lines.append(lines[idx])
                idx += 1
            table = parse_md_table(table_lines, styles)
            if table:
                story.append(Spacer(1, 4))
                story.append(table)
                story.append(Spacer(1, 8))
            continue

        if stripped.startswith("> "):
            story.append(Paragraph(inline_pdf(stripped[2:].strip()), styles["blockquote"]))
            idx += 1
            continue

        if re.match(r"^[-*]\s+", stripped):
            while idx < len(lines) and re.match(r"^[-*]\s+", lines[idx].strip()):
                item = re.sub(r"^[-*]\s+", "", lines[idx].strip())
                story.append(Paragraph(f"• &nbsp;{inline_pdf(item)}", styles["bullet"]))
                idx += 1
            story.append(Spacer(1, 4))
            continue

        if re.match(r"^\d+\.\s+", stripped):
            number = 1
            while idx < len(lines) and re.match(r"^\d+\.\s+", lines[idx].strip()):
                item = re.sub(r"^\d+\.\s+", "", lines[idx].strip())
                story.append(Paragraph(f"{number}.&nbsp; {inline_pdf(item)}", styles["bullet"]))
                number += 1
                idx += 1
            story.append(Spacer(1, 4))
            continue

        if stripped == "":
            story.append(Spacer(1, 4))
            idx += 1
            continue

        paragraph_lines = [stripped]
        idx += 1
        while idx < len(lines):
            next_stripped = lines[idx].strip()
            if (
                next_stripped == ""
                or next_stripped.startswith("#")
                or next_stripped.startswith("|")
                or next_stripped.startswith("```")
                or next_stripped.startswith("> ")
                or re.match(r"^[-*]\s+", next_stripped)
                or re.match(r"^\d+\.\s+", next_stripped)
                or re.match(r"^-{3,}$", next_stripped)
            ):
                break
            paragraph_lines.append(next_stripped)
            idx += 1
        story.append(Paragraph(inline_pdf(" ".join(paragraph_lines)), styles["body"]))

    if in_abstract:
        flush_abstract()
    return story


def register_odt_styles(doc: OpenDocumentText) -> None:
    styles = [
        ("TitleStyle", {"fontsize": "18pt", "fontweight": "bold"}, {"textalign": "center", "marginbottom": "0.15in"}),
        ("MetaStyle", {"fontsize": "10pt", "fontstyle": "italic", "color": "#555555"}, {"textalign": "center", "marginbottom": "0.06in"}),
        ("BodyStyle", {"fontsize": "11pt"}, {"textalign": "justify", "marginbottom": "0.08in"}),
        ("CodeStyle", {"fontfamily": "Courier New", "fontsize": "9pt"}, {"backgroundcolor": "#f5f5f5", "padding": "0.06in", "marginbottom": "0.08in"}),
        ("QuoteStyle", {"fontsize": "11pt", "fontstyle": "italic"}, {"marginleft": "0.25in", "marginright": "0.25in", "marginbottom": "0.08in"}),
    ]
    for name, text_props, para_props in styles:
        style = Style(name=name, family="paragraph")
        style.addElement(TextProperties(**text_props))
        style.addElement(ParagraphProperties(**para_props))
        doc.styles.addElement(style)


def export_odt(input_path: Path, output_path: Path) -> None:
    md_text = input_path.read_text(encoding="utf-8")
    lines = md_text.splitlines()
    doc = OpenDocumentText()
    register_odt_styles(doc)

    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()

        if stripped == "---":
            idx += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            level = min(len(heading.group(1)), 6)
            text = plain_text(heading.group(2))
            if level == 1:
                doc.text.addElement(P(stylename="TitleStyle", text=text))
            else:
                doc.text.addElement(H(outlinelevel=level, text=text))
            idx += 1
            continue

        meta = re.match(r"^\*\*(.+?):\*\*\s*(.*)$", stripped)
        if meta:
            doc.text.addElement(P(stylename="MetaStyle", text=f"{meta.group(1)}: {plain_text(meta.group(2))}"))
            idx += 1
            continue

        if stripped.startswith("```"):
            idx += 1
            code_lines = []
            while idx < len(lines) and not lines[idx].strip().startswith("```"):
                code_lines.append(lines[idx])
                idx += 1
            doc.text.addElement(P(stylename="CodeStyle", text="\n".join(code_lines)))
            idx += 1
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines = []
            while idx < len(lines) and lines[idx].strip().startswith("|"):
                table_lines.append(plain_text(lines[idx].strip()))
                idx += 1
            for table_line in table_lines:
                doc.text.addElement(P(stylename="CodeStyle", text=table_line))
            continue

        if stripped.startswith("> "):
            doc.text.addElement(P(stylename="QuoteStyle", text=plain_text(stripped[2:].strip())))
            idx += 1
            continue

        if re.match(r"^[-*]\s+", stripped):
            lst = List()
            while idx < len(lines) and re.match(r"^[-*]\s+", lines[idx].strip()):
                item = re.sub(r"^[-*]\s+", "", lines[idx].strip())
                lst_item = ListItem()
                lst_item.addElement(P(stylename="BodyStyle", text=plain_text(item)))
                lst.addElement(lst_item)
                idx += 1
            doc.text.addElement(lst)
            continue

        if re.match(r"^\d+\.\s+", stripped):
            lst = List()
            while idx < len(lines) and re.match(r"^\d+\.\s+", lines[idx].strip()):
                item = re.sub(r"^\d+\.\s+", "", lines[idx].strip())
                lst_item = ListItem()
                lst_item.addElement(P(stylename="BodyStyle", text=plain_text(item)))
                lst.addElement(lst_item)
                idx += 1
            doc.text.addElement(lst)
            continue

        image_match = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", stripped)
        if image_match:
            caption = image_match.group(1) or image_match.group(2)
            doc.text.addElement(P(stylename="MetaStyle", text=f"Figure: {plain_text(caption)}"))
            idx += 1
            continue

        if stripped == "":
            idx += 1
            continue

        paragraph_lines = [stripped]
        idx += 1
        while idx < len(lines):
            next_stripped = lines[idx].strip()
            if (
                next_stripped == ""
                or next_stripped.startswith("#")
                or next_stripped.startswith("|")
                or next_stripped.startswith("```")
                or next_stripped.startswith("> ")
                or re.match(r"^[-*]\s+", next_stripped)
                or re.match(r"^\d+\.\s+", next_stripped)
                or re.match(r"^-{3,}$", next_stripped)
            ):
                break
            paragraph_lines.append(next_stripped)
            idx += 1
        doc.text.addElement(P(stylename="BodyStyle", text=plain_text(" ".join(paragraph_lines))))

    doc.save(str(output_path))


def make_page_decorators(running_head: str):
    def on_first_page(canvas, _doc):
        canvas.saveState()
        canvas.restoreState()

    def on_later_pages(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.drawString(LEFT_MARGIN, PAGE_H - 0.7 * inch, running_head[:90])
        canvas.drawRightString(PAGE_W - RIGHT_MARGIN, PAGE_H - 0.7 * inch, f"Page {doc.page}")
        canvas.restoreState()

    return on_first_page, on_later_pages


def export_pdf(input_path: Path, output_path: Path) -> None:
    md_text = input_path.read_text(encoding="utf-8")
    title, meta = parse_front_matter(md_text)
    styles = build_pdf_styles()
    story = md_to_pdf_flowables(md_text, styles, input_path.parent)
    on_first_page, on_later_pages = make_page_decorators(title)

    author = next((value for label, value in meta if label.lower() in {"author", "authors"}), "Hrishikesh Maluskar")

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title=title,
        author=author,
        subject="OctaMind research paper",
        keywords="OctaMind, research, LLM, FAISS, DAG, memory",
        creator="OctaMind Research",
    )
    doc.build(story, onFirstPage=on_first_page, onLaterPages=on_later_pages)


def export_paper(input_path: Path, pdf_enabled: bool, odt_enabled: bool, output_dir: Path) -> list[Path]:
    outputs: list[Path] = []
    stem = input_path.stem
    if pdf_enabled:
        pdf_path = output_dir / f"{stem}.pdf"
        export_pdf(input_path, pdf_path)
        outputs.append(pdf_path)
    if odt_enabled:
        odt_path = output_dir / f"{stem}.odt"
        export_odt(input_path, odt_path)
        outputs.append(odt_path)
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export research papers to PDF and ODT.")
    parser.add_argument("inputs", nargs="*", help="Markdown paper paths. Defaults to both research papers.")
    parser.add_argument("--pdf-only", action="store_true", help="Generate only PDF output.")
    parser.add_argument("--odt-only", action="store_true", help="Generate only ODT output.")
    parser.add_argument("--output-dir", default=str(SCRIPT_DIR), help="Directory for generated artifacts.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_paths = [Path(path).resolve() for path in args.inputs] if args.inputs else DEFAULT_INPUTS
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_enabled = not args.odt_only
    odt_enabled = not args.pdf_only

    all_outputs: list[Path] = []
    for input_path in input_paths:
        if not input_path.exists():
            raise FileNotFoundError(f"Input markdown not found: {input_path}")
        all_outputs.extend(export_paper(input_path, pdf_enabled, odt_enabled, output_dir))

    for output in all_outputs:
        print(output)


if __name__ == "__main__":
    main()