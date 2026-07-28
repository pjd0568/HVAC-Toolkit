# Brand assets

Primary artwork is the attached hvac-calcs.app lockup (PNG). SVG drafts in
this folder are legacy and no longer referenced by the app.

## Files in use

| File | Use | Pixels |
|------|-----|--------|
| `home-hero.png` | Home page hero (below top nav, above headline) | 1024 × 282 |
| `lockup-tagline.png` | Marketing header lockup | 1024 × 190 |
| `logo-pdf.png` | PDF report header (same lockup) | 1024 × 190 |
| `icon.png` | Dashboard / app sidebar mark (graph only) | 512 × 512 |
| `favicon-32.png` | Browser favicon | 32 × 32 |
| `apple-touch-icon.png` | iOS / share icon | 180 × 180 |

Templates load via `brand_mark_url` / `brand_lockup_url` / `brand_hero_url`
(see `app/__init__.py`). Bump `BRAND_ASSET_VERSION` after replacing files.
Override the PDF logo:

```
REPORT_LOGO_PATH=/absolute/path/to/company-logo.png
```
