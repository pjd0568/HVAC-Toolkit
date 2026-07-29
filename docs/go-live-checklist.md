# Go-live checklist — dogfood, then soft launch

Operator checklist for drawing the line before public self-serve.
Keep `REGISTRATION_OPEN=false` except when creating an invite or your dogfood account.

**Deferred until after soft launch (do not build now):** Weather in-app data,
Projects persistence, Customer Portal UI, password reset / email verify,
account self-delete, Sentry, annual plans / tiers, marketing home redesign.

---

## A. Production mail & Stripe cutover

Do this before a live (£) self-subscribe.

### Mail (Resend)

- [ ] Resend: domain `hvac-calcs.app` **Verified** (SPF/DKIM in Cloudflare)
- [ ] Railway: `RESEND_API_KEY`, `MAIL_DEFAULT_SENDER=info@hvac-calcs.app`, `CONTACT_EMAIL`
- [ ] `GET /health` shows a mail backend (not unset)
- [ ] Send a real message via `/contact` → lands in the inbox you monitor
- [ ] (After a test register) trial welcome email arrives

See `specs/SPEC-transactional-email.md`.

### Stripe Test mode (local or prod webhook)

- [ ] Test API keys in env: `STRIPE_SECRET_KEY=sk_test_…`, `STRIPE_PRICE_ID`
- [ ] Managed Payments terms accepted (Test Dashboard)
- [ ] Product/price: `flask --app wsgi ensure-stripe-product` (or Dashboard tax code `txcd_10103100`)
- [ ] Webhook events: `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `customer.subscription.updated`, `customer.subscription.deleted`
  - Local: `stripe listen --forward-to localhost:5000/webhooks/stripe` → `STRIPE_WEBHOOK_SECRET`
  - Prod test: Dashboard endpoint `https://hvac-calcs.app/webhooks/stripe` with test signing secret
- [ ] Pricing page CTA is **Subscribe**, not “Checkout coming soon”

### Stripe Live mode (only after Test walkthrough passes)

- [ ] Live Managed Payments terms accepted
- [ ] Railway: live `sk_live_…`, live `STRIPE_PRICE_ID`, live webhook `whsec_…` (replace test secrets)
- [ ] Live webhook endpoint on the same URL, Live mode, same four event types
- [ ] Confirm CTA still works with live keys

---

## B. Dogfood walkthrough (you as the only customer)

Use a work email you actually read. Prefer production once mail + webhooks are wired; otherwise local + `stripe listen`.

### B1 — Stripe Test

- [ ] Briefly set `REGISTRATION_OPEN=true`
- [ ] Register with work email → trial welcome email
- [ ] Set `REGISTRATION_OPEN=false` again immediately
- [ ] Use 1–2 calculators under trial
- [ ] Checkout with `4242 4242 4242 4242` → success flash, suite stays unlocked, thanks email
- [ ] Confirm Stripe Dashboard shows the test subscription
- [ ] Cancel via Stripe / Link (receipt email links) — **not** an in-app button
- [ ] App locks suite after webhook; cancellation email arrives
- [ ] Submit `/contact` with topic **Billing** to yourself
- [ ] Skim Help → **Account, billing & cancel** — note any confusing steps

### B2 — One live self-subscribe then cancel

Only after B1 is clean:

- [ ] Live keys on Railway (section A)
- [ ] Subscribe with a real card → £9.50 charged → active + receipt
- [ ] Cancel immediately via Stripe / Link → suite locks + emails
- [ ] Optional: refund from Stripe Dashboard; confirm it matches Terms wording

Friction list (fill in while dogfooding):

1. …
2. …

Fix **copy or process** only for items that confused you; do not add Portal / new calculators yet.

---

## C. Soft invite cohort (3–5 people)

Still closed to the public.

- [ ] Keep `REGISTRATION_OPEN=false` by default
- [ ] For each invitee: open registration briefly **or** create account yourself and share credentials once
- [ ] Tell them: trial → Pricing to pay; cancel via Stripe/Link; Billing questions → Contact
- [ ] Point them at Help → Account, billing & cancel
- [ ] Support playbook (you, manually):
  - **Password lost:** reset hash in DB / Werkzeug (no self-serve reset yet) or create a new account
  - **Cancel / refund:** Stripe Dashboard → Customers / Subscriptions
  - **Access wrong:** check `subscription_status`, webhook deliveries, Railway logs
- [ ] Log friction from invitees for 1–2 weeks
- [ ] Only then consider `REGISTRATION_OPEN=true` for public self-serve

---

## D. After go-live hygiene

- [ ] Submit `https://hvac-calcs.app/sitemap.xml` in Google Search Console
- [ ] Watch Railway logs + Stripe Dashboard for webhook failures for the first cohort
