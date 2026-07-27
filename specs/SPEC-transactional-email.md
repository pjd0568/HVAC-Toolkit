# Functional Spec — Transactional email (SMTP)

**Module:** `web/app/mail.py`, `web/app/lifecycle_mail.py`
**Status:** v0.1
**From address:** `info@hvac-calcs.app` (Google Workspace)

## Purpose

Send operational mail from the product mailbox:

| Trigger | Email |
|---------|--------|
| Account register | Trial welcome |
| Subscription becomes `active` | Thanks for subscribing |
| Subscription leaves `active` → `canceled` | Soft cancellation / come-back |

Contact-form messages already use the same SMTP helper.

## Railway variables

| Variable | Example |
|----------|---------|
| `MAIL_SERVER` | `smtp.gmail.com` |
| `MAIL_PORT` | `587` (or `465` if 587 is blocked) |
| `MAIL_USE_TLS` | `true` (for 587) |
| `MAIL_USE_SSL` | `true` when using port `465` |
| `MAIL_USERNAME` | `info@hvac-calcs.app` |
| `MAIL_PASSWORD` | Google **App Password** (not the normal login password) |
| `MAIL_DEFAULT_SENDER` | `info@hvac-calcs.app` |
| `CONTACT_EMAIL` | `info@hvac-calcs.app` |

If contact form sits on “Sending…” then fails: check Railway logs for
`SMTP auth failed` or `SMTP timed out`. Timeout on 587 → switch to:

```text
MAIL_PORT=465
MAIL_USE_SSL=true
MAIL_USE_TLS=false
```

### Google Workspace setup

1. Admin / account: enable 2-Step Verification for `info@`.
2. Google Account → Security → App passwords → create one for “Mail”.
3. Put that 16-character password in `MAIL_PASSWORD` on Railway.
4. Redeploy.

### Local test

```bash
cd web
source .venv/bin/activate
flask --app wsgi send-test-email you@example.com
```

## Behaviour notes

- If SMTP is unset, sends are skipped (logged); register / webhooks still succeed.
- Subscribe / cancel mails fire only on **status transitions** so Stripe webhook
  retries do not spam the user.
- Plain text only (no HTML templates yet).
