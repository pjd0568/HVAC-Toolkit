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
| `/`, `/login`, `/subscribe`, `/health`, static | Public |
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
| `created_at` / `updated_at` | Timestamps |

## Entitlement (with `access.py`)

Priority: `ACCESS_DEV_TIER` → authenticated user → (anonymous has no app access).

For an authenticated user:

1. `subscription_status == "active"` → Pro
2. Else if `trial_started_at` within 14 days → Trial (`can_use_pro`)
3. Else → Free

Stripe Checkout / webhooks later only flip `subscription_status`.

## Out of scope

Email verification, password reset, Google OAuth, invite-only registration,
roles/admin, Stripe.
