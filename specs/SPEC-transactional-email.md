# Functional Spec — Transactional email

**Module:** `web/app/mail.py`, `web/app/lifecycle_mail.py`
**Status:** v0.2 — Resend preferred on Railway
**From address:** `info@hvac-calcs.app`

## Why not Gmail SMTP on Railway?

Outbound SMTP (ports 587/465) from cloud hosts to `smtp.gmail.com` often
**times out or is refused**, even with a valid Workspace App Password. Prefer
an HTTP email API.

## Preferred: Resend

1. Create an account at [https://resend.com](https://resend.com)
2. **Domains → Add** `hvac-calcs.app` and add the DNS records Resend shows
   (SPF / DKIM — usually at Cloudflare)
3. Wait until the domain shows **Verified**
4. **API Keys → Create** → copy `re_…`
5. Railway variables:

| Variable | Value |
|----------|--------|
| `RESEND_API_KEY` | `re_…` |
| `MAIL_DEFAULT_SENDER` | `info@hvac-calcs.app` |
| `CONTACT_EMAIL` | `info@hvac-calcs.app` |

You can leave `MAIL_SERVER` / `MAIL_PASSWORD` unset when Resend is configured.
`send_email()` uses Resend whenever `RESEND_API_KEY` is present.

### Quick test before domain verify

Resend allows sending from `onboarding@resend.dev` **only to your Resend
account email**. For production mail to customers, the domain must be verified
and `MAIL_DEFAULT_SENDER` must be on that domain (e.g. `info@hvac-calcs.app`).

## Fallback: Google Workspace SMTP

Only if you must. Same App Password flow as before (`MAIL_*` vars). Unreliable
from Railway.

## Lifecycle emails

| Trigger | Email |
|---------|--------|
| Account register | Trial welcome |
| Subscription → `active` | Thanks for subscribing |
| Subscription `active` → `canceled` | Soft cancellation |

If mail is unset, sends are skipped (logged); register / webhooks still succeed.
