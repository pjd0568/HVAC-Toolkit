"""Tests for the homepage psychrometric teaser API and hydrate helpers."""

from __future__ import annotations

import pytest

from app.teaser import (
    form_from_teaser_si,
    resolve_teaser_state,
    session_point_from_si,
    teaser_payload,
)


@pytest.fixture
def client(app):
    return app.test_client()


def test_homepage_includes_teaser(client):
    res = client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'id="psychro-teaser"' in html
    assert "Free psychrometric calculator" in html
    assert "psychro_teaser.js" in html
    assert "application/ld+json" in html


def test_teaser_api_si_rh(client):
    res = client.post(
        "/api/psychro/teaser",
        json={"system": "SI", "t_db": 21, "prop": "rh", "val": 50, "pressure": 101.325},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["system"] == "SI"
    assert data["outputs"]["t_wb"]["symbol"] == "°C"
    assert data["outputs"]["h"]["symbol"] == "kJ/kg"
    assert data["si"]["t_db"] == pytest.approx(21.0)
    assert data["si"]["rh"] == pytest.approx(0.5, rel=1e-3)


def test_teaser_api_ip_converts_and_recalculates(client):
    res = client.post(
        "/api/psychro/teaser",
        json={"system": "IP", "t_db": 70, "prop": "rh", "val": 50},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["outputs"]["t_dp"]["symbol"] == "°F"
    assert data["outputs"]["h"]["symbol"] == "Btu/lb"
    assert data["symbols"]["pressure"] == "inHg"
    # 70°F ≈ 21.11°C
    assert data["si"]["t_db"] == pytest.approx((70 - 32) * 5 / 9, abs=0.01)


def test_teaser_api_rejects_bad_rh(client):
    res = client.post(
        "/api/psychro/teaser",
        json={"system": "SI", "t_db": 21, "prop": "rh", "val": 150},
    )
    assert res.status_code == 400
    assert res.get_json()["ok"] is False


def test_teaser_api_wet_bulb(client):
    res = client.post(
        "/api/psychro/teaser",
        json={"system": "SI", "t_db": 25, "prop": "twb", "val": 18},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["si"]["t_wb"] == pytest.approx(18.0, abs=0.05)


def test_resolve_and_form_roundtrip():
    state, U = resolve_teaser_state(system="SI", t_db=21, prop="rh", val=50, pressure=101.325)
    payload = teaser_payload(state, U, prop="rh", val=50)
    form = form_from_teaser_si(payload["si"], "SI")
    assert form["s_prop"] == "rh"
    assert float(form["s_t"]) == pytest.approx(21.0, abs=0.05)
    assert float(form["s_val"]) == pytest.approx(50.0, abs=0.05)
    point = session_point_from_si(payload["si"], "A")
    assert point["label"] == "A"
    assert point["rh"] == pytest.approx(0.5, rel=1e-3)


def test_hydrate_teaser_requires_login(client):
    res = client.post(
        "/psychrometrics/hydrate-teaser",
        json={
            "system": "SI",
            "si": {
                "t_db": 21,
                "rh": 0.5,
                "t_wb": 14,
                "t_dp": 10,
                "w": 0.007,
                "h": 40,
                "v": 0.84,
                "rho": 1.2,
                "p_w": 1.2,
                "p": 101.325,
                "prop": "rh",
            },
        },
    )
    # Unauthenticated app traffic is redirected to login.
    assert res.status_code in (302, 401)
