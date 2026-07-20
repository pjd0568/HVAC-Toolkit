"""Reusable PDF report assembly: header, input table, results table, chart image.

Deliberately unit-agnostic and hvac_engine-agnostic: callers (blueprints) format
every value through the active UnitView before handing rows here, so this module
works for any future calculator, not just the psychrometric tools. See
specs/SPEC-pdf-report.md for the full contract and rationale.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Palette matched to app/static/css/app.css :root, so the PDF reads as the same
# product as the web app.
_INK = colors.HexColor("#16202E")
_MUTED = colors.HexColor("#697687")
_LINE = colors.HexColor("#E1E7F0")
_BLUE_SOFT = colors.HexColor("#E9F1FA")

_PAGE_MARGIN = 16 * mm
_CONTENT_WIDTH = A4[0] - 2 * _PAGE_MARGIN


@dataclass
class ReportMeta:
    """Everything the header needs. Project/System/Revision/Author are plain
    free-text today (no auth or project database yet -- see SPEC-pdf-report.md);
    `report_date` defaults to today if not given.
    """

    brand_name: str
    tool_title: str
    project: str = ""
    system: str = ""
    revision: str = ""
    author: str = ""
    report_date: date = field(default_factory=date.today)
    logo_path: str = ""


def _styles() -> dict:
    ss = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle("Brand", parent=ss["Normal"], textColor=_MUTED, fontSize=9),
        "title": ParagraphStyle("ReportTitle", parent=ss["Heading1"], textColor=_INK,
                                 fontSize=16, spaceBefore=2, spaceAfter=0),
        "meta_label": ParagraphStyle("MetaLabel", parent=ss["Normal"], textColor=_MUTED,
                                      fontSize=8, alignment=TA_RIGHT),
        "meta_value": ParagraphStyle("MetaValue", parent=ss["Normal"], textColor=_INK,
                                      fontSize=9, alignment=TA_RIGHT),
        "section": ParagraphStyle("Section", parent=ss["Heading2"], textColor=_INK,
                                   fontSize=12, spaceBefore=14, spaceAfter=6),
    }


def _header(meta: ReportMeta, styles: dict) -> Table:
    left: list = []
    if meta.logo_path:
        try:
            left.append(Image(meta.logo_path, width=28 * mm, height=28 * mm, kind="proportional"))
        except Exception:
            pass  # missing/unreadable logo -- fall back to text-only header
    left.append(Paragraph(meta.brand_name, styles["brand"]))
    left.append(Paragraph(meta.tool_title, styles["title"]))

    meta_rows = [
        ("Project", meta.project or "—"),
        ("System", meta.system or "—"),
        ("Date", meta.report_date.strftime("%d %b %Y")),
        ("Revision", meta.revision or "—"),
        ("Author", meta.author or "—"),
    ]
    right = Table(
        [[Paragraph(f"{k}:", styles["meta_label"]), Paragraph(v, styles["meta_value"])]
         for k, v in meta_rows],
        colWidths=[22 * mm, 40 * mm],
    )
    right.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    header = Table([[left, right]], colWidths=[_CONTENT_WIDTH - 62 * mm, 62 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return header


def _data_table(rows: list[tuple[str, str, str]]) -> Table:
    """rows: (label, value, unit). Value and unit are separate table columns --
    value right-aligned, unit left-aligned in its own narrow column with a
    small gutter -- so every row's unit lines up in one vertical column and
    sits a consistent, deliberate gap from its number, the same pairing the
    on-screen results table gets from `.valunit` (see app/units.py, app.css).
    `unit` is "" for rows that don't carry one (ratios, free-text messages).
    """
    data = [["Property", "Value", ""]] + [[label, value, unit] for label, value, unit in rows]
    t = Table(data, colWidths=[_CONTENT_WIDTH * 0.52, _CONTENT_WIDTH * 0.30, _CONTENT_WIDTH * 0.18])
    t.setStyle(TableStyle([
        ("SPAN", (1, 0), (2, 0)),  # single "Value" header spans the value+unit columns
        ("BACKGROUND", (0, 0), (-1, 0), _BLUE_SOFT),
        ("TEXTCOLOR", (0, 0), (-1, -1), _INK),
        ("TEXTCOLOR", (2, 1), (2, -1), _MUTED),  # unit column reads muted, like .valunit .u
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTSIZE", (2, 1), (2, -1), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, _LINE),
        ("LINEBELOW", (0, 1), (-1, -2), 0.5, _LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("ALIGN", (2, 1), (2, -1), "LEFT"),
        ("LEFTPADDING", (2, 1), (2, -1), 4),
    ]))
    return t


def _item_table(
    headers: list[str],
    rows: list[list[str]],
    col_widths_mm: list | None = None,
    footer_rows: int = 0,
) -> Table:
    """Generic multi-column data table -- distinct from `_data_table`'s fixed
    label/value/unit shape. For a tool whose report needs an arbitrary number
    of columns of already-formatted strings (e.g. Duct Sizing's Index Leg,
    one row per pressure-drop item) rather than a flat property list. Same
    header/line/palette treatment as `_data_table` so every table in every
    PDF this app produces reads as one consistent design language, not a
    one-off style per tool.

    `col_widths_mm`: optional list of column widths in millimetres -- must
    have the same length as `headers`. If omitted or mismatched, columns are
    divided equally across the content width. Allows callers to assign
    proportional widths to mixed-importance columns (e.g. a narrow "#" column
    alongside a wide "Item" column) rather than every column getting the same
    fraction of the page.

    `footer_rows`: number of trailing rows that are summary/total rows (e.g.
    TOTAL, +N% margin, TOTAL WITH MARGIN for the Index Leg). Each footer row
    has its first n-1 cells merged into one right-aligned label cell and the
    last cell as the value -- so even long labels like "TOTAL WITH MARGIN"
    never overflow into the value cell. All footer rows are bolded; a heavier
    rule is drawn above the first one. When 0 (the default) the original
    "bold/rule last row" behaviour applies so existing callers are unaffected.
    """
    data = [headers] + rows
    n = len(headers)
    total_rows = len(data)

    if col_widths_mm and len(col_widths_mm) == n:
        col_widths = [w * mm for w in col_widths_mm]
    else:
        col_width = _CONTENT_WIDTH / n
        col_widths = [col_width] * n

    t = Table(data, colWidths=col_widths, repeatRows=1)

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), _BLUE_SOFT),
        ("TEXTCOLOR", (0, 0), (-1, -1), _INK),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, _LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (0, 1), (-1, -1), "CENTER"),
    ]

    if footer_rows > 0 and total_rows > 1:
        first_footer = total_rows - footer_rows  # 0-based index into `data`
        # Thin underlines for data rows only (not footer rows)
        if first_footer > 1:
            style_cmds.append(("LINEBELOW", (0, 1), (-1, first_footer - 1), 0.5, _LINE))
        # Heavy rule above the first footer row
        style_cmds.append(("LINEABOVE", (0, first_footer), (-1, first_footer), 1.0, _LINE))
        # Bold all footer rows
        style_cmds.append(("FONTNAME", (0, first_footer), (-1, total_rows - 1), "Helvetica-Bold"))
        # Merge cols 0..n-2 into a single label cell per footer row, right-aligned --
        # this is what prevents "TOTAL WITH MARGIN" from bleeding into the value cell.
        for r in range(first_footer, total_rows):
            style_cmds.append(("SPAN", (0, r), (n - 2, r)))
            style_cmds.append(("ALIGN", (0, r), (0, r), "RIGHT"))
        # Right-align the value (last column) in every footer row
        style_cmds.append(("ALIGN", (n - 1, first_footer), (n - 1, total_rows - 1), "RIGHT"))
    else:
        # Original behaviour: thin underlines, bold + rule on last row only
        style_cmds.append(("LINEBELOW", (0, 1), (-1, -2), 0.5, _LINE))
        style_cmds.append(("LINEABOVE", (0, -1), (-1, -1), 1.0, _LINE))
        style_cmds.append(("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"))

    t.setStyle(TableStyle(style_cmds))
    return t


def _footer(canvas, doc, meta: ReportMeta) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(_MUTED)
    canvas.drawString(_PAGE_MARGIN, 10 * mm,
                       f"{meta.brand_name} — generated {meta.report_date.strftime('%d %b %Y')}")
    canvas.drawRightString(A4[0] - _PAGE_MARGIN, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf(
    meta: ReportMeta,
    input_rows: list[tuple[str, str, str]] | None = None,
    result_rows: list[tuple[str, str, str]] | None = None,
    chart_png: bytes | None = None,
    chart_title: str = "Psychrometric Chart",
    chart_aspect: float = 4.4 / 7.2,
    extra_tables: list[tuple] | None = None,
) -> bytes:
    """Assemble the PDF and return its bytes. See SPEC-pdf-report.md for the contract.

    `input_rows` / `result_rows`: if None or empty, the corresponding section is
    omitted from the output entirely -- allows a leg-table-first report that
    skips the 3-column sizer values while reusing the same header/footer/palette.

    `chart_png` is deliberately generic despite the name/default -- any tool can
    hand this an image to embed as the report's closing figure. `chart_title` and
    `chart_aspect` (height/width) let a caller repurpose the same slot for a
    different image (e.g. the Weather tool's static site-location map) without
    the section heading or proportions being wrong for that image. Existing
    callers that only pass `chart_png` keep the original psychrometric-chart
    heading and aspect ratio unchanged.

    `extra_tables`: a list of tuples `(section_title, headers, rows[, col_widths_mm])`.
    Rendered after any Inputs/Results and before the chart, via `_item_table()`.
    The optional 4th element `col_widths_mm` is a list of per-column widths in mm
    passed straight to `_item_table(col_widths_mm=...)` -- useful for tables with
    many columns of unequal importance (e.g. Duct Sizing's Index Leg). Existing
    3-tuple callers are unaffected. Omitted entirely if empty/None.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=_PAGE_MARGIN, bottomMargin=_PAGE_MARGIN,
        leftMargin=_PAGE_MARGIN, rightMargin=_PAGE_MARGIN,
        title=f"{meta.tool_title} — {meta.project or meta.brand_name}",
    )
    styles = _styles()
    story = [
        _header(meta, styles),
        Spacer(1, 6 * mm),
        HRFlowable(width="100%", color=_LINE, thickness=1),
        Spacer(1, 2 * mm),
    ]

    if input_rows:
        story.append(Paragraph("Inputs", styles["section"]))
        story.append(_data_table(input_rows))
    if result_rows:
        story.append(Paragraph("Results", styles["section"]))
        story.append(_data_table(result_rows))

    for item in (extra_tables or []):
        title, headers, rows = item[0], item[1], item[2]
        cwmm = item[3] if len(item) > 3 else None
        ftrows = item[4] if len(item) > 4 else 0
        story.append(Paragraph(title, styles["section"]))
        story.append(_item_table(headers, rows, col_widths_mm=cwmm, footer_rows=ftrows))

    if chart_png:
        chart_width = _CONTENT_WIDTH
        chart_height = chart_width * chart_aspect
        story.append(KeepTogether([
            Paragraph(chart_title, styles["section"]),
            Image(io.BytesIO(chart_png), width=chart_width, height=chart_height),
        ]))

    def _on_page(canvas, doc_):
        _footer(canvas, doc_, meta)

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buf.getvalue()
