"""Free→Pro stage CTA for psychrometric single-point only."""

from __future__ import annotations

import pytest

from app.psychro_stage_cta import (
    COUNT_KEY,
    DISMISS_KEY,
    STAGE_THRESHOLD,
    psychro_single_calc_count,
)

PUBLIC = "/tools/psychrometric-calculator"
V2 = "/v2/psychrometrics/single-point"


@pytest.fixture
def client(app):
    return app.test_client()

VALID = {
    "action": "calculate",
    "s_t": "21",
    "s_prop": "rh",
    "s_val": "50",
    "altitude": "0",
}
INVALID = {
    "action": "calculate",
    "s_t": "21",
    "s_prop": "rh",
    "s_val": "150",
    "altitude": "0",
}


def _calc(client, path=PUBLIC, data=None):
    return client.post(path, data=data or VALID, follow_redirects=True)


def test_first_two_calcs_have_results_without_stage_cta(client):
    for n in (1, 2):
        page = _calc(client)
        html = page.get_data(as_text=True)
        assert page.status_code == 200
        assert "Resolved states" in html
        assert "psychro-stage-cta" not in html
        assert "Continue this job in Pro" not in html
        with client.session_transaction() as sess:
            assert sess.get(COUNT_KEY) == n


def test_third_calc_shows_stage_cta_on_public_and_v2(client, app):
    app.config["REGISTRATION_OPEN"] = True
    for path in (PUBLIC, V2):
        with client.session_transaction() as sess:
            sess.pop(COUNT_KEY, None)
            sess.pop(DISMISS_KEY, None)
            sess.pop("psychro_single_points", None)

        for _ in range(STAGE_THRESHOLD - 1):
            page = _calc(client, path)
            assert "psychro-stage-cta" not in page.get_data(as_text=True)

        page = _calc(client, path)
        html = page.get_data(as_text=True)
        assert "psychro-stage-cta" in html
        assert 'data-cta-placement="stage"' in html
        assert 'data-cta-source="psychrometric_single"' in html
        assert 'data-cta-target="interactive_chart"' in html
        assert "Continue this job in Pro" in html
        assert "full single-point" in html
        assert "/register" in html
        assert "interactive-chart" in html
        # Static public pro_next must stay suppressed for psychrometrics.
        if path == PUBLIC:
            assert "Need process lines, AHU analysis" not in html


def test_invalid_post_does_not_increment(client):
    _calc(client)
    with client.session_transaction() as sess:
        assert sess.get(COUNT_KEY) == 1
    bad = client.post(PUBLIC, data=INVALID, follow_redirects=True)
    html = bad.get_data(as_text=True)
    assert bad.status_code == 200
    assert "error" in html.lower() or "must" in html.lower() or "between" in html.lower() or "invalid" in html.lower() or "range" in html.lower()
    with client.session_transaction() as sess:
        assert sess.get(COUNT_KEY) == 1


def test_teaser_api_does_not_bump_count(client):
    _calc(client)
    with client.session_transaction() as sess:
        assert sess.get(COUNT_KEY) == 1
    teaser = client.post(
        "/api/psychro/teaser",
        json={"system": "SI", "t_db": 21, "prop": "rh", "val": 50},
    )
    assert teaser.status_code == 200
    assert teaser.get_json()["ok"] is True
    with client.session_transaction() as sess:
        assert sess.get(COUNT_KEY) == 1
    page = client.get(PUBLIC)
    assert "psychro-stage-cta" not in page.get_data(as_text=True)


def test_unit_preference_does_not_bump(client):
    _calc(client)
    with client.session_transaction() as sess:
        assert sess.get(COUNT_KEY) == 1
    units = client.post(
        "/preferences/units",
        data={"system": "IP", "next": PUBLIC},
        follow_redirects=False,
    )
    assert units.status_code in (302, 303)
    with client.session_transaction() as sess:
        assert sess.get(COUNT_KEY) == 1


def test_get_after_threshold_keeps_cta_without_extra_bump(client):
    for _ in range(STAGE_THRESHOLD):
        _calc(client)
    with client.session_transaction() as sess:
        assert sess.get(COUNT_KEY) == STAGE_THRESHOLD
    page = client.get(PUBLIC)
    html = page.get_data(as_text=True)
    assert "psychro-stage-cta" in html
    with client.session_transaction() as sess:
        assert sess.get(COUNT_KEY) == STAGE_THRESHOLD


def test_dismiss_hides_cta_for_rest_of_session(client):
    for _ in range(STAGE_THRESHOLD):
        _calc(client)
    assert "psychro-stage-cta" in client.get(PUBLIC).get_data(as_text=True)

    dismissed = client.post(
        PUBLIC,
        data={"action": "dismiss_stage_cta"},
        follow_redirects=True,
    )
    html = dismissed.get_data(as_text=True)
    assert dismissed.status_code == 200
    assert "psychro-stage-cta" not in html
    with client.session_transaction() as sess:
        assert sess.get(DISMISS_KEY) is True
        assert sess.get(COUNT_KEY) >= STAGE_THRESHOLD

    again = _calc(client)
    assert "psychro-stage-cta" not in again.get_data(as_text=True)


def test_suite_access_hides_stage_cta(client, app):
    for _ in range(STAGE_THRESHOLD):
        _calc(client)
    app.config["ACCESS_DEV_TIER"] = "pro"
    try:
        page = client.get(PUBLIC)
        assert "psychro-stage-cta" not in page.get_data(as_text=True)
        page = _calc(client)
        assert "psychro-stage-cta" not in page.get_data(as_text=True)
    finally:
        app.config["ACCESS_DEV_TIER"] = None


def test_other_free_tools_keep_static_pro_next(client):
    page = client.get("/tools/duct-sizing-calculator")
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "pro-next" in html
    assert "psychro-stage-cta" not in html


def test_helpers_default_outside_request(app):
    assert psychro_single_calc_count() == 0
