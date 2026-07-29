# Functional Spec — Stripe Managed Payments billing

**Module:** `web/app/stripe_billing.py`, `web/app/blueprints/billing.py`
**Status:** v0.1 — Checkout + webhooks (Test mode)
**Clean-room note:** Commercial packaging for this product only.

## Purpose

Take payment for the £9.50/month full-suite plan via Stripe **Managed Payments**
(Stripe as merchant of record; tax calculated at checkout) and flip
`User.subscription_status` so `access.py` unlocks the suite.

## Env (Test mode)

| Variable | Source |
|----------|--------|
| `STRIPE_SECRET_KEY` | [API keys](https://dashboard.stripe.com/test/apikeys) (`sk_test_…`) |
| `STRIPE_PUBLISHABLE_KEY` | Same page (`pk_test_…`) — reserved for future client use |
| `STRIPE_WEBHOOK_SECRET` | Webhook endpoint signing secret (`whsec_…`) |
| `STRIPE_PRICE_ID` | Price for £9.50/month GBP (`price_…`) |
| `STRIPE_MANAGED_PAYMENTS` | Default `true` |

Before first Checkout: accept Managed Payments terms at
[Dashboard → Settings → Managed Payments](https://dashboard.stripe.com/test/settings/managed-payments).

Create the product either in the Dashboard (tax code **eligible for Managed
Payments**, e.g. `txcd_10103100`) or:

```bash
cd web
source .venv/bin/activate   # required — plain `flask` is often not on PATH
flask --app wsgi ensure-stripe-product
# then set STRIPE_PRICE_ID=price_…
# or without activate:
#   .venv/bin/flask --app wsgi ensure-stripe-product
```

## Flow

1. Signed-in user POSTs `/create-checkout-session`.
2. App ensures a Stripe Customer, creates a Checkout Session with
   `mode=subscription`, `managed_payments[enabled]=true`, line item =
   `STRIPE_PRICE_ID`, and redirects (303) to `session.url`.
3. Stripe redirects to `/subscribe/success` after payment.
4. Webhook `POST /webhooks/stripe` handles:
   - `checkout.session.completed` / `checkout.session.async_payment_succeeded`
     → set `subscription_status=active`, store `stripe_customer_id` /
     `stripe_subscription_id`
   - `customer.subscription.updated` / `customer.subscription.deleted`
     → keep status in sync (canceled / unpaid → suite locks after trial rules)

Managed Payments Checkout uses Stripe’s preview API version
`2026-02-25.preview` on product and session create calls (per Stripe blueprint).
Do **not** send unsupported params (`automatic_tax`, `payment_method_types`,
shipping, Connect fee fields, etc.).

## User columns

| Column | Notes |
|--------|-------|
| `stripe_customer_id` | Unique; created before Checkout |
| `stripe_subscription_id` | Unique; set from completed session / subscription events |

## Local webhook testing

```bash
stripe listen --forward-to localhost:5000/webhooks/stripe
# copy the whsec_… into STRIPE_WEBHOOK_SECRET
```

Test card: `4242 4242 4242 4242`, any future expiry, any CVC. Try different
billing addresses to see tax.

## Out of scope (parked until after soft launch)

Customer Portal (Managed Payments subscription management is via Link — see
Help → Account, billing & cancel), refunds UI, multi-currency prices, annual
plans. Operator dogfood + live cutover: `docs/go-live-checklist.md`.
