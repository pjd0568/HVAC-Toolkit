# HVAC-CALCS relaunch — baseline (Phase 0)

Recorded 13 October 2026 on branch `main` (`bc94f45`) before relaunch edits.
No calculation code was changed for this snapshot.

## Tests before edits

| Suite | Result |
| --- | --- |
| `engine` pytest | 389 passed, 1 skipped |
| `web` pytest | 43 passed |

## What production actually runs

- Railway service **Pauls Hvac App** is online at `https://hvac-calcs.app` (project `wonderful-intuition`, production).
- Repository docs and `origin/Publish` are the deploy line. `main` is **not** what Railway publishes.
- `origin/Publish` is `179e7e7` (“Offer trial and subscribe actions on the pricing page”).
- Live `/subscribe` shows **£4.50/month** and a **Start free trial** link to `/register`.
- `GET /register` returns **200** (no redirect to home), so production `REGISTRATION_OPEN` is on.
- `GET /health` returns `{"status":"ok","mail_backend":"resend"}`.
- This session did not read Railway variable values. The live charge shown to visitors is £4.50/month. Stripe Price ID remains an environment setting; do not assume a new Checkout price was created.

## Branch divergence (do not lose this)

`main` is ahead of `Publish` with diagnostics, compact forms, and pipe Pa/kPa work.
`Publish` is ahead of `main` with the £4.50 price, contact-form limits, and the pricing-page trial/subscribe actions.

Refrigeration on **Publish** (production): PT table and DX pipe sizer are suite modules. Superheat/subcooling is still `COMING_SOON`. Charge calculator is coming soon.

Refrigeration on **main**: superheat/subcooling is an implemented suite tool (engine, tests, V2 page). It is **not** on the production branch until `main` is published.

## Price and copy on `main` before this relaunch

`PRICE_MONTHLY_GBP` on `main` was still `"9.50"` with Stripe unit amount 950 pence. Templates hard-coded £9.50 in several places. Production already displays £4.50 from `Publish`.

Public nav label was **Pricing/Subscribe**. Checkout-not-configured copy named `STRIPE_SECRET_KEY` on the pricing page and in a flash message.

## Access before edits

Anonymous visitors could use the homepage psychrometric teaser only. Suite routes redirected to login, then required a trial or subscription. PDF/CSV/chart export used the same module gate as the calculator page.
