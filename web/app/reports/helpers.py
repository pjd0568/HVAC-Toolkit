"""Shared PDF-report request helpers, used by every blueprint that offers a
"Download PDF Report" button (see templates/_report_form.html).

Pulled out of blueprints/psychro.py (which originally defined its own copies)
so every tool's report metadata (brand/logo/Project/System/Revision/Author)
and PDF response headers are built exactly the same way -- one place to keep
every PDF reading as the same product, not one copy per blueprint that could
quietly drift apart. See specs/SPEC-pdf-report.md.
"""

from __future__ import annotations

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


def pdf_response(pdf_bytes: bytes, filename: str) -> Response:
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
