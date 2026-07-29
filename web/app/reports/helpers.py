"""Shared PDF-report request helpers, used by every blueprint that offers a
"Download PDF Report" button (see templates/_report_form.html).

Pulled out of blueprints/psychro.py (which originally defined its own copies)
so every tool's report metadata (brand/logo/Project/System/Revision/Author)
and PDF response headers are built exactly the same way -- one place to keep
every PDF reading as the same product, not one copy per blueprint that could
quietly drift apart. See specs/SPEC-pdf-report.md.
"""

from __future__ import annotations

import re

from flask import Response, current_app, request

from app.reports.builder import ReportMeta


def report_meta_from_form(tool_title: str) -> ReportMeta:
    """Project/System/Revision/Author are plain free-text fields typed at download
    time -- there's no auth or project database yet (see SPEC-pdf-report.md)."""
    return ReportMeta(
        brand_name=current_app.config["BRAND_NAME"],
        tool_title=tool_title,
        project=request.form.get("report_project", "").strip(),
        system=request.form.get("report_system", "").strip(),
        revision=request.form.get("report_revision", "").strip(),
        author=request.form.get("report_author", "").strip(),
        logo_path=current_app.config.get("REPORT_LOGO_PATH", "") or "",
    )


def _filename_part(text: str) -> str:
    """One path-safe segment for a download filename (no spaces / reserved chars)."""
    text = (text or "").strip()
    if not text:
        return ""
    text = re.sub(r"[^\w.\-]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip(".-")
    return text[:80]


def pdf_filename(meta: ReportMeta, fallback: str = "report") -> str:
    """Build ``Project-System-Revision-YYYY-MM-DD.pdf`` from report fields.

    Empty project/system/revision parts are skipped. If none of those were
    entered, falls back to ``{fallback}-{date}.pdf`` so the download still has
    a useful name.
    """
    parts = [
        _filename_part(meta.project),
        _filename_part(meta.system),
        _filename_part(meta.revision),
    ]
    parts = [p for p in parts if p]
    date_s = meta.report_date.strftime("%Y-%m-%d")
    if parts:
        stem = "-".join([*parts, date_s])
    else:
        stem = f"{_filename_part(fallback) or 'report'}-{date_s}"
    return f"{stem}.pdf"


def pdf_response(
    pdf_bytes: bytes,
    filename: str | None = None,
    *,
    meta: ReportMeta | None = None,
    fallback: str = "report",
) -> Response:
    """Return a PDF download. Prefer ``meta=`` so the filename uses project fields."""
    if meta is not None:
        filename = pdf_filename(meta, fallback)
    if not filename:
        filename = f"{_filename_part(fallback) or 'report'}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
