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
scheduler. Do not add one. Create a separate Railway Cron service that uses
this same image and start command:

```
flask --app wsgi analytics-weekly-report
```

Cron, one Monday run in UTC:

```
0 7 * * 1
```

That is about 07:00 UK time in winter and 08:00 UK time in summer. Do not
add further Monday executions to chase British Summer Time. The recipient
is `ANALYTICS_REPORT_EMAIL`. No address is hard-coded.

A run claims the week by inserting `analytics_report_runs.status = sending`
with `weekly_key` set to the period start date. A second run that sees that
claim still inside 30 minutes does not send. A successful send keeps the
key and is never sent again. A failed email clears `weekly_key`, so the
next run can retry. If the process dies and leaves `sending`, a later run
releases that claim once it is at least 30 minutes old, then sends. The
release is a conditional update, so two recoveries cannot both send.

Manual send from the dashboard uses the dates selected on screen and the same
recipient. It is a POST with a session token.
