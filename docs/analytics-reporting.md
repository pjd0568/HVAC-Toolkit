# Product analytics reporting

HVAC-CALCS stores allowlisted product events in the existing Postgres database.
Cloudflare Web Analytics and Google Search Console stay responsible for site
traffic and search. This report is for calculator and Pro usage.

## Owner access

Set on Railway (not in git):

```
ANALYTICS_ADMIN_EMAILS=you@example.com
ANALYTICS_REPORT_EMAIL=you@example.com
ANALYTICS_WEEKLY_REPORT_ENABLED=true
```

`ANALYTICS_ADMIN_EMAILS` is a comma-separated list. Only those accounts can open
`/admin/analytics`. A normal subscriber receives 403. The link is not in the
public navigation.

## Retention — review before relying on it

`ANALYTICS_RETENTION_DAYS` defaults to **365**.

That default is a product choice so a year can be compared with the previous
year. It is not a legal determination. Change it in the environment if a
shorter period is required. The privacy page prints the configured value.
The cleanup deletes `analytics_events` only. It does not delete users, trials,
or Stripe records.

`ANALYTICS_INTERNAL_EMAILS` is an optional comma-separated list. Events for
those accounts, and for `ANALYTICS_ADMIN_EMAILS`, are stored with
`excluded = true` and left out of the report. The flag is set on the server
from the signed-in account. It is not a value the browser can send. Historical
rows stay included because they were not flagged.

## Counting

Timezone for periods is `Europe/London`. Queries use a half-open UTC range
from local midnight to the next local midnight.

The unique completion rate is ordered journeys, capped at 100%. Raw
completions can be higher than unique starts because one journey can calculate
more than once. The 30-minute start window and the 15-second completion
window only suppress duplicate writes.

The sequenced funnel uses a 7-day attribution window. Both events must be
inside the reporting period. Preset dashboard ranges end yesterday so a
partial day is not compared with a complete day.

First-touch is written once per session. Latest-touch changes when a new
`utm_campaign` or external referrer arrives. Rows from before that capture
have null touch flags and stay `unknown`. Do not backfill them.

`subscription_active` is written only when Stripe's subscription status is
`active` on a verified webhook, and only once per user. A checkout success
page view does not count. A payment-mode checkout with no subscription object
does not count.

Google Search Console is not connected. Compare its export (queries,
impressions, clicks, CTR, position, landing page) with the first-party
`google / organic` rows and landing paths. `document.referrer` does not
contain the search query.

## UTM links

```
utm_source=<platform>&utm_medium=<format>&utm_campaign=<campaign>&utm_content=<creative>
```

Lowercase, underscores. The admin page builds a copyable URL.

## Weekly email

The report covers the previous complete Monday–Sunday in `Europe/London`.
`weekly_key` stops a duplicate execution of that same week from sending
again. It is not a reason to schedule the job more than once.

```
flask --app wsgi analytics-weekly-report
```

That command also prunes events older than the retention window.
`flask --app wsgi analytics-prune` prunes without sending.

Railway runs the site with two Gunicorn workers and has no in-process
scheduler. Do not add one. The website service does not send the report.

There is already one cron service, **HVAC Toolkit**. Fix that service. Do not
add another cron service. Do not change the start command on **Pauls Hvac App**.
That service is the website. If its start command becomes the report command,
hvac-calcs.app stops serving pages.

The usual reason a Monday email never arrives is that **HVAC Toolkit** still
starts Gunicorn, the same command as the website, instead of the report command.

On the cron service **HVAC Toolkit** only:

1. Settings → **Cron Schedule**: `0 7 * * 1` (Monday 07:00 UTC). That is about
   07:00 UK time in winter and 08:00 UK time in summer. Do not add a second
   Monday run.
2. Settings → **Custom start command**:

```
flask --app wsgi analytics-weekly-report
```

3. Variables → `DATABASE_URL` must be the website database, written as the
   Railway reference `${{Postgres.DATABASE_URL}}` (use the Postgres service’s
   real name if it is not `Postgres`). Also set
   `ANALYTICS_WEEKLY_REPORT_ENABLED=true`, `ANALYTICS_REPORT_EMAIL`,
   `RESEND_API_KEY`, `MAIL_DEFAULT_SENDER`, and `SECRET_KEY`.
4. Deploy **HVAC Toolkit** after this code is on the `Publish` branch. The next
   Monday run should log `weekly=sent` or `weekly=already-sent`. Logs that show
   Gunicorn listening on a port mean the start command is still the website
   command.

**Retry weekly report** on `https://hvac-calcs.app/admin/analytics` sends the
last complete week from the website service. Use that to send the missed week
without waiting for Monday. It does not replace the cron start command.

A run records `started_at`, `completed_at`, `attempt_count`, `status`, and the provider message id when Resend returns one. It does not log the recipient address or the API key.

A run claims the week by inserting `analytics_report_runs.status = sending`
with `weekly_key` set to the period start date. A second run that sees that
claim still inside 30 minutes does not send. A successful send keeps the
key and is never sent again. A failed email clears `weekly_key`, so the
next run can retry. If the process dies and leaves `sending`, a later run
releases that claim once it is at least 30 minutes old, then sends. The
release is a conditional update, so two recoveries cannot both send.

Manual send from the dashboard uses the dates selected on screen and the same
recipient. It is a POST with a session token.
