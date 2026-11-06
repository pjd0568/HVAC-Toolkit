"""Sequenced funnel, attribution and weekly-send guarantees.

Synthetic rows live in the test database only.
"""

import json
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from app import create_app
from app.analytics import (
    ALLOWED_EVENTS,
    capture_campaign,
    link_session_to_user,
    note_confirmed_subscription,
    record_analytics_event,
)
from app.analytics_channels import build_campaign_url, classify_channel
from app.analytics_report import (
    _DIAGNOSTIC_EVENTS,
    build_report,
    format_delta,
    render_email_html,
    render_markdown,
    send_weekly_analytics_report,
)
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


PERIOD_START = date(2026, 10, 5)
PERIOD_END = date(2026, 10, 11)
T0 = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)


def _at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def _add(event_name: str, minutes: int, **kwargs) -> None:
    row = AnalyticsEvent(event_name=event_name, occurred_at=_at(minutes), **kwargs)
    db.session.add(row)


def _touch(source=None, medium=None, campaign=None, content=None, host=None, path="/", captured=True):
    channel = classify_channel(utm_source=source, referrer_host=host, captured=captured)
    return {
        "first_captured": captured,
        "latest_captured": captured,
        "first_utm_source": source,
        "first_utm_medium": medium,
        "first_utm_campaign": campaign,
        "first_utm_content": content,
        "utm_source": source,
        "utm_medium": medium,
        "utm_campaign": campaign,
        "utm_content": content,
        "first_landing_path": path,
        "latest_landing_path": path,
        "first_referrer_host": host,
        "latest_referrer_host": host,
        "first_channel": channel,
        "latest_channel": channel,
        "first_seen_at": T0,
        "latest_seen_at": T0,
    }


def test_completion_rate_uses_ordered_journeys_and_caps_at_100(analytics_app):
    with analytics_app.app_context():
        _add("calculator_start", 0, anonymous_session_id="s-many", tool="psychrometric_single")
        for minute in (5, 10, 15, 20):
            _add("calculator_complete", minute, anonymous_session_id="s-many", tool="psychrometric_single")
        _add("calculator_complete", 1, anonymous_session_id="s-pipe", tool="pipe_sizing")
        _add("calculator_start", 30, anonymous_session_id="s-pipe", tool="pipe_sizing")
        _add("calculator_start", 2, anonymous_session_id="s-a", tool="duct_sizing")
        _add("calculator_complete", 3, anonymous_session_id="s-b", tool="duct_sizing")
        db.session.commit()
        report = build_report(PERIOD_START, PERIOD_END)
        by_tool = {row.tool: row for row in report.calculators}
        psych = by_tool["psychrometric_single"]
        assert psych.unique_starts == 1
        assert psych.unique_completions == 1
        assert psych.raw_completions == 4
        assert psych.matched_completions == 1
        assert psych.completion_rate == "100%"
        assert psych.per_journey == "4.00"
        pipe = by_tool["pipe_sizing"]
        assert pipe.unique_starts == 1
        assert pipe.unique_completions == 1
        assert pipe.matched_completions == 0
        assert pipe.completion_rate == "0%"
        duct = by_tool["duct_sizing"]
        assert duct.unique_starts == 1
        assert duct.unique_completions == 1
        assert duct.matched_completions == 0
        assert duct.completion_rate == "0%"
        for row in report.calculators:
            if row.unique_starts:
                assert row.matched_completions <= row.unique_starts


def test_sequences_ignore_other_sessions_and_earlier_events(analytics_app):
    with analytics_app.app_context():
        _add("calculator_complete", 0, anonymous_session_id="s-1", tool="duct_sizing")
        _add("pro_cta_view", 5, anonymous_session_id="s-1", source="duct_sizing", target="duct_index_leg", cta_placement="result")
        _add("pro_cta_click", 1, anonymous_session_id="s-1", source="duct_sizing", target="duct_index_leg", cta_placement="result")
        _add("pro_cta_click", 6, anonymous_session_id="s-2", source="duct_sizing", target="duct_index_leg", cta_placement="result")
        db.session.commit()
        report = build_report(PERIOD_START, PERIOD_END)
        view_step = report.funnel[0]
        click_step = report.funnel[1]
        assert view_step.label == "Free completion → CTA view"
        assert view_step.eligible == 1
        assert view_step.reached == 1
        assert click_step.eligible == 1
        assert click_step.reached == 0


def test_anonymous_journey_links_to_user_without_duplicating(analytics_app):
    with analytics_app.app_context():
        user = User(email="person@example.com", trial_started_at=PERIOD_START, subscription_status="trialing")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        _add(
            "calculator_complete",
            0,
            anonymous_session_id="s-link",
            tool="duct_sizing",
        )
        _add(
            "pro_cta_view",
            1,
            anonymous_session_id="s-link",
            source="duct_sizing",
            target="duct_index_leg",
            cta_placement="result",
        )
        _add(
            "pro_cta_click",
            2,
            anonymous_session_id="s-link",
            source="duct_sizing",
            target="duct_index_leg",
            cta_placement="result",
        )
        _add(
            "registration_start",
            3,
            anonymous_session_id="s-link",
            source="duct_sizing",
            target="duct_index_leg",
        )
        db.session.commit()
        before = AnalyticsEvent.query.count()
    with analytics_app.test_request_context("/register"):
        from flask import session

        session["aid"] = "s-link"
        link_session_to_user(user_id)
    with analytics_app.app_context():
        assert AnalyticsEvent.query.count() == before
        linked = AnalyticsEvent.query.filter_by(anonymous_session_id="s-link").all()
        assert linked
        assert {row.user_id for row in linked} == {user_id}
        _add(
            "registration_complete",
            4,
            anonymous_session_id="s-link",
            user_id=user_id,
            source="duct_sizing",
            target="duct_index_leg",
        )
        _add("pro_tool_use", 5, anonymous_session_id="s-link", user_id=user_id, tool="duct_index_leg")
        _add("checkout_start", 6, user_id=user_id)
        _add("subscription_active", 7, user_id=user_id)
        db.session.commit()
        report = build_report(PERIOD_START, PERIOD_END)
        paid = report.funnel[-1]
        assert paid.label == "Free completion → active subscription"
        assert paid.eligible == 1
        assert paid.reached == 1
        assert report.audience.new_pro_users == 1
        assert report.audience.anonymous_pro_events == 0


def test_returning_anonymous_and_internal_pro_use_are_separate(analytics_app):
    with analytics_app.app_context():
        old = User(
            email="old@example.com",
            trial_started_at=date(2026, 1, 1),
            subscription_status="trialing",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        old.set_password("password123")
        db.session.add(old)
        db.session.commit()
        _add("pro_tool_use", 10, user_id=old.id, tool="mixed_air")
        _add("pro_tool_use", 11, tool="mixed_air")
        _add("pro_tool_use", 12, tool="mixed_air", excluded=True, anonymous_session_id="s-staff")
        db.session.commit()
        report = build_report(PERIOD_START, PERIOD_END)
        assert report.audience.returning_pro_users == 1
        assert report.audience.new_pro_users == 0
        assert report.audience.anonymous_pro_events == 1
        assert report.audience.internal_pro_events == 1
        assert report.pro_uses == 2
        assert report.excluded_events == 1


def test_first_touch_survives_a_later_campaign(client, analytics_app):
    first = client.get(
        "/?utm_source=LinkedIn&utm_medium=video&utm_campaign=psychrometrics_week&utm_content=single_point_demo"
    )
    assert first.status_code in {200, 301, 302, 308}
    client.get("/?utm_source=youtube&utm_medium=short&utm_campaign=other_week&utm_content=clip")
    client.post("/e", json={"event": "calculator_start", "props": {"tool": "duct_sizing"}})
    with analytics_app.app_context():
        row = AnalyticsEvent.query.filter_by(event_name="calculator_start").one()
        assert row.first_utm_source == "linkedin"
        assert row.first_utm_medium == "video"
        assert row.first_utm_campaign == "psychrometrics_week"
        assert row.utm_source == "youtube"
        assert row.utm_campaign == "other_week"
        assert row.first_channel == "linkedin / campaign"
        assert row.latest_channel == "youtube / campaign"
        assert row.first_utm_source != row.utm_source


def test_latest_touch_updates_for_external_referrer_only(client, analytics_app):
    client.get("/")
    client.get("/", headers={"Referer": "https://www.google.co.uk/search?q=secret-query"})
    client.post("/e", json={"event": "calculator_start", "props": {"tool": "duct_sizing"}})
    with analytics_app.app_context():
        row = AnalyticsEvent.query.filter_by(event_name="calculator_start").one()
        assert row.first_channel == "direct"
        assert row.first_referrer_host is None
        assert row.latest_referrer_host == "www.google.co.uk"
        assert row.latest_channel == "google / organic"
        blob = " ".join(str(getattr(row, name) or "") for name in (
            "first_landing_path",
            "latest_landing_path",
            "first_referrer_host",
            "latest_referrer_host",
            "route",
        ))
        assert "secret-query" not in blob


def test_channel_classification_examples():
    assert classify_channel(utm_source="instagram", referrer_host="google.com", captured=True) == "instagram / campaign"
    assert classify_channel(utm_source=None, referrer_host="www.google.com", captured=True) == "google / organic"
    assert classify_channel(utm_source=None, referrer_host="www.bing.com", captured=True) == "bing / organic"
    assert classify_channel(utm_source=None, referrer_host="duckduckgo.com", captured=True) == "duckduckgo / organic"
    assert classify_channel(utm_source=None, referrer_host="m.facebook.com", captured=True) == "facebook / referral"
    assert classify_channel(utm_source=None, referrer_host="chatgpt.com", captured=True) == "chatgpt / referral"
    assert classify_channel(utm_source=None, referrer_host="example.com", captured=True) == "other_referral / referral"
    assert classify_channel(utm_source=None, referrer_host=None, captured=True) == "direct"
    assert classify_channel(utm_source=None, referrer_host=None, captured=False) == "unknown"
    assert classify_channel(utm_source=None, referrer_host="www.google.com", captured=True, utm_unusable=True) == "unknown"
    url = build_campaign_url(
        "https://hvac-calcs.app/duct-sizing",
        source="linkedin",
        medium="video",
        campaign="psychrometrics_week",
        content="single_point_demo",
    )
    assert url == (
        "https://hvac-calcs.app/duct-sizing?utm_source=linkedin&utm_medium=video"
        "&utm_campaign=psychrometrics_week&utm_content=single_point_demo"
    )
    assert build_campaign_url("https://hvac-calcs.app/", source="LinkedIn", medium="video", campaign="x", content="y") is None


def test_fixture_report_reconciles_channels_and_funnel(analytics_app):
    with analytics_app.app_context():
        user = User(email="new@example.com", trial_started_at=PERIOD_START, subscription_status="trialing")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        uid = user.id
        common = dict(anonymous_session_id="s-li", user_id=uid)
        touch = _touch(
            source="linkedin",
            medium="video",
            campaign="psychrometrics_week",
            content="single_point_demo",
            path="/duct-sizing",
        )
        _add("calculator_start", 0, tool="duct_sizing", **common, **touch)
        _add("calculator_complete", 5, tool="duct_sizing", unit_system="SI", **common, **touch)
        _add("calculator_complete", 25, tool="duct_sizing", unit_system="SI", **common, **touch)
        _add("pro_cta_view", 6, source="duct_sizing", target="duct_index_leg", cta_placement="result", **common, **touch)
        _add("pro_cta_click", 7, source="duct_sizing", target="duct_index_leg", cta_placement="result", **common, **touch)
        _add("registration_start", 8, source="duct_sizing", target="duct_index_leg", **common, **touch)
        _add("registration_complete", 9, source="duct_sizing", target="duct_index_leg", **common, **touch)
        _add("pro_tool_use", 15, tool="duct_index_leg", **common, **touch)
        _add("checkout_start", 16, **common, **touch)
        _add("subscription_active", 17, **common, **touch)

        yt = _touch(source="youtube", medium="short", campaign="psychrometrics_week", content="single_point_demo", path="/pipe")
        _add("calculator_start", 40, anonymous_session_id="s-yt", tool="pipe_sizing", **yt)

        ig = _touch(source="instagram", medium="reel", campaign="psychrometrics_week", content="single_point_demo", path="/psychro")
        _add("calculator_start", 41, anonymous_session_id="s-ig", tool="psychrometric_single", **ig)
        _add("calculator_complete", 42, anonymous_session_id="s-ig", tool="psychrometric_single", **ig)

        fb = _touch(source="facebook", medium="community", campaign="psychrometrics_week", content="single_point_answer", path="/converter")
        _add("calculator_start", 43, anonymous_session_id="s-fb", tool="unit_converter", **fb)
        _add("calculator_complete", 44, anonymous_session_id="s-fb", tool="unit_converter", **fb)

        google = _touch(host="www.google.com", path="/refrigerant", captured=True)
        _add("calculator_start", 45, anonymous_session_id="s-g", tool="refrigerant_pt", **google)
        _add("calculator_complete", 46, anonymous_session_id="s-g", tool="refrigerant_pt", **google)

        chat = _touch(host="chatgpt.com", path="/superheat", captured=True)
        _add("calculator_start", 47, anonymous_session_id="s-ai", tool="superheat_subcooling", **chat)
        _add("calculator_complete", 48, anonymous_session_id="s-ai", tool="superheat_subcooling", **chat)

        direct = _touch(path="/", captured=True)
        _add("calculator_complete", 49, anonymous_session_id="s-direct", tool="duct_sizing", **direct)

        _add("calculator_complete", 50, anonymous_session_id="s-unknown", tool="pipe_sizing")
        _add("pro_cta_view", 51, source="home", cta_placement="home")
        _add("pro_cta_click", 52, source="pricing", cta_placement="pricing")
        _add(
            "pro_cta_view",
            53,
            anonymous_session_id="s-other",
            source="duct_sizing",
            target="duct_index_leg",
            cta_placement="landing",
        )
        db.session.commit()

        report = build_report(PERIOD_START, PERIOD_END)
        text = render_markdown(report)
        totals = json.loads(re.search(r"```json\n(\{.*?\})\n```", text, re.S).group(1))
        assert totals["views_reconcile"] is True
        assert totals["clicks_reconcile"] is True
        assert totals["cta_views"] == totals["path_views"] == report.cta_views
        assert totals["cta_clicks"] == totals["path_clicks"] == report.cta_clicks
        assert totals["max_unique_completion_rate_pct"] <= 100
        assert "Activity summary" not in text
        assert "not a sequential cohort funnel" in text or "not a sequential funnel" in text
        names = {row.source for row in report.paths}
        assert "unmapped source" in names
        assert "unmapped target" in names or any(row.source == "unmapped target" for row in report.paths)
        assert "other CTA placement" in names
        assert report.google_organic_journeys == 1
        assert report.google_organic_completions == 1
        first = {row.channel: row for row in report.channels_first}
        assert "linkedin / campaign" in first
        assert "google / organic" in first
        assert "chatgpt / referral" in first
        assert "direct" in first
        assert "unknown" in first
        assert first["unknown"].landing_journeys >= 1
        assert report.previous_start == date(2026, 9, 28)
        assert report.previous_end == date(2026, 10, 4)
        assert report.previous_end < report.start
        assert (report.end - report.start) == (report.previous_end - report.previous_start)
        assert report.deltas["calculations"].startswith("0 → ")
        assert "New this period" in report.deltas["calculations"]
        paid = next(step for step in report.funnel if step.label == "Free completion → active subscription")
        assert paid.reached <= paid.eligible
        assert paid.reached == 1
        for step in report.funnel:
            assert step.reached <= step.eligible
            if step.eligible < 5:
                assert step.rate == "insufficient data"


def test_period_math_and_zero_baseline():
    assert format_delta(250, 39) == "39 → 250, +541%"
    assert format_delta(1, 0) == "0 → 1, New this period"
    assert format_delta(0, 0) == "0 → 0, No comparable baseline"
    assert format_delta(4, 8) == "8 → 4, -50%"


def test_partial_day_is_not_compared(analytics_app):
    with analytics_app.app_context():
        from app.analytics_report import london_today

        today = london_today()
        report = build_report(today, today)
        assert report.deltas["calculations"] == "No comparable baseline"
        assert "not a complete day" in report.comparison_note


def test_stripe_active_status_is_recorded_once(analytics_app):
    with analytics_app.app_context():
        user = User(email="payer@example.com", trial_started_at=PERIOD_START, subscription_status="trialing")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        note_confirmed_subscription(user.id, "trialing")
        note_confirmed_subscription(user.id, "past_due")
        assert AnalyticsEvent.query.filter_by(event_name="subscription_active").count() == 0
        note_confirmed_subscription(user.id, "active")
        note_confirmed_subscription(user.id, "active")
        assert AnalyticsEvent.query.filter_by(event_name="subscription_active").count() == 1


def test_weekly_send_stores_provider_id_and_cannot_repeat(analytics_app, monkeypatch):
    def fake_send(**kwargs):
        fake_send.last_message_id = "msg_test_1"
        return True

    monkeypatch.setattr("app.mail.mail_configured", lambda: True)
    monkeypatch.setattr("app.mail.send_email", fake_send)
    with analytics_app.app_context():
        now = datetime(2026, 10, 13, 8, 0, tzinfo=timezone.utc)
        assert send_weekly_analytics_report(now) == "sent"
        assert send_weekly_analytics_report(now) == "already-sent"
        row = AnalyticsReportRun.query.filter_by(status="sent").one()
        assert row.provider_message_id == "msg_test_1"
        assert row.attempt_count == 1
        assert row.started_at is not None
        assert row.completed_at is not None
        assert row.weekly_key == "2026-10-05"
        assert AnalyticsReportRun.query.filter_by(status="sent").count() == 1


def test_funnel_diagnostics_count_links_without_identifiers(analytics_app, client):
    secret_sessions = (
        "diag-session-ordered-9f3a",
        "diag-session-early-9f3a",
        "diag-session-mismatch-9f3a",
        "diag-session-user-a-9f3a",
        "diag-session-user-b-9f3a",
        "diag-session-nosource-9f3a",
        "diag-session-lonely-9f3a",
        "diag-session-lonely-cta-9f3a",
        "diag-session-far-9f3a",
        "diag-session-excluded-9f3a",
        "diag-session-only-9f3a",
        "diag-session-both-9f3a",
        "diag-session-excluded-login-9f3a",
    )
    start = date(2026, 10, 1)
    end = date(2026, 10, 20)
    base = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)

    def at(minutes: int) -> datetime:
        return base + timedelta(minutes=minutes)

    with analytics_app.app_context():
        assert set(_DIAGNOSTIC_EVENTS) == set(ALLOWED_EVENTS)
        owner = User(email="owner@example.com", trial_started_at=start, subscription_status="trialing")
        owner.set_password("password123")
        db.session.add(owner)
        db.session.add(AnalyticsEvent(
            event_name="calculator_complete", occurred_at=at(0),
            anonymous_session_id=secret_sessions[0], tool="duct_sizing", user_id=11,
        ))
        db.session.add(AnalyticsEvent(
            event_name="pro_cta_view", occurred_at=at(10),
            anonymous_session_id=secret_sessions[0], source="duct_sizing", target="duct_index_leg",
        ))
        db.session.add(AnalyticsEvent(
            event_name="pro_cta_view", occurred_at=at(20),
            anonymous_session_id=secret_sessions[1], source="duct_sizing",
        ))
        db.session.add(AnalyticsEvent(
            event_name="calculator_complete", occurred_at=at(30),
            anonymous_session_id=secret_sessions[1], tool="duct_sizing",
        ))
        db.session.add(AnalyticsEvent(
            event_name="calculator_complete", occurred_at=at(40),
            anonymous_session_id=secret_sessions[2], tool="pipe_sizing",
        ))
        db.session.add(AnalyticsEvent(
            event_name="pro_cta_view", occurred_at=at(50),
            anonymous_session_id=secret_sessions[2], source="duct_sizing",
        ))
        db.session.add(AnalyticsEvent(
            event_name="calculator_complete", occurred_at=at(60),
            anonymous_session_id=secret_sessions[3], tool="duct_sizing", user_id=22,
        ))
        db.session.add(AnalyticsEvent(
            event_name="pro_cta_view", occurred_at=at(70),
            anonymous_session_id=secret_sessions[4], source="duct_sizing", user_id=22,
        ))
        db.session.add(AnalyticsEvent(
            event_name="pro_cta_view", occurred_at=at(80),
            anonymous_session_id=secret_sessions[5],
        ))
        db.session.add(AnalyticsEvent(
            event_name="calculator_complete", occurred_at=at(90),
            anonymous_session_id=secret_sessions[6], tool="duct_sizing",
        ))
        db.session.add(AnalyticsEvent(
            event_name="pro_cta_view", occurred_at=at(100),
            anonymous_session_id=secret_sessions[7], source="duct_sizing",
        ))
        db.session.add(AnalyticsEvent(
            event_name="calculator_complete", occurred_at=at(110),
            anonymous_session_id=secret_sessions[8], tool="duct_sizing",
        ))
        db.session.add(AnalyticsEvent(
            event_name="pro_cta_view", occurred_at=at(110) + timedelta(days=8),
            anonymous_session_id=secret_sessions[8], source="duct_sizing",
        ))
        db.session.add(AnalyticsEvent(
            event_name="calculator_complete", occurred_at=at(120),
            anonymous_session_id=secret_sessions[9], tool="duct_sizing", excluded=True,
        ))
        db.session.add(AnalyticsEvent(
            event_name="pro_cta_view", occurred_at=at(130),
            anonymous_session_id=secret_sessions[9], source="duct_sizing", excluded=True,
        ))
        db.session.add(AnalyticsEvent(
            event_name="login", occurred_at=at(140), anonymous_session_id=secret_sessions[10],
        ))
        db.session.add(AnalyticsEvent(
            event_name="login", occurred_at=at(141), user_id=33,
        ))
        db.session.add(AnalyticsEvent(
            event_name="login", occurred_at=at(142),
            anonymous_session_id=secret_sessions[11], user_id=44,
            source="duct_sizing", target="duct_index_leg",
            first_captured=False, latest_captured=False,
        ))
        db.session.add(AnalyticsEvent(event_name="login", occurred_at=at(143)))
        db.session.add(AnalyticsEvent(
            event_name="login", occurred_at=at(144),
            anonymous_session_id=secret_sessions[12], excluded=True,
        ))
        db.session.commit()
        report = build_report(start, end)
        by_event = {row.event_name: row for row in report.event_diagnostics}
        assert list(by_event) == list(_DIAGNOSTIC_EVENTS)
        login = by_event["login"]
        assert login.total == 5
        assert login.with_session == 3
        assert login.with_user == 2
        assert login.with_both == 1
        assert login.with_neither == 1
        assert login.distinct_sessions == 3
        assert login.distinct_users == 2
        assert login.with_source == 1
        assert login.with_target == 1
        assert login.with_capture_flag == 1
        assert login.excluded == 1
        assert login.with_both + login.with_neither + (login.with_session - login.with_both) + (login.with_user - login.with_both) == login.total
        completes = by_event["calculator_complete"]
        assert completes.total == 7
        assert completes.excluded == 1
        assert completes.with_session == 7
        assert completes.with_user == 2
        assert completes.with_both == 2
        assert completes.with_neither == 0
        assert completes.distinct_sessions == 7
        assert completes.distinct_users == 2
        assert completes.with_source == 0
        views = by_event["pro_cta_view"]
        assert views.total == 8
        assert views.excluded == 1
        assert views.with_source == 7
        assert views.with_target == 1
        link = report.link_diagnostics
        assert link.same_journey_ordered == 1
        assert link.same_journey_cta_first == 1
        assert link.same_session_source_mismatch == 1
        assert link.same_user_session_differs == 1
        assert link.cta_without_source == 1
        assert link.completion_without_cta == 5
        assert link.cta_without_completion == 6
        assert link.outside_window == 1
        assert link.same_journey_ordered + link.completion_without_cta == 6
        text = render_markdown(report)
        html = render_email_html(report)
        assert "19. Funnel diagnostics" in text
        assert "Same journey and correct order | 1" in text
        assert "Outside the 7-day window | 1" in text
        for secret in secret_sessions:
            assert secret not in text
            assert secret not in html
        assert "owner@example.com" not in text
        assert "owner@example.com" not in html

    logged_in = client.post("/login", data={"email": "owner@example.com", "password": "password123"})
    assert logged_in.status_code in {302, 303}
    page = client.get(f"/admin/analytics/?start={start.isoformat()}&end={end.isoformat()}")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "Funnel diagnostics" in body
    assert "Same journey and correct order" in body
    assert "diag-session-ordered-9f3a" not in body
    assert "owner@example.com" not in body


def test_capture_rejects_unusable_utm_without_calling_it_direct(analytics_app):
    with analytics_app.test_request_context("/?utm_source=not%20a%20source"):
        capture_campaign()
        record_analytics_event("calculator_start", tool="duct_sizing")
        row = AnalyticsEvent.query.one()
        assert row.utm_source is None
        assert row.first_channel == "unknown"
        assert row.first_channel != "direct"
