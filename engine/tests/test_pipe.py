"""Tests for hvac_engine.pipe — see specs/SPEC-pipe-sizing.md."""

from __future__ import annotations

import math

import pytest

from hvac_engine import pipe as p


def test_flow_from_load_100kw_20k():
  props = p.fluid_properties("water", 60.0)
  flow = p.flow_from_load(100.0, 20.0, props)
  expected_mass = 100_000.0 / (props.cp_j_kgk * 20.0)
  assert flow.mass_flow_kg_s == pytest.approx(expected_mass, rel=1e-6)
  assert flow.volume_flow_m3h == pytest.approx(expected_mass / props.density_kg_m3 * 3600.0, rel=1e-6)


def test_water_properties_interpolation_25c():
  props = p.fluid_properties("water", 25.0)
  at20 = p.fluid_properties("water", 20.0)
  at30 = p.fluid_properties("water", 30.0)
  assert at30.density_kg_m3 < props.density_kg_m3 < at20.density_kg_m3
  assert at30.dynamic_viscosity_pa_s < props.dynamic_viscosity_pa_s < at20.dynamic_viscosity_pa_s


def test_glycol_catalogue_concentration_only():
  props = p.fluid_properties("ppg", 10.0, concentration_pct=33)
  assert props.concentration_pct == 33
  with pytest.raises(ValueError):
    p.fluid_properties("water", 20.0, concentration_pct=33)
  with pytest.raises(ValueError):
    p.fluid_properties("ppg", 20.0, concentration_pct=30)


def test_glycol_freeze_point_per_concentration():
  assert p.glycol_freeze_point_c("ppg", 33) == pytest.approx(-15, abs=0.1)
  assert p.glycol_freeze_point_c("epg", 32) == pytest.approx(-20, abs=0.1)


def test_hydratech_ppg_33pct_20c_matches_datasheet():
  """Spot-check against Hydratech_Glycol_Data.xlsx (PPG / Coolflow NTP, 33%, 20 °C)."""
  props = p.fluid_properties("ppg", 20.0, concentration_pct=33)
  assert props.density_kg_m3 == pytest.approx(1032, abs=0.5)
  assert props.dynamic_viscosity_pa_s == pytest.approx(0.0037668, rel=0.01)
  assert props.cp_j_kgk == pytest.approx(3840, abs=5)
  assert props.freezing_point_c == pytest.approx(-15, abs=0.1)


def test_evaluate_dn25_steel_hand_check():
  props = p.fluid_properties("water", 20.0)
  vol_m3h = 3.6  # 1 l/s
  entry = next(e for e in p.catalogue_for("carbon_steel") if e.dn == 25)
  result = p.evaluate_size(vol_m3h, entry, props, "carbon_steel", "lthw")

  d = entry.id_m
  v = (vol_m3h / 3600.0) / (math.pi * d ** 2 / 4.0)
  re = v * d / props.kinematic_viscosity_m2_s
  f = p._swamee_jain(re, p.ROUGHNESS["carbon_steel"], d)
  dp_dl = f * (1.0 / d) * (props.density_kg_m3 * v ** 2 / 2.0)

  assert result.velocity_ms == pytest.approx(v, rel=1e-6)
  assert result.friction_rate_pa_per_m == pytest.approx(dp_dl, rel=1e-6)


@pytest.mark.parametrize(
    "dp,expected",
    [
        (50.0, "red"),
        (100.0, "amber"),
        (125.0, "amber"),
        (175.0, "amber"),
        (250.0, "green"),
        (350.0, "amber"),
        (450.0, "amber"),
        (550.0, "red"),
    ],
)
def test_friction_status(dp, expected):
  assert p.friction_status(dp) == expected


@pytest.mark.parametrize(
    "dn,velocity,expected",
    [
        (25, 1.0, "green"),
        (25, 0.5, "red"),
        (25, 1.6, "red"),
        (80, 1.5, "green"),
        (80, 2.0, "amber"),
        (80, 2.6, "red"),
        (200, 2.0, "green"),
        (200, 3.1, "red"),
    ],
)
def test_velocity_status_per_dn(dn, velocity, expected):
  assert p.velocity_status(velocity, dn) == expected


def test_dairy_ss_uses_dn_label():
  entry = p.catalogue_for("dairy_ss")[0]
  assert entry.label.startswith("DN")


@pytest.mark.parametrize(
    "value,min_i,max_i,abs_max,expected",
    [
        (0.5, 0.5, 1.4, 1.5, "green"),
        (0.4, 0.5, 1.4, 1.5, "amber"),   # oversized
        (1.45, 0.5, 1.4, 1.5, "amber"),  # commercial push
        (1.5, 0.5, 1.4, 1.5, "red"),
        (200.0, 40.0, 285.0, 300.0, "green"),
        (30.0, 40.0, 285.0, 300.0, "amber"),   # low pd — oversized
        (290.0, 40.0, 285.0, 300.0, "amber"),  # pushed
        (300.0, 80.0, 250.0, 300.0, "red"),
    ],
)
def test_band_status(value, min_i, max_i, abs_max, expected):
  assert p.band_status(value, min_i, max_i, abs_max) == expected


def test_pipe_mass_per_m_positive():
  entry = next(e for e in p.catalogue_for("carbon_steel") if e.dn == 50)
  assert p.pipe_mass_per_m("carbon_steel", entry) > 0


def test_default_selected_dn_recommended():
  props = p.fluid_properties("water", 60.0)
  flow = p.flow_from_load(100.0, 20.0, props)
  rows = p.evaluate_catalogue(flow.volume_flow_m3h, "carbon_steel", props, "lthw")
  idx = p.recommended_index(rows, "lthw")
  assert idx is not None
  dn = p.default_selected_dn(rows, "lthw")
  assert dn == rows[idx].entry.dn
  assert p.friction_status(rows[idx].friction_rate_pa_per_m) == "green"
  assert p.velocity_status(rows[idx].velocity_ms, rows[idx].entry.dn) != "red"


def test_catalogue_has_green_velocity_for_typical_lthw():
  props = p.fluid_properties("water", 60.0)
  flow = p.flow_from_load(100.0, 20.0, props)
  rows = p.evaluate_catalogue(flow.volume_flow_m3h, "carbon_steel", props, "lthw")
  greens = [r for r in rows if r.status_velocity == "green"]
  assert greens, "expected at least one green velocity for a typical LTHW duty"


def test_trim_catalogue_view_window():
  props = p.fluid_properties("water", 60.0)
  flow = p.flow_from_load(100.0, 20.0, props)
  rows = p.evaluate_catalogue(flow.volume_flow_m3h, "carbon_steel", props, "lthw")
  assert len(rows) > 6
  trimmed = p.trim_catalogue_view(rows, "lthw")
  assert len(trimmed) < len(rows)
  rec = p.recommended_index(rows, "lthw")
  assert rec is not None
  assert rows[rec].entry.dn in {r.entry.dn for r in trimmed}
  # Focused window — should not start at the smallest catalogue DN
  assert trimmed[0].entry.dn > rows[0].entry.dn
  full_dns = {r.entry.dn for r in rows}
  trim_dns = {r.entry.dn for r in trimmed}
  assert trim_dns.issubset(full_dns)


def test_mean_water_temperature():
  assert p.mean_water_temperature_c(50.0, 20.0) == 60.0


def test_volume_flow_conversions():
  assert p.volume_flow_ls(3.6) == pytest.approx(1.0)
  assert p.volume_flow_m3h_from_ls(1.0) == pytest.approx(3.6)


def test_flow_from_load_rejects_non_positive():
  props = p.fluid_properties("water", 20.0)
  with pytest.raises(ValueError):
    p.flow_from_load(0.0, 10.0, props)
  with pytest.raises(ValueError):
    p.flow_from_load(10.0, 0.0, props)
