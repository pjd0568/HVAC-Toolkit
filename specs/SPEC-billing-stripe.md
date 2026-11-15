# Functional Spec — Stripe Managed Payments billing

**Module:** `web/app/stripe_billing.py`, `web/app/blueprints/billing.py`
**Status:** v0.2 — Checkout trial + webhooks (card up front, £0 until trial ends)
**Clean-room note:** Commercial packaging for this product only.

## Purpose

Take payment for the full-suite plan (£4.50/month or £39.50/year) via Stripe
**Managed Payments** (Stripe as merchant of record; tax calculated at checkout)
and sync `User.subscription_status` so `access.py` unlocks the suite.

New Pro customers start a **14-day Stripe subscription trial** on the existing
monthly Price (`STRIPE_PRICE_ID`), with a payment method collected at Checkout
and **no charge until the trial ends**. Existing paying subscribers are never
restarted or given another trial.

## Env (Test mode)

| Variable | Source |
|----------|--------|
| `STRIPE_SECRET_KEY` | [API keys](https://dashboard.stripe.com/test/apikeys) (`sk_test_…`) |
| `STRIPE_PUBLISHABLE_KEY` | Same page (`pk_test_…`) — reserved for future client use |
| `STRIPE_WEBHOOK_SECRET` | Webhook endpoint signing secret (`whsec_…`) |
| `STRIPE_PRICE_ID` | Price for £4.50/month GBP (`price_…`). Display amount is `PRICE_MONTHLY_GBP`. |
| `STRIPE_PRICE_ID_ANNUAL` | Price for £39.50/year GBP (`price_…`). Display amount is `PRICE_ANNUAL_GBP`. |
| `STRIPE_MANAGED_PAYMENTS` | Default `true` |

Do **not** run `flask ensure-stripe-product` against live Stripe. Checkout
requires the existing `STRIPE_PRICE_ID` (£4.50/month) and will not create a
Product or Price.

## Flow

1. CTA **Start your 14-day free trial** → register/login if needed (preserving
   `next`) → Checkout.
2. App ensures a Stripe Customer, creates a Checkout Session with
   `mode=subscription`, `managed_payments[enabled]=true`,
   `payment_method_collection=always`, line item = `STRIPE_PRICE_ID`, and
   `subscription_data.trial_period_days=14` when the account is trial-eligible.
3. Ineligible accounts (prior `trial_started_at`, prior Stripe subscription, or
   open suite subscription) get paid Checkout on the same Price with **no**
   trial days, or are redirected to Account billing if already subscribed.
4. Stripe redirects to `/subscribe/success?session_id={CHECKOUT_SESSION_ID}`.
   Access is confirmed from webhooks / retrieved session — not the URL alone.
5. Webhook `POST /webhooks/stripe` (signature verified, event-id idempotent):
   - `checkout.session.completed` / `async_payment_succeeded`
   - `customer.subscription.created` / `updated` / `deleted`
   - `invoice.paid` / `invoice.payment_failed`
6. Customer Portal: `POST /create-portal-session` for the logged-in user's
   `stripe_customer_id` only (return URL = Account billing).

## Status policy

| Stripe status | Stored | Suite access |
|---------------|--------|--------------|
| `trialing` | `trialing` | Yes (tier `trial`) |
| `active` | `active` | Yes (tier `pro`) |
| `past_due` | `past_due` | Yes + billing issue flag |
| `unpaid` / `incomplete` / `canceled` | same / canceled | No |

## Trial eligibility

- Eligible: no `trial_started_at`, no prior `stripe_subscription_id`, no open
  suite subscription.
- Not eligible: any prior trial (app or Stripe), prior Stripe subscription, or
  active/trialing/past_due Stripe-backed access.
- Legacy app trials (`trial_started_at` without Stripe sub) keep access until
  the 14-day clock ends; they are not given a second free Stripe trial.

## User columns

| Column | Notes |
|--------|-------|
| `stripe_customer_id` | Unique; created before Checkout |
| `stripe_subscription_id` | Unique; set from subscription events |
| `stripe_trial_end` | From Stripe `trial_end` |
| `stripe_current_period_end` | From Stripe `current_period_end` |
| `cancel_at_period_end` | From Stripe flag |
| `trial_started_at` | Set on first trial (blocks repeat free trials) |

## Operator note (Dashboard)

Enable / configure the **Stripe Customer Portal** (cancellation at period end,
payment method update) in the Stripe Dashboard. Application code only creates
portal sessions; it does not configure portal settings.

## Local webhook testing

```bash
stripe listen --forward-to localhost:5000/webhooks/stripe
# copy the whsec_… into STRIPE_WEBHOOK_SECRET
```

Test card: `4242 4242 4242 4242`, any future expiry, any CVC.
