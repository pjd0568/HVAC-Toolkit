"""Free→Pro stage CTA after three successful free calculations."""

from __future__ import annotations

import pytest

from app.stage_cta import DISMISS_KEY, STAGE_THRESHOLD

PUBLIC_PSY = "/tools/psychrometric-calculator"
PUBLIC_DUCT = "/tools/duct-sizing-calculator"
PUBLIC_PIPE = "/tools/chilled-water-pipe-sizing"
V2_PSY = "/v2/psychrometrics/single-point"

PSY_VALID = {
    "action": "calculate",
    "s_t": "21",
    "s_prop": "rh",
    "s_val": "50",
    "altitude": "0",
}
PIPE_QS = (
    "mode=from_load&application=lthw&fluid=water&material=carbon_steel"
    "&glycol_pct=0&load=100&delta_t=20&lwt=50&selected_dn=50"
)
DUCT_QS = "volume=0.5&basis=velocity&target_value=6&shape=circular"


@pytest.fixture
def client(app):
    return app.test_client()


def _psy(client, path=PUBLIC_PSY):
    return client.post(path, data=PSY_VALID, follow_redirects=True)


def _count_key(tool: str) -> str:
    return f"stage_cta_count:{tool}"


def _dismiss_key(tool: str) -> str:
    return f"stage_cta_dismissed:{tool}"


def _clear_stage(client, tool: str):
    with client.session_transaction() as sess:
        sess.pop(_count_key(tool), None)
        sess.pop(_dismiss_key(tool), None)
        if tool == "psychrometric_single":
            sess.pop("psychro_single_calc_count", None)
            sess.pop(DISMISS_KEY, None)
            sess.pop("psychro_single_points", None)


def _session_count(client, tool: str) -> int:
    with client.session_transaction() as sess:
        return int(sess.get(_count_key(tool), 0) or 0)


def test_psychro_third_calc_shows_top_stage_cta(client, app):
    app.config["REGISTRATION_OPEN"] = True
    _clear_stage(client, "psychrometric_single")
    for _ in range(STAGE_THRESHOLD - 1):
        html = _psy(client).get_data(as_text=True)
        assert 'data-cta-placement="stage"' not in html

    html = _psy(client).get_data(as_text=True)
    assert 'data-cta-placement="stage"' in html
    assert "full psychrometric suite" in html.lower()
    assert "sample-pro-report.pdf" in html
    assert html.index('data-cta-placement="stage"') < html.index("public-calc-surface")


def test_pipe_third_calc_promotes_circuit_calculator(client):
    _clear_stage(client, "pipe_sizing")
    for n in range(1, STAGE_THRESHOLD):
        page = client.get(f"{PUBLIC_PIPE}?{PIPE_QS}")
        assert page.status_code == 200
        assert 'data-cta-placement="stage"' not in page.get_data(as_text=True)
        assert _session_count(client, "pipe_sizing") == n

    page = client.get(f"{PUBLIC_PIPE}?{PIPE_QS}")
    html = page.get_data(as_text=True)
    assert 'data-cta-placement="stage"' in html
    assert "pipe circuit" in html.lower() or "pump head" in html.lower()
    assert "sample-pro-report.pdf" in html
    assert html.index('data-cta-placement="stage"') < html.index("public-calc-surface")


def test_duct_third_calc_promotes_index_leg(client):
    _clear_stage(client, "duct_sizing")
    for _ in range(STAGE_THRESHOLD - 1):
        page = client.get(f"{PUBLIC_DUCT}?{DUCT_QS}")
        assert 'data-cta-placement="stage"' not in page.get_data(as_text=True)

    page = client.get(f"{PUBLIC_DUCT}?{DUCT_QS}")
    html = page.get_data(as_text=True)
    assert 'data-cta-placement="stage"' in html
    assert "index leg" in html.lower()
    assert "sample-pro-report.pdf" in html
    assert html.index('data-cta-placement="stage"') < html.index("public-calc-surface")


def test_duct_api_calculate_signals_stage_cta(client):
    _clear_stage(client, "duct_sizing")
    for _ in range(STAGE_THRESHOLD - 1):
        res = client.get(f"/duct-sizing/api/state?{DUCT_QS}&intent=calculate")
        assert res.status_code == 200
        assert res.get_json().get("show_stage_cta") is False

    res = client.get(f"/duct-sizing/api/state?{DUCT_QS}&intent=calculate")
    assert res.get_json().get("show_stage_cta") is True


def test_dismiss_stage_cta_for_pipe(client):
    _clear_stage(client, "pipe_sizing")
    for _ in range(STAGE_THRESHOLD):
        client.get(f"{PUBLIC_PIPE}?{PIPE_QS}")
    assert 'data-cta-placement="stage"' in client.get(f"{PUBLIC_PIPE}?{PIPE_QS}").get_data(as_text=True)

    dismissed = client.post(
        "/preferences/dismiss-stage-cta",
        data={"tool": "pipe_sizing", "next": PUBLIC_PIPE},
        follow_redirects=True,
    )
    assert dismissed.status_code == 200
    assert 'data-cta-placement="stage"' not in dismissed.get_data(as_text=True)
    assert 'data-cta-placement="stage"' not in client.get(f"{PUBLIC_PIPE}?{PIPE_QS}").get_data(as_text=True)


def test_suite_access_hides_stage_cta(client, app):
    _clear_stage(client, "psychrometric_single")
    for _ in range(STAGE_THRESHOLD):
        _psy(client)
    app.config["ACCESS_DEV_TIER"] = "pro"
    try:
        assert 'data-cta-placement="stage"' not in client.get(PUBLIC_PSY).get_data(as_text=True)
    finally:
        app.config["ACCESS_DEV_TIER"] = None


def test_sample_pro_report_is_public(client):
    res = client.get("/static/examples/sample-pro-report.pdf")
    assert res.status_code == 200
    assert res.data.startswith(b"%PDF")


def test_v2_psychro_shows_stage_cta_at_top(client, app):
    app.config["REGISTRATION_OPEN"] = True
    _clear_stage(client, "psychrometric_single")
    for _ in range(STAGE_THRESHOLD):
        _psy(client, V2_PSY)
    html = client.get(V2_PSY).get_data(as_text=True)
    assert 'data-cta-placement="stage"' in html
    assert "full psychrometric suite" in html.lower()
    assert html.index('data-cta-placement="stage"') < html.index("psychro-layout")


def test_bare_duct_page_has_no_immediate_pro_card(client):
    """Duct/pipe no longer show a permanent bottom Pro card before the threshold."""
    page = client.get(PUBLIC_DUCT)
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert 'data-cta-placement="stage"' not in html
    assert 'data-cta-placement="result"' not in html
