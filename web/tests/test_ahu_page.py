"""AHU design is one page: fresh + return flows, mixed air, predicted process."""

from __future__ import annotations

import pytest

PAGE = "/v2/psychrometrics/ahu"

SUMMER = {
    "altitude": "0",
    "oa_t": "28", "oa_prop": "rh", "oa_val": "50", "oa_flow": "1500",
    "ra_t": "22", "ra_prop": "rh", "ra_val": "50", "ra_flow": "3500",
    "sup_t": "18", "sup_prop": "rh", "sup_val": "58",
    "coil_kind": "chw", "fluid_t": "6", "approach": "3", "adp_t": "9",
    "fan_pos": "draw", "fan_sfp": "2.0", "fan_kw": "",
}

WINTER = {
    "altitude": "0",
    "oa_t": "-5", "oa_prop": "rh", "oa_val": "90", "oa_flow": "1500",
    "ra_t": "21", "ra_prop": "rh", "ra_val": "50", "ra_flow": "3500",
    "sup_t": "21", "sup_prop": "rh", "sup_val": "40",
    "coil_kind": "chw", "fluid_t": "6", "approach": "3", "adp_t": "9",
    "fan_pos": "draw", "fan_sfp": "1.9", "fan_kw": "",
}


@pytest.fixture
def client(app):
    app.config["ACCESS_DEV_TIER"] = "pro"
    return app.test_client()


def test_page_is_one_form_not_a_wizard(client):
    page = client.get(PAGE)
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Fresh air" in html
    assert "Return air" in html
    assert "Off AHU" in html
    assert "System volume is the fresh-air flow" in html
    assert 'name="oa_flow"' in html
    assert 'name="ra_flow"' in html
    assert 'name="flow"' not in html
    assert "data-v2-wizard" not in html
    assert "Design season" not in html
    assert "Part L type" in html
    assert "Central H&amp;C — 2.0" in html or "Central H&C — 2.0" in html


def test_summer_predicts_dehumidification_and_reheat(client):
    page = client.post(PAGE, data=SUMMER)
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Dehumidification and reheat" in html
    assert "System volume" in html
    assert "Total cooling" in html
    assert "Total heat added" in html
    assert "Fan gain" in html
    assert "from SFP" in html
    assert "CC —" in html
    assert "HC —" in html


def test_winter_predicts_heating_and_humidification(client):
    page = client.post(PAGE, data=WINTER)
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Heating and humidification" in html
    assert "HUM —" in html


def test_custom_sfp_is_kept(client):
    data = dict(SUMMER, fan_sfp="1.2")
    page = client.post(PAGE, data=data)
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert 'value="custom" selected' in html or 'value="custom"  selected' in html
    assert 'name="fan_sfp" value="1.2"' in html


def test_zero_flows_are_rejected(client):
    data = dict(SUMMER, oa_flow="0", ra_flow="0")
    page = client.post(PAGE, data=data)
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Enter a fresh-air flow" in html
    assert "Dehumidification and reheat" not in html
