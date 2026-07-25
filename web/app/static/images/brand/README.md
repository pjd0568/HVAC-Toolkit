# Brand assets (V2)

Hand-built SVG mark + lockups from the CoPilot proof board, plus PNG
exports for favicons and PDF headers (ReportLab does not embed SVG).

## Files

| File | Use |
|------|-----|
| `icon.svg` | UI mark (sidebar, marketing header) — transparent |
| `icon-dark.svg` | Same mark on dark backgrounds |
| `app-icon.svg` / `app-icon-dark.svg` | Rounded-square app icon |
| `lockup.svg` / `lockup-dark.svg` | Icon + wordmark (optional drop-in) |
| `lockup-tagline.svg` | Icon + wordmark + tagline (login / coming-soon hero) |
| `logo-pdf.png` | PDF report header (default `REPORT_LOGO_PATH`) — 400×400 |
| `favicon-32.png` | Browser favicon |
| `apple-touch-icon.png` | 180×180 iOS home screen |
| `app-icon-512.png` | PWA / high-res app icon |
| `app-icon-dark-512.png` | Dark tile variant |

SVG used in `<img>` must be clean XML (ASCII comments only). A stray
control character in a comment returns HTTP 200 but shows a broken-image
icon in the browser.

## Regenerating PNGs

```bash
web/.venv/bin/python web/app/static/images/brand/render_pngs.py
```

## Drop-in replacements

Templates load via `brand_mark_url` / `brand_lockup_url` / `brand_favicon_url`
(see `app/__init__.py`). To swap a file, replace the asset in this folder —
no template edit needed. Bump `BRAND_ASSET_VERSION` (or set it in env) after
replacing files so Cloudflare/browser caches refresh. Override the PDF logo:

```
REPORT_LOGO_PATH=/absolute/path/to/company-logo.png
```

User company logos (future) should also be PNG/JPEG and will override
the product logo on PDF headers only.
