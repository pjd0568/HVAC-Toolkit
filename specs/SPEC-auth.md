# Functional Spec — Authentication & accounts

**Module:** `web/app/models/user.py`, `web/app/blueprints/auth.py`, login gate
**Status:** v0.1 — accounts scaffold (pre-Stripe)
**Clean-room note:** Product accounts only. No reference to employer tooling.

## Purpose

Durable user identity so trial clocks and (later) Stripe subscriptions bind to a
person, not a browser cookie. Gate the calculator shell behind login while the
public marketing / coming-soon / pricing pages stay open.

## Public vs gated

| Path | Auth |
|------|------|
| `/`, `/login`, `/subscribe`, `/webhooks/stripe`, `/health`, static | Public |
| `/register` | Public only when `REGISTRATION_OPEN=true` (default **closed**) |
| `/app` and all calculator / reference / help routes | Login required |

Anonymous hits on gated routes redirect to `/login?next=…`. Existing accounts
can always log in; new self-serve signups are blocked until registration is
opened for launch.

## User record

| Field | Notes |
|-------|-------|
| `email` | Unique, normalised lowercase |
| `password_hash` | Werkzeug hash; never store plaintext |
| `trial_started_at` | Date; set on register |
| `subscription_status` | `none` \| `trialing` \| `active` \| `canceled` |
| `stripe_customer_id` | Stripe Customer id (`cus_…`); set at Checkout |
| `stripe_subscription_id` | Stripe Subscription id (`sub_…`); set by webhook |
| `created_at` / `updated_at` | Timestamps |

## Entitlement (with `access.py`)

Priority: `ACCESS_DEV_TIER` → authenticated user → (anonymous has no app access).

For an authenticated user:

1. `subscription_status == "active"` → Subscribed (full suite; internal tier `"pro"`)
2. Else if `trial_started_at` within 14 days → Trial (`has_suite_access`)
3. Else → Trial ended (no calculator access until subscribe)

Stripe Checkout webhooks flip `subscription_status` (see `SPEC-billing-stripe.md`).

## Out of scope

Password reset, Google OAuth, invite-only registration codes, roles/admin.
Email click-to-verify is deferred; open registration uses Cloudflare Turnstile
when ``TURNSTILE_SITE_KEY`` + ``TURNSTILE_SECRET_KEY`` are set (see
``web/app/turnstile.py``).

## Bot protection (Turnstile)

| Variable | Role |
|----------|------|
| `TURNSTILE_SITE_KEY` | Widget on `/register` |
| `TURNSTILE_SECRET_KEY` | Server-side siteverify |

Both must be set to enforce the check. If either is missing, registration works
without a widget (local/dev). Create a widget at
[Cloudflare Turnstile](https://dash.cloudflare.com/) with hostname
`hvac-calcs.app`.
