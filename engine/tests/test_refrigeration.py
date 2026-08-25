"""Tests for hvac_engine.refrigeration — requires CoolProp."""

from __future__ import annotations

import math

import pytest

pytest.importorskip("CoolProp")

from hvac_engine import refrigeration as ref


def test_list_includes_r744_unavailable():
    rows = ref.list_refrigerants()
    r744 = next(r for r in rows if r.id == "r744")
    assert not r744.available


def test_available_fluids_resolve():
    for info in ref.list_refrigerants(include_unavailable=False):
        # One saturation call must succeed
        table = ref.pt_table(info.id, t_min_c=0.0, t_max_c=0.0, t_step_k=1.0)
        assert len(table.rows) == 1
        assert not table.rows[0].skipped


def test_r744_rejected():
    with pytest.raises(ValueError, match="not available"):
        ref.pt_table("r744")
    with pytest.raises(ValueError, match="not available"):
        ref.size_dx_pipe(10.0, "r744", -5.0, 40.0)


def test_pt_r32_negligible_glide():
    table = ref.pt_table("r32", t_min_c=-10.0, t_max_c=10.0, t_step_k=5.0)
    assert len(table.rows) == 5
    for row in table.rows:
        assert not row.skipped
        assert abs(row.p_bubble_barg - row.p_dew_barg) < 0.05
    assert table.max_glide_k < 0.1
    assert not table.glide_notable


def test_pt_r407c_shows_glide():
    table = ref.pt_table("r407c", t_min_c=0.0, t_max_c=0.0, t_step_k=1.0)
    row = table.rows[0]
    assert not row.skipped
    # At fixed T, bubble P > dew P for zeotropes
    assert row.p_bubble_barg > row.p_dew_barg
    assert table.glide_notable
    assert table.max_glide_k >= 0.1


def test_pt_barg_anchor_r134a():
    # R-134a Psat @ 0 °C ≈ 2.928 bara → ≈ 1.915 barg
    table = ref.pt_table("r134a", t_min_c=0.0, t_max_c=0.0, t_step_k=1.0)
    row = table.rows[0]
    assert abs(row.p_bubble_barg - 1.915) < 0.05


def test_acr_catalogue_ids():
    assert len(ref.ACR_CATALOGUE) >= 7
    q = ref.find_acr("1/4")
    assert q is not None
    assert q.id_mm == pytest.approx(6.35 - 1.6)
    assert q.area_m2 > 0


def test_mass_flow_and_velocity_r32():
    result = ref.size_dx_pipe(
        cooling_capacity_kw=10.0,
        refrigerant_id="r32",
        evaporating_temp_c=-5.0,
        condensing_temp_c=45.0,
        subcooling_k=5.0,
        superheat_k=5.0,
        line_type="suction",
    )
    assert result.mass_flow_kg_s == pytest.approx(
        10.0 / result.delta_h_kj_kg, rel=1e-6
    )
    assert result.delta_h_kj_kg > 100.0
    assert result.recommended is not None
    # Velocity reconstructs from m_dot / (rho A)
    rec = result.recommended
    v_check = result.mass_flow_kg_s / (result.density_kg_m3 * rec.entry.area_m2)
    assert rec.velocity_ms == pytest.approx(v_check, rel=1e-9)
    assert rec.in_ideal_band or rec.status_velocity in ("green", "amber", "red")


def test_liquid_line_slower_than_suction():
    common = dict(
        cooling_capacity_kw=10.0,
        refrigerant_id="r32",
        evaporating_temp_c=-5.0,
        condensing_temp_c=45.0,
        subcooling_k=5.0,
        superheat_k=5.0,
    )
    suc = ref.size_dx_pipe(**common, line_type="suction")
    liq = ref.size_dx_pipe(**common, line_type="liquid")
    # Same size: liquid denser → lower velocity
    size = "1/2"
    vs = next(r for r in suc.rows if r.entry.nominal_inch == size).velocity_ms
    vl = next(r for r in liq.rows if r.entry.nominal_inch == size).velocity_ms
    assert vl < vs


def test_oil_return_red_status():
    assert ref.velocity_status(3.0, "suction", "horizontal") == "red"
    assert ref.velocity_status(7.0, "suction", "upflow_riser") == "red"
    assert ref.velocity_status(11.0, "suction", "upflow_riser") == "green"


def test_r454b_and_r513a_pt():
    for rid in ("r454b", "r513a"):
        table = ref.pt_table(rid, t_min_c=0.0, t_max_c=5.0, t_step_k=5.0)
        assert any(not r.skipped for r in table.rows)


def test_unknown_refrigerant():
    with pytest.raises(ValueError, match="unknown"):
        ref.get_refrigerant("r999")


def test_saturation_at_pressure_r134a():
    # ~1.915 barg ≈ 0 °C for R-134a
    t_bub, t_dew = ref.saturation_at_pressure_barg("r134a", 1.915)
    assert abs(t_bub - 0.0) < 0.4
    assert abs(t_dew - t_bub) < 0.05


def test_diagnose_sh_sc_healthy_r32():
    # Pick pressures near -5 °C dew and 45 °C bubble for R-32, then apply SH/SC.
    from CoolProp.CoolProp import PropsSI

    fluid = "R32"
    p_lo = PropsSI("P", "T", (-5.0) + 273.15, "Q", 1, fluid)
    p_hi = PropsSI("P", "T", 45.0 + 273.15, "Q", 0, fluid)
    p_lo_barg = p_lo / 1e5 - ref.P_ATM_BAR
    p_hi_barg = p_hi / 1e5 - ref.P_ATM_BAR
    result = ref.diagnose_sh_sc(
        "r32",
        p_low_barg=p_lo_barg,
        p_high_barg=p_hi_barg,
        t_suction_c=-5.0 + 8.0,
        t_liquid_c=45.0 - 6.0,
    )
    assert result.superheat_k == pytest.approx(8.0, abs=0.15)
    assert result.subcooling_k == pytest.approx(6.0, abs=0.15)
    assert result.superheat.status == "green"
    assert result.subcooling.status == "green"


def test_classify_floodback_and_high_sc():
    assert ref.classify_superheat(2.0).status == "red"
    assert ref.classify_superheat(2.0).headline == "Floodback risk"
    assert ref.classify_subcooling(20.0).status == "red"


def test_diagnose_rejects_inverted_pressures():
    with pytest.raises(ValueError, match="high-side"):
        ref.diagnose_sh_sc(
            "r32",
            p_low_barg=10.0,
            p_high_barg=5.0,
            t_suction_c=10.0,
            t_liquid_c=20.0,
        )
