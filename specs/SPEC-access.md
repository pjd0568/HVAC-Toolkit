# Functional Spec — Access (Trial → Subscription)

**Module:** `web/app/access.py` (+ nav / blueprint gates)
**Status:** v0.3 — 27 July 2026 (single full-suite plan; no permanent Free tier)
**Clean-room note:** Commercial packaging for this product only. No reference to
any employer tooling or the frozen prototype.

## Purpose

Define how a 14-day full-suite trial works, what a paid subscription unlocks,
and a single place every calculator can ask “may this user use me?” so Stripe
can plug in later without rewriting every tool. Accounts and login gating are
specified in `SPEC-auth.md`.

## Commercial model

| Stage | Meaning |
|-------|---------|
| **Trial** | Full suite for 14 days from account registration. |
| **Subscribed** | Paid subscriber — full suite (`subscription_status == active`). Price: **£9.50/month**. |
| **Trial ended** | No calculator access until subscribed. Soft gate: subscribe panel (not a raw 403). |

There is **no permanent free calculator catalogue**. Dashboard, Help, Design
Guides, Methodology, and Coming Soon placeholders (Weather, Projects) remain
reachable after trial expiry so users can still reach pricing and reference
material.

## Suite catalogue (all unlocked on trial / subscription)

Psychrometrics (Single Point, Mixed Air, Cooling Coil, Desiccant, Heat & Humidify, AHU Design), Duct Sizing
(including Index Leg), Pipe Sizing (including Pipe System), Unit Converter, PDF
reports.

## Coming Soon (not gated as paid extras)

| Module id | Tool | Notes |
|-----------|------|-------|
| `weather` | Weather & Design Conditions | Placeholder + ASHRAE external links |
| `projects` | Projects | Static preview layout |

Nav and pages flag these with a **Coming Soon** chip only — no Pro tags.

## Trial clock

- Duration: **14 days**.
- Start: set on **register** (`User.trial_started_at`).
- Persistence: Postgres user row (survives cookie clear).
- While trial active: `tier == "trial"`, `has_suite_access == True`.
- After expiry without subscription: `tier == "free"`, `has_suite_access == False`.
- Subscribed: `User.subscription_status == "active"` (Stripe Managed Payments
  Checkout + webhooks — see `SPEC-billing-stripe.md`); internal tier code
  remains `"pro"` for the `ACCESS_DEV_TIER` override.

## Module flag API

```text
SUITE_MODULES             → frozenset of gated calculator ids
COMING_SOON_MODULES       → weather, projects
can_access(module_id)     → bool
get_entitlement()         → {tier, has_suite_access, trial_days_remaining, …}
PRICE_MONTHLY_GBP         → "9.50"
```

Injected into every template as `access` (same pattern as `U`). Sidebar/topbar
show Trial countdown or **Subscribed** — never “Pro”.

## Gating

1. **Login gate:** calculator shell requires authentication (`SPEC-auth.md`).
2. **Suite tools:** blueprint `@require_module(...)`; if denied, render the
   shared subscribe panel (HTTP 200) or JSON 403 for API/CSV. CTAs link to
   `/subscribe`.
3. **Coming Soon pages:** always open when logged in (placeholder content).

## Out of scope for this scaffold

- Softening access further (watermarked PDFs, etc.).
- Stripe Customer Portal (Managed Payments uses Link for subscription management).

## Dev override

`Config.ACCESS_DEV_TIER` = `None` | `"free"` | `"trial"` | `"pro"` forces the
entitlement in development (`"free"` = trial ended; `"pro"` = subscribed).
