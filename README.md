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

## Local then Railway

| Branch | Role |
|--------|------|
| **`main`** (Main) | Day-to-day development and local testing |
| **`Publish`** | Production — Railway deploys `hvac-calcs.app` from this branch only |

Work and commit on **`main`**. When a change is ready for the live site, push it
to **`Publish`**. Railway does **not** deploy from `main`.

1. **Stay on `main`** (or branch from it: `feat/weather`, `feat/projects`, …).
2. **Run locally** (below). Use `ACCESS_DEV_TIER=pro` in `.env` so the suite is
   unlocked without Stripe. Optional: `REGISTRATION_OPEN=true` so you can
   create a local account; or open `/login?preview=1` when `ACCESS_DEV_TIER` is
   set (logs in `preview@example.com`).
3. **Test** — engine `pytest`, then click through the tool at
   `http://127.0.0.1:5000/app`.
4. **Publish when ready** — update the deploy branch and push:

   ```bash
   git checkout main
   git push origin main          # backup / share work on GitHub
   git push origin main:Publish  # deploy: copies main → Publish on GitHub
   ```

   Railway builds from the repo root (`railway.toml` → `web/Dockerfile`) and
   runs `flask --app wsgi db upgrade`.

Do not put `ACCESS_DEV_TIER` or `REGISTRATION_OPEN=true` on Railway unless you
mean it. Production secrets stay in the Railway dashboard, not in git.

> **Branch name note:** Git’s development branch is `main` (lowercase). macOS
> treats `Main` and `main` as the same name, so we keep the standard `main`
> spelling for the local/Main line of work.

## Local development

```bash
# Engine tests
cd engine && pip install -e ".[dev]" && pytest

# Web app (needs Postgres — easiest via Compose)
cp .env.example .env   # set SECRET_KEY; add ACCESS_DEV_TIER=pro for local suite access
docker compose up --build

# Or run Flask against Compose Postgres only:
docker compose up -d db
cd web && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://app:app@127.0.0.1:5432/app
export SECRET_KEY=dev-only-change-me
export ACCESS_DEV_TIER=pro
flask --app wsgi db upgrade
flask --app wsgi run --debug
```

Open `http://127.0.0.1:5000/` (coming soon), then `/app` after login.

## Deploy on Railway

Railway is linked to this GitHub repo and watches **`Publish`** only. A push to
`Publish` (see `git push origin main:Publish` above) is the publish step.

1. Service root = **repository root** (not `web/`). Builder: [`railway.toml`](railway.toml)
   → [`web/Dockerfile`](web/Dockerfile).
2. Postgres plugin injects `DATABASE_URL`.
3. Production variables live in Railway only: `SECRET_KEY`, Stripe, Resend, etc.
   Leave `REGISTRATION_OPEN` unset/`false` unless you are opening public trials.
4. Health check: `GET /health`. Custom domain: `hvac-calcs.app` (Cloudflare
   SSL **Full (strict)**).
5. After go-live, submit `https://hvac-calcs.app/sitemap.xml` in Google Search Console.

If the build fails, confirm the service root is the monorepo root and the
Dockerfile path is `web/Dockerfile`. Gunicorn binds `$PORT` automatically.

To re-point the Railway service at `Publish` (e.g. after reconnecting GitHub):

```bash
railway service source connect --repo pjd0568/HVAC-Toolkit --branch Publish --service "Pauls Hvac App"
```

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
  Set keys in Railway from the Stripe Dashboard. Cancel / invoices via Stripe /
  Link (documented under Help → Account, billing & cancel).
- Open registration: add Cloudflare Turnstile keys (`TURNSTILE_SITE_KEY` /
  `TURNSTILE_SECRET_KEY`) so `/register` is bot-checked (`specs/SPEC-auth.md`).
- Transactional email via **Resend** (preferred on Railway) or SMTP fallback
  (`specs/SPEC-transactional-email.md`) — trial welcome, subscribe thanks,
  cancellation. Gmail SMTP from Railway is unreliable.

## Go-live (draw the line)

Operator checklist: [`docs/go-live-checklist.md`](docs/go-live-checklist.md) —
dogfood yourself (Stripe test, then one live pay-and-cancel), then a small invite
cohort. Keep `REGISTRATION_OPEN=false` until you intentionally open trials.

**Parked until after soft launch:** Customer Portal, password reset, Sentry,
Weather/Projects product work, public marketing redesign.

## Provenance

All calculation methods are implemented from the functional specs in `specs/`,
which cite public engineering standards (ASHRAE Handbook — Fundamentals, CIBSE
Guides, NIST SP 811). Developed on personal equipment in personal time.
