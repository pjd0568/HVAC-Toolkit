# Functional Spec — Psychrometrics Module

**Module:** `hvac_engine.psychrometrics`
**Status:** v1.0 — 2 July 2026
**Clean-room note:** This spec is written from public engineering standards only.
The implementation is coded from this spec with no other codebase open.

## Purpose

Compute thermodynamic properties of moist air at a given barometric pressure, and
resolve a complete psychrometric state from any valid pair of independent properties.
This module is the foundation for AHU process modelling (mixing, coils, humidification),
which will be specified separately in SPEC-ahu-processes.md.

## Method sources (public standards)

- ASHRAE Handbook — Fundamentals (2017), Chapter 1 "Psychrometrics":
  Hyland & Wexler saturation pressure correlations (eqns 5 and 6), humidity ratio
  (eqn 22), enthalpy (eqn 30), specific volume (eqn 26), wet-bulb relation
  (eqns 33 and 35), relative humidity definition (eqn 12), degree of saturation.
- Hyland, R.W. & Wexler, A. (1983), ASHRAE Transactions 89(2A) — original source of
  the saturation correlations.

## Conventions

- SI internally: temperature °C, pressure kPa, humidity ratio kg/kg dry air,
  enthalpy kJ/kg dry air, specific volume m³/kg dry air.
- Default barometric pressure: 101.325 kPa (sea level). All functions accept
  pressure as a parameter. A standard-atmosphere altitude → pressure helper is
  provided (`pressure_from_altitude`) for the common case of a site elevation;
  callers who have a directly measured/specified barometric pressure may still
  supply it themselves instead.
- Enthalpy datum: 0 kJ/kg for dry air at 0 °C; consistent with ASHRAE eqn 30.
- Valid range: −60 °C to +90 °C dry bulb (correlation validity range).
  Out-of-range inputs raise `ValueError`.
- Unit conversion to/from imperial happens in a separate conversions module,
  never inside this one.

## Functions

### `saturation_pressure(t_c) -> kPa`
Hyland-Wexler correlation. Over ice for t < 0 °C (HOF eqn 5), over liquid water for
t ≥ 0 °C (HOF eqn 6). Input °C, converted internally to Kelvin.

### `humidity_ratio_from_vapour_pressure(p_w, p) -> kg/kg`
W = 0.621945 · p_w / (p − p_w)   (HOF eqn 22)

### `saturation_humidity_ratio(t_c, p) -> kg/kg`
W_s = humidity_ratio_from_vapour_pressure(saturation_pressure(t_c), p)

### `vapour_pressure_from_humidity_ratio(w, p) -> kPa`
Inverse of eqn 22: p_w = p · W / (0.621945 + W)

### `relative_humidity(t_c, w, p) -> fraction 0..1`
φ = p_w / p_ws(t)   (HOF eqn 12, mole-fraction form at same T and p)

### `humidity_ratio_from_rh(t_c, rh, p) -> kg/kg`
p_w = φ · p_ws(t), then eqn 22.

### `enthalpy(t_c, w) -> kJ/kg dry air`
h = 1.006·t + W·(2501 + 1.86·t)   (HOF eqn 30)

### `dry_bulb_from_enthalpy(h, w) -> °C`
Algebraic inverse of eqn 30: t = (h − 2501·W) / (1.006 + 1.86·W)

### `specific_volume(t_c, w, p) -> m³/kg dry air`
v = 0.287042 · (t + 273.15) · (1 + 1.607858·W) / p   (HOF eqn 26, p in kPa)

### `density(t_c, w, p) -> kg/m³`
ρ = (1 + W) / v  (moist air mass per unit volume)

### `humidity_ratio_from_wet_bulb(t_c, t_wb_c, p) -> kg/kg`
HOF eqn 33 (t_wb ≥ 0 °C):
W = ((2501 − 2.326·t_wb)·W_s(t_wb) − 1.006·(t − t_wb)) / (2501 + 1.86·t − 4.186·t_wb)
HOF eqn 35 (t_wb < 0 °C):
W = ((2830 − 0.24·t_wb)·W_s(t_wb) − 1.006·(t − t_wb)) / (2830 + 1.86·t − 2.1·t_wb)

### `wet_bulb(t_c, w, p) -> °C`
Numerical inversion of the above (bisection between −60 °C and t; W is monotonic
increasing in t_wb). Tolerance 1e−8 kg/kg.

### `dew_point(w, p) -> °C`
Numerical inversion of saturation_pressure over p_w (bisection −60..90 °C,
tolerance 1e−9 kPa). No polynomial approximation — exact consistency with the
saturation correlation is preferred over speed.

### `state(p=101.325, **pair) -> PsychroState`
Resolve a full state from dry bulb plus one of: `rh` (0..1), `w`, `twb`, `tdp`, `h`;
or from (`h`, `w`). Returns a frozen dataclass:

`PsychroState(t_db, t_wb, t_dp, w, rh, h, v, rho, p_w, p)`

Validation: rh outside 0..1, w < 0, supersaturated inputs (w > W_s at t) raise
`ValueError` with a clear message.

### `pressure_from_altitude(z_m) -> kPa`
Standard-atmosphere design pressure at site elevation (HOF eqn 3, US standard
atmosphere, troposphere): p = 101.325 · (1 − 2.25577×10⁻⁵ · z)^5.2559, z in metres.
Valid −500 to 9000 m (`Z_MIN`/`Z_MAX`); out-of-range raises `ValueError`. This is
the standard *design* pressure for a given elevation, not a live weather reading —
used by the web layer as the default way to resolve barometric pressure from a
user-entered site altitude.

## Acceptance tests (public anchor values)

Saturation pressure (HOF Table 3 values):
- 0 °C → 0.6112 kPa (±0.001)
- 20 °C → 2.3392 kPa (±0.002)
- 25 °C → 3.1699 kPa (±0.002)
- −20 °C → 0.10326 kPa (±0.0005)
- 50 °C → 12.3513 kPa (±0.01)

Standard example (HOF ch.1 example 1-type): t = 40 °C, t_wb = 20 °C, 101.325 kPa
→ W ≈ 0.00650 kg/kg (±0.0002), h ≈ 56.7 kJ/kg (±0.3), v ≈ 0.896 m³/kg (±0.003),
t_dp ≈ 7.4 °C (±0.3) (cross-checked against the Magnus approximation, which gives
7.45 °C for the same vapour pressure).

Round-trip consistency: for a grid of states, wet_bulb(state from twb) returns the
input twb within 0.01 K; dew_point(humidity_ratio_from_rh(t, 1.0, p), p) returns t
within 0.01 K (saturation self-consistency).

Standard atmosphere (HOF Table 1 anchor values): pressure_from_altitude(0) = 101.325
kPa exactly; pressure_from_altitude(1000) ≈ 89.88 kPa (±0.05); pressure_from_altitude(2000)
≈ 79.50 kPa (±0.05).
