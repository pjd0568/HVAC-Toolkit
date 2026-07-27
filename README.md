# HVAC Toolkit / HVAC Calcs

Subscription HVAC engineering toolkit for engineers, designers and contractors.
SI + imperial. Brand via `BRAND_NAME` / `BRAND_TAG` (see `.env.example`).
Logo assets live in `web/app/static/images/brand/` (V2 mark); PDFs use
`logo-pdf.png` by default (`REPORT_LOGO_PATH` to override).

Public site: coming-soon marketing at `/`. Calculators at `/app` (login required).

## Structure

```
specs/      Functional specs per engine module — written from public standards
            (ASHRAE HOF, CIBSE guides) BEFORE implementation. The clean-room trail.
engine/     hvac_engine — standalone, pure-Python calculation package.
web/        Flask application (app factory + blueprints) consuming the engine.
```

## Local development

```bash
# Engine tests
cd engine && pip install -e ".[dev]" && pytest

# Web app (needs Postgres — easiest via Compose)
cp .env.example .env   # set SECRET_KEY at minimum
docker compose up --build

# Or run Flask against Compose Postgres only:
docker compose up -d db
cd web && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://app:app@127.0.0.1:5432/app
export SECRET_KEY=dev-only-change-me
flask --app wsgi db upgrade
flask --app wsgi run --debug
```

Open `http://127.0.0.1:5000/` (coming soon), register at `/register`, then use `/app`.

## Deploy on Railway

1. Create a Railway project and link this GitHub repo at the **repository root**
   (not `web/`). Builder uses Docker via [`railway.toml`](railway.toml) →
   [`web/Dockerfile`](web/Dockerfile).
2. Add the **Postgres** plugin; Railway injects `DATABASE_URL`.
3. Set variables: `SECRET_KEY` (long random), `BRAND_NAME` (e.g. `HVAC Calcs`),
   optional `BRAND_TAG`. Leave `REGISTRATION_OPEN` unset or `false` until launch
   (existing accounts can still log in; `/register` stays closed). Optional:
   `CONTACT_EMAIL`, `LEGAL_ENTITY`, and `MAIL_*` SMTP vars so `/contact` sends
   mail server-side (otherwise it opens a mailto draft).
4. Deploy. Release command runs `flask --app wsgi db upgrade`. Health check:
   `GET /health`.
5. Custom domain: Railway → Domains → `hvac-calcs.app`. Copy the CNAME/ALIAS
   into Cloudflare DNS. SSL mode on Cloudflare: **Full (strict)** once Railway
   has issued its certificate.
6. After go-live, submit `https://hvac-calcs.app/sitemap.xml` in Google Search Console.

If the build fails, confirm the service root is the monorepo root and the
Dockerfile path is `web/Dockerfile`. Gunicorn binds `$PORT` automatically.

## Cloudflare + domain

- Domain: `hvac-calcs.app` (product).
- Parent email/company: Google Workspace on `pjd-it-systems.com` (separate).
- Point the apex (and `www` if used) at Railway’s target; keep proxy on if you
  want Cloudflare CDN/WAF in front.

## Auth & billing (current)

- Email/password accounts in Postgres (`specs/SPEC-auth.md`).
- 14-day free trial starts on register; full suite then £9.50/month
  (`specs/SPEC-access.md`). Weather and Projects are Coming Soon.
- Stripe Managed Payments Checkout + webhooks (`specs/SPEC-billing-stripe.md`).
  Set keys in Railway from the Stripe Dashboard.
- Transactional SMTP from `info@hvac-calcs.app` (`specs/SPEC-transactional-email.md`)
  — trial welcome, subscribe thanks, cancellation.

## Provenance

All calculation methods are implemented from the functional specs in `specs/`,
which cite public engineering standards (ASHRAE Handbook — Fundamentals, CIBSE
Guides, NIST SP 811). Developed on personal equipment in personal time.
