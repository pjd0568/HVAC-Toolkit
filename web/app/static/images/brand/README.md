# Brand assets

Primary artwork is the attached hvac-calcs.app lockup (PNG). SVG drafts in
this folder are legacy sketches; regenerable raster icons come from
`render_pngs.py` (matches `app-icon.svg` geometry).

## Files in use

| File | Use | Pixels |
|------|-----|--------|
| `home-hero.png` | Home page hero (below top nav, above headline) | 1024 × 282 |
| `lockup-tagline.png` | Marketing header lockup | 1024 × 190 |
| `logo-pdf.png` | PDF report header (same lockup) | 1024 × 190 |
| `icon.png` | Dashboard / app sidebar mark (graph only) | 512 × 512 |
| `favicon-32.png` | Browser favicon | 32 × 32 |
| `apple-touch-icon.png` | iOS / share icon | 180 × 180 |
| `app-icon-192.png` / `app-icon-512.png` | PWA `purpose: any` | 192 / 512 |
| `app-icon-maskable-192.png` / `app-icon-maskable-512.png` | PWA `purpose: maskable` (Android adaptive; mark inset in safe zone) | 192 / 512 |

Regenerate favicons + PWA icons:

```
python3 web/app/static/images/brand/render_pngs.py
```

Templates load via `brand_mark_url` / `brand_lockup_url` / `brand_hero_url`
(see `app/__init__.py`). Bump `BRAND_ASSET_VERSION` after replacing files.
Override the PDF logo:

```
REPORT_LOGO_PATH=/absolute/path/to/company-logo.png
```
