# Functional Spec — Access Tiers (Free / Trial / Pro)

**Module:** `web/app/access.py` (+ nav / blueprint gates)
**Status:** v0.1 scaffold — 20 July 2026 (pre-auth MVP)
**Clean-room note:** Commercial packaging for this product only. No reference to
any employer tooling or the frozen prototype.

## Purpose

Define which calculators are available on the Free tier vs Pro, how a 14-day
full-suite trial works, and a single place every module can ask “may this user
use me?” so Stripe / accounts can plug in later without rewriting every tool.

## Tiers

| Tier | Meaning |
|------|---------|
| **Free** | Permanent free tools only (see catalogue). |
| **Trial** | Full suite for 14 days from first visit (clock starts once). |
| **Pro** | Paid subscriber — full suite (Stripe later). |

`can_use_pro` is true for **Trial** and **Pro**. Free after trial expiry cannot
open Pro modules (soft gate: upgrade panel, not a raw 403).

## Free catalogue (MVP)

| Module id | Tool | Notes |
|-----------|------|-------|
| `psychro.single_point` | Psychrometrics — Single Point | Full single-point tool |
| `duct.sizer` | Duct Sizing — core 3-column sizer | Index Leg is Pro (`duct.index_leg`) |
| `pipe.sizer` | Pipe Sizing — Stage 1 DN / flow sizer | System builder + lift/head is Pro (`pipe.system`) |

Always free (navigation / learning, not “calculators”):

- `dashboard`, `help`, `guides` (Design Guides)

## Pro catalogue (everything else)

Includes but is not limited to: Mixed Air, Cooling Coil, AHU Design, Weather,
Unit Converter, Projects, Duct Index Leg, Pipe System (pressure drop + lift /
pump head), and any future Pro-only modules.

## Trial clock

- Duration: **14 days**.
- Start: first request that touches the access layer (session today).
- Persistence today: Flask **session** (`trial_started_at` ISO date). Honest
  limitation until auth: clearing cookies resets the clock — acceptable for
  pre-launch MVP only; move to user record when accounts land.
- While trial active: `tier == "trial"`, `can_use_pro == True`.
- After expiry without Pro: `tier == "free"`, `can_use_pro == False`.

## Module flag API

```text
MODULES[module_id].tier   → "free" | "pro"
can_access(module_id)     → bool
get_entitlement()         → {tier, can_use_pro, trial_days_remaining, …}
```

Injected into every template as `access` (same pattern as `U`). Nav shows a
**Pro** chip on Pro modules. During trial the sidebar foot shows remaining days.

## Gating

1. **Whole-route Pro tools** (e.g. Weather, Mixed Air): blueprint checks
   `can_access(...)`; if denied, render a shared upgrade panel (HTTP 200) rather
   than crashing.
2. **Mixed pages** (Duct, Pipe): Free sizer always available; Pro panels
   (Index Leg / Pipe System) replaced by a locked card when `can_use_pro` is
   false.

## Out of scope for this scaffold

- Stripe Checkout / Customer Portal / Tax.
- Real user accounts and durable trial binding.
- Usage metering (e.g. “N free calcs per month”) — Free is unlimited on the
  three free tools for MVP.
- Softening Free further (watermarked PDFs, etc.).

## Dev override

`Config.ACCESS_DEV_TIER` = `None` | `"free"` | `"trial"` | `"pro"` forces the
entitlement in development so Free/Pro UI can be click-tested without waiting
out the trial.
