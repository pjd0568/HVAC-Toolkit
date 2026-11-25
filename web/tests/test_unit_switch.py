"""SI/IP toggle must convert GET query values, not only the unit labels."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from hvac_engine import units as eng_units

from app.unit_switch import convert_value, rewrite_next_url


def test_power_converts_between_si_and_ip():
    ip = convert_value("power", "50", from_system="SI", to_system="IP")
    assert ip is not None
    assert float(ip) == pytest.approx(eng_units.from_si("power", 50.0, "IP"), rel=1e-6)
    assert float(ip) != 50.0

    back = convert_value("power", ip, from_system="IP", to_system="SI")
    assert back is not None
    assert float(back) == pytest.approx(50.0, rel=1e-4)


def test_delta_t_scales_without_fahrenheit_offset():
    assert convert_value("temperature_difference", "20", from_system="SI", to_system="IP") == "36"
    assert convert_value("temperature_difference", "36", from_system="IP", to_system="SI") == "20"


def test_lwt_uses_absolute_temperature_conversion():
    ip = convert_value("temperature", "50", from_system="SI", to_system="IP")
    assert ip is not None
    assert float(ip) == pytest.approx(122.0, abs=0.05)


def test_rewrite_pipe_url_preserves_physical_load():
    nxt = (
        "/tools/chilled-water-pipe-sizing?mode=from_load&application=chw"
        "&fluid=water&material=carbon_steel&glycol_pct=0&load=50&delta_t=6"
        "&lwt=6&flow_ls=4.0&selected_dn=50"
    )
    rewritten = rewrite_next_url(nxt, from_system="SI", to_system="IP")
    qs = parse_qs(urlsplit(rewritten).query)
    assert float(qs["load"][0]) == pytest.approx(eng_units.from_si("power", 50.0, "IP"), rel=1e-6)
    assert float(qs["delta_t"][0]) == pytest.approx(10.8, abs=0.05)
    assert float(qs["lwt"][0]) == pytest.approx(42.8, abs=0.05)
    assert qs["flow_ls"][0] == "4.0"
    assert qs["selected_dn"][0] == "50"


def test_set_units_redirect_converts_pipe_query(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["units"] = "SI"
    nxt = (
        "/tools/chilled-water-pipe-sizing?mode=from_load&application=lthw"
        "&fluid=water&material=carbon_steel&glycol_pct=0&load=50&delta_t=20"
        "&lwt=50&flow_ls=1.0&selected_dn=50"
    )
    res = client.post(
        "/preferences/units",
        data={"system": "IP", "next": nxt},
        follow_redirects=False,
    )
    assert res.status_code in (302, 303)
    location = res.headers["Location"]
    qs = parse_qs(urlsplit(location).query)
    assert float(qs["load"][0]) == pytest.approx(eng_units.from_si("power", 50.0, "IP"), rel=1e-6)
    assert float(qs["load"][0]) != 50.0

    page = client.get(location)
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "Btu/h" in body
    # The converted load must appear in the form — not the original 50.
    assert f'value="{qs["load"][0]}"' in body or f"value='{qs['load'][0]}'" in body
