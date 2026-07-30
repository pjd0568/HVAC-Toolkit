"""Tests for app.units: the SI/IP system toggle and the airflow (m³/h vs m³/s)
display toggle layered on top of it.
"""

from __future__ import annotations

import pytest

from app.units import (
    DEFAULT_FLOW_UNIT,
    UnitView,
    get_flow_unit,
    set_flow_unit,
)


@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config.update(TESTING=True)
    return application


def test_flow_unit_defaults_to_m3h(app):
    with app.test_request_context("/"):
        assert get_flow_unit() == DEFAULT_FLOW_UNIT
        assert DEFAULT_FLOW_UNIT == "m3h"


def test_set_flow_unit_persists_valid_choice(app):
    with app.test_request_context("/"):
        set_flow_unit("m3s")
        assert get_flow_unit() == "m3s"


def test_set_flow_unit_ignores_invalid_choice(app):
    with app.test_request_context("/"):
        set_flow_unit("m3s")
        set_flow_unit("bogus")
        assert get_flow_unit() == "m3s"


def test_si_m3h_view_matches_canonical_value():
    U = UnitView("SI", "m3h")
    assert U.sym("vol_flow") == "m³/h"
    assert U.fmt("vol_flow", 1800.0) == "1800"
    assert U.to_si("vol_flow", 1800.0) == pytest.approx(1800.0)


def test_si_m3s_view_converts_display_and_round_trips():
    U = UnitView("SI", "m3s")
    assert U.sym("vol_flow") == "m³/s"
    # 1800 m3/h == 0.5 m3/s
    assert U.fmt("vol_flow", 1800.0) == "0.500"
    assert U.to_si("vol_flow", 0.5) == pytest.approx(1800.0)
    # round trip: SI canonical -> display -> SI canonical
    si_value = 3600.0
    display = U.conv("vol_flow", si_value)
    assert U.to_si("vol_flow", display) == pytest.approx(si_value)


def test_ip_view_ignores_flow_unit_preference():
    """IP airflow is always CFM, regardless of the m³/h vs m³/s toggle."""
    U_m3h = UnitView("IP", "m3h")
    U_m3s = UnitView("IP", "m3s")
    assert U_m3h.sym("vol_flow") == "CFM"
    assert U_m3s.sym("vol_flow") == "CFM"
    assert U_m3h.fmt("vol_flow", 1800.0) == U_m3s.fmt("vol_flow", 1800.0)
    assert U_m3h.to_si("vol_flow", 1000.0) == pytest.approx(U_m3s.to_si("vol_flow", 1000.0))


def test_flow_unit_does_not_affect_other_quantities():
    U = UnitView("SI", "m3s")
    assert U.sym("mass_flow") == "kg/s"
    assert U.fmt("temperature", 21.0) == "21.0"


def test_invalid_flow_unit_falls_back_to_default():
    U = UnitView("SI", "not-a-real-unit")
    assert U.flow_unit == DEFAULT_FLOW_UNIT
    assert U.sym("vol_flow") == "m³/h"
