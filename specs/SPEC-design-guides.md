# Functional Spec — Design Guides (Reference)

**Module:** `web` content — Reference / Design Guides
**Status:** v1.0 — 3 July 2026
**Clean-room note:** This spec and the article content behind it are written fresh from
public engineering standards, with the frozen prototype (`archive/Consumer HVAC App/`)
closed throughout. That prototype has its own "Knowledge Base" article covering the same
subject (cooling coil design), so the note is explicit: no text, structure or diagram was
copied or paraphrased from it. Only the choice of *topic* (coil design deserves an
explainer alongside the Cooling Coil / AHU Design tools) carried across — the topic
itself is standard HVAC scope, not proprietary. See CLAUDE.md, "IP separation rules".

## Purpose

A small library of reference articles, distinct from the calculators, that explain the
engineering behind a tool well enough that a user can sanity-check a result or make a
selection decision the calculator itself doesn't automate (coil rows, face velocity,
condensate drainage, etc.). First article: cooling coil design and the psychrometric
cooling process, cross-linked from the Cooling Coil and AHU Design tools.

## Method sources (public standards)

- ASHRAE Handbook — Fundamentals (2017), Chapter 1 "Psychrometrics" (sensible/latent
  split, enthalpy) and Chapter 23 "Air-Cooling and Dehumidifying Coils" (apparatus dew
  point, contact factor / bypass factor, face velocity and condensate carryover
  guidance).
- CIBSE Guide B (Heating, Ventilating, Air Conditioning and Refrigeration), section on
  cooling coil selection — face velocity, row/fin trade-offs, frost and reheat practice
  (UK-context corroboration of the ASHRAE figures).

## Content structure

- `web/app/blueprints/guides.py` — a small article registry (slug, title, summary,
  template path), same shape as a normal Flask blueprint; no persistence, content is
  static Jinja fragments under `templates/guides/`.
- `GET /reference` — index/listing page (`guides.html`), one card per article.
- `GET /reference/<slug>` — article page (`guide_article.html` wraps the body fragment).
- Article bodies are self-contained HTML fragments (prose + inline SVG diagrams, no
  external image files) styled with new `.article/.formula/.fig/.callout` classes added
  to `app.css` — presentational patterns only (box with a border, monospace formula
  line, figure + caption), not content, so no IP concern in reusing generic patterns
  like these across any web app.

## Not yet

- No search/tagging across articles (one article for now).
- No "read time" or authorship metadata.
- Future articles (duct sizing practice, pipe sizing/pump curves, psychrometrics
  primer) should follow the same spec-first, clean-room method: write what the article
  needs to cover and its public-standard sources here (or a new SPEC-*.md) before
  drafting the body.
