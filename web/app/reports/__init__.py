"""Reusable PDF report writer (Flask-side, unit-agnostic).

Two pieces:
  chart.py    -- renders the same chart_payload() dict app/chart.py already builds
                 for the on-screen SVG chart, as a static PNG for embedding.
  builder.py  -- assembles the PDF itself (header, input table, results table,
                 chart image) from plain label/value rows any calculator can supply.

See specs/SPEC-pdf-report.md.
"""
