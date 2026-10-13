"""Product analytics: allowlist, privacy, owner dashboard, weekly periods."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app import create_app
from app.analytics import record_analytics_event
from app.analytics_report import build_report, previous_complete_week, prune_analytics_events, render_markdown, send_weekly_analytics_report
from app.extensions import db
from app.models.analytics import AnalyticsEvent, AnalyticsReportRun
from app.models.user import User


@pytest.fixture
def analytics_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'analytics.db'}")
    monkeypatch.setenv("SECRET_KEY", "analytics-test")
    application = create_app()
    application.config.update(
        TESTING=True,
        REGISTRATION_OPEN=True,
        ANALYTICS_ADMIN_EMAILS="owner@example.com",
        ANALYTICS_REPORT_EMAIL="owner@example.com",
        ANALYTICS_WEEKLY_REPORT_ENABLED=True,
        ANALYTICS_RETENTION_DAYS=30,
        TURNSTILE_SITE_KEY="",
        TURNSTILE_SECRET_KEY="",
    )
    return application


@pytest.fixture
def client(analytics_app):
    return analytics_app.test_client()


def _user(email: str, password: str = "password123") -> None:
    user = User(email=email, trial_started_at=datetime.now(timezone.utc).date(), subscription_status="trialing")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()


def _login(client, email: str) -> None:
    response = client.post("/login", data={"email": email, "password": "password123"})
    assert response.status_code in {302, 303}


def test_allowlisted_event_is_stored(analytics_app):
    with analytics_app.app_context():
        record_analytics_event("checkout_start", route="/create-checkout-session")
        row = AnalyticsEvent.query.one()
        assert row.event_name == "checkout_start"
        assert row.route == "/create-checkout-session"


def test_unknown_event_and_calculation_values_are_dropped(client, analytics_app):
    response = client.post("/e", json={
        "event": "airflow_recorded",
        "props": {"tool": "duct_sizing", "airflow": "1.7", "email": "a@b.c"},
    })
    assert response.status_code == 204
    with analytics_app.app_context():
        assert AnalyticsEvent.query.count() == 0

    ok = client.post("/e", json={
        "event": "calculator_start",
        "props": {"tool": "duct_sizing", "airflow": "1.7", "velocity": "6"},
    })
    assert ok.status_code == 204
    with analytics_app.app_context():
        row = AnalyticsEvent.query.one()
        blob = " ".join(str(value) for value in row.__dict__.values())
        assert row.tool == "duct_sizing"
        assert "1.7" not in blob
        assert "@" not in blob


def test_invalid_tool_and_overlong_utm_are_rejected(analytics_app):
    with analytics_app.app_context():
        record_analytics_event("calculator_complete", tool="not_a_tool")
        record_analytics_event("calculator_start", tool="x" * 80)
        record_analytics_event(
            "calculator_complete",
            tool="duct_sizing",
            utm_campaign="bad campaign",
            utm_source="linkedin",
        )
        row = AnalyticsEvent.query.one()
        assert row.tool == "duct_sizing"
        assert row.utm_source == "linkedin"
        assert row.utm_campaign is None


_PERMITTED_EVENT_COLUMNS = {
    "id",
    "event_name",
    "occurred_at",
    "anonymous_session_id",
    "user_id",
    "tool",
    "category",
    "source",
    "target",
    "route",
    "access_state",
    "unit_system",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
}

# Text dimensions that can hold client or application strings.
# Identifiers and timestamps are excluded: they are system-generated and can
# coincidentally contain a digit sequence such as "1.7".
_STORED_TEXT_FIELDS = (
    "event_name",
    "tool",
    "category",
    "source",
    "target",
    "route",
    "access_state",
    "unit_system",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
)

_CALCULATION_PAYLOAD_COLUMNS = {
    "airflow",
    "volume",
    "metadata",
    "payload",
    "props",
    "properties",
    "json",
    "data",
    "request",
    "form",
    "body",
    "inputs",
    "outputs",
}


def test_duct_calculate_records_completion_without_inputs(client, analytics_app):
    sentinels = ("0.137701", "3.917363", "zzq-project-917363")
    response = client.get(
        "/duct-sizing/api/state"
        "?intent=calculate"
        "&volume=0.137701"
        "&target_value=3.917363"
        "&project=zzq-project-917363"
    )
    assert response.status_code == 200
    assert not response.get_json().get("error")
    with analytics_app.app_context():
        columns = {column.name for column in AnalyticsEvent.__table__.columns}
        assert columns == _PERMITTED_EVENT_COLUMNS
        assert columns.isdisjoint(_CALCULATION_PAYLOAD_COLUMNS)
        row = AnalyticsEvent.query.filter_by(event_name="calculator_complete").one()
        assert row.event_name == "calculator_complete"
        assert row.tool == "duct_sizing"
        assert row.route == "/duct-sizing/api/state"
        assert row.category == "air_distribution"
        assert row.source is None
        assert row.target is None
        assert row.utm_source is None
        assert row.utm_medium is None
        assert row.utm_campaign is None
        assert row.utm_content is None
        for name in _STORED_TEXT_FIELDS:
            value = getattr(row, name)
            if value is None:
                continue
            text = str(value)
            for sentinel in sentinels:
                assert sentinel not in text, name


def test_analytics_failure_does_not_block_teaser(client, monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("app.analytics._record", explode)
    response = client.post("/api/psychro/teaser", json={
        "system": "SI",
        "prop": "rh",
        "t_db": 21,
        "val": 50,
    })
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_owner_dashboard_is_private(client, analytics_app):
    anonymous = client.get("/admin/analytics/")
    assert anonymous.status_code == 302
    assert "/login" in anonymous.headers["Location"]

    with analytics_app.app_context():
        _user("subscriber@example.com")
        _user("owner@example.com")
    _login(client, "subscriber@example.com")
    forbidden = client.get("/admin/analytics/")
    assert forbidden.status_code == 403

    client.post("/logout")
    _login(client, "owner@example.com")
    allowed = client.get("/admin/analytics/")
    assert allowed.status_code == 200
    assert b"Product Analytics" in allowed.data
    assert b"subscriber@example.com" not in allowed.data


def test_funnel_uses_unique_journeys_and_guards_zero(analytics_app):
    with analytics_app.app_context():
        empty = build_report(datetime.now(timezone.utc).date(), datetime.now(timezone.utc).date())
        assert empty.calc_to_cta is None
        assert "not calculated" in render_markdown(empty)

        with analytics_app.test_request_context("/tools/duct-sizing-calculator"):
            record_analytics_event("calculator_complete", tool="duct_sizing")
            record_analytics_event("calculator_complete", tool="pipe_sizing")
            record_analytics_event("pro_cta_click", source="duct_sizing", target="duct_index_leg")
        report = build_report(datetime.now(timezone.utc).date(), datetime.now(timezone.utc).date())
        assert report.completions == 2
        assert report.unique_free_journeys == 1
        text = render_markdown(report)
        assert "duct_sizing" in text
        assert "anonymous" not in text.lower() or "session" in text


def test_markdown_omits_identifiers(analytics_app):
    with analytics_app.app_context():
        record_analytics_event(
            "registration_complete",
            source="duct_sizing",
            target="duct_index_leg",
            user_id=None,
        )
        row = AnalyticsEvent.query.one()
        row.anonymous_session_id = "session-secret-value"
        row.user_id = None
        db.session.commit()
        text = render_markdown(build_report(
            row.occurred_at.date() - timedelta(days=1),
            row.occurred_at.date() + timedelta(days=1),
        ))
        assert "session-secret-value" not in text
        assert "@" not in text


def test_previous_london_week_across_bst():
    london = ZoneInfo("Europe/London")
    tuesday = datetime(2026, 10, 13, 10, 0, tzinfo=london)
    assert previous_complete_week(tuesday) == (
        datetime(2026, 10, 5).date(),
        datetime(2026, 10, 11).date(),
    )
    monday = datetime(2026, 10, 12, 8, 0, tzinfo=london)
    assert previous_complete_week(monday) == (
        datetime(2026, 10, 5).date(),
        datetime(2026, 10, 11).date(),
    )
    # 23:30 UTC on 14 Jun 2026 is 00:30 BST on Monday 15 Jun.
    bst_monday = datetime(2026, 6, 14, 23, 30, tzinfo=timezone.utc)
    assert previous_complete_week(bst_monday) == (
        datetime(2026, 6, 8).date(),
        datetime(2026, 6, 14).date(),
    )


def test_weekly_report_sends_once(analytics_app):
    with analytics_app.app_context():
        with pytest.MonkeyPatch.context() as patcher:
            sent = []

            def fake_send(**kwargs):
                sent.append(kwargs["subject"])
                return True

            patcher.setattr("app.mail.mail_configured", lambda: True)
            patcher.setattr("app.mail.send_email", fake_send)
            now = datetime(2026, 10, 13, 8, 0, tzinfo=ZoneInfo("Europe/London"))
            assert send_weekly_analytics_report(now) == "sent"
            assert send_weekly_analytics_report(now) == "already-sent"
            assert len(sent) == 1
            assert "2026-10-05 - 2026-10-11" in sent[0]


def _weekly_claim(start, end, status, created_at):
    row = AnalyticsReportRun(
        period_start=start,
        period_end=end,
        kind="weekly",
        status=status,
        weekly_key=start.isoformat(),
        created_at=created_at,
        sent_at=created_at if status == "sent" else None,
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_weekly_immediate_duplicate_does_not_send(analytics_app):
    with analytics_app.app_context():
        now = datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc)
        start, end = previous_complete_week(now)
        _weekly_claim(start, end, "sending", now - timedelta(minutes=1))
        with pytest.MonkeyPatch.context() as patcher:
            sent = []
            patcher.setattr("app.mail.mail_configured", lambda: True)
            patcher.setattr("app.mail.send_email", lambda **kwargs: sent.append(kwargs) or True)
            assert send_weekly_analytics_report(now) == "already-sent"
            assert sent == []


def test_weekly_failed_send_can_retry(analytics_app):
    with analytics_app.app_context():
        with pytest.MonkeyPatch.context() as patcher:
            attempts = {"n": 0}

            def fake_send(**kwargs):
                attempts["n"] += 1
                return attempts["n"] > 1

            patcher.setattr("app.mail.mail_configured", lambda: True)
            patcher.setattr("app.mail.send_email", fake_send)
            now = datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc)
            assert send_weekly_analytics_report(now) == "failed"
            assert send_weekly_analytics_report(now) == "sent"
            assert attempts["n"] == 2
            start, _end = previous_complete_week(now)
            sent_row = AnalyticsReportRun.query.filter_by(
                weekly_key=start.isoformat(),
                status="sent",
            ).one()
            assert sent_row.weekly_key == start.isoformat()


def test_weekly_stale_sending_can_recover(analytics_app):
    with analytics_app.app_context():
        now = datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc)
        start, end = previous_complete_week(now)
        stale = _weekly_claim(start, end, "sending", now - timedelta(minutes=31))
        stale_id = stale.id
        with pytest.MonkeyPatch.context() as patcher:
            sent = []
            patcher.setattr("app.mail.mail_configured", lambda: True)
            patcher.setattr("app.mail.send_email", lambda **kwargs: sent.append(kwargs["subject"]) or True)
            assert send_weekly_analytics_report(now) == "sent"
            assert len(sent) == 1
            released = db.session.get(AnalyticsReportRun, stale_id)
            assert released.status == "failed"
            assert released.weekly_key is None
            claimed = AnalyticsReportRun.query.filter_by(
                weekly_key=start.isoformat(),
                status="sent",
            ).one()
            assert claimed.id != stale_id


def test_weekly_sent_key_cannot_be_resent(analytics_app):
    with analytics_app.app_context():
        now = datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc)
        start, end = previous_complete_week(now)
        _weekly_claim(start, end, "sent", now - timedelta(days=1))
        with pytest.MonkeyPatch.context() as patcher:
            sent = []
            patcher.setattr("app.mail.mail_configured", lambda: True)
            patcher.setattr("app.mail.send_email", lambda **kwargs: sent.append(kwargs) or True)
            assert send_weekly_analytics_report(now) == "already-sent"
            assert send_weekly_analytics_report(now) == "already-sent"
            assert sent == []


def test_prune_deletes_events_not_users(analytics_app):
    with analytics_app.app_context():
        _user("keep@example.com")
        old = AnalyticsEvent(
            event_name="login",
            occurred_at=datetime.now(timezone.utc) - timedelta(days=40),
        )
        fresh = AnalyticsEvent(
            event_name="login",
            occurred_at=datetime.now(timezone.utc),
        )
        db.session.add_all([old, fresh])
        db.session.commit()
        assert prune_analytics_events() == 1
        assert AnalyticsEvent.query.count() == 1
        assert User.query.filter_by(email="keep@example.com").count() == 1


def test_send_now_requires_token_and_posts(client, analytics_app, monkeypatch):
    with analytics_app.app_context():
        _user("owner@example.com")
    _login(client, "owner@example.com")
    blocked = client.post("/admin/analytics/send", data={"start": "2026-10-01", "end": "2026-10-07"})
    assert blocked.status_code == 302
    calls = []
    monkeypatch.setattr("app.mail.mail_configured", lambda: True)
    monkeypatch.setattr("app.mail.send_email", lambda **kwargs: calls.append(kwargs) or True)
    page = client.get("/admin/analytics/?days=7")
    token = page.get_data(as_text=True).split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
    sent = client.post("/admin/analytics/send", data={
        "csrf_token": token,
        "start": "2026-10-01",
        "end": "2026-10-07",
    })
    assert sent.status_code == 302
    assert len(calls) == 1
    assert calls[0]["to"] == "owner@example.com"
    assert "1.7" not in calls[0]["body"]


def test_checkout_success_does_not_record_subscription(client, analytics_app):
    with analytics_app.app_context():
        _user("owner@example.com")
    _login(client, "owner@example.com")
    client.get("/subscribe/success")
    with analytics_app.app_context():
        assert AnalyticsEvent.query.filter_by(event_name="subscription_active").count() == 0
