# Functional Spec — Air Treatment Processes Module

**Module:** `hvac_engine.processes`
**Status:** v1.0 — 2 July 2026
**Depends on:** `hvac_engine.psychrometrics` (SPEC-psychrometrics.md)
**Clean-room note:** Written from public engineering standards only; coded from this
spec with no other codebase open.

## Purpose

Model the air-side processes that make up an air handling unit: mixing, sensible
heating/cooling, dehumidifying cooling coils, humidification — individually and
chained into a full AHU duty simulation with per-stage duties and state points.

## Method sources (public standards)

- ASHRAE Handbook — Fundamentals (2017), Chapter 1: moist air property relations,
  adiabatic mixing of two airstreams (eqn 44 region), enthalpy/humidity-ratio
  balances for heating, cooling and humidification processes.
- Standard coil practice (ASHRAE HOF Ch.1 / HVAC Systems & Equipment coil chapters,
  CIBSE Guide B): apparatus dew point (ADP), bypass factor (BF) and contact
  factor (CF = 1 − BF) representation of dehumidifying coils; sensible heat
  ratio (SHR).
- Evaporative cooling as a constant-thermodynamic-wet-bulb process with a
  saturation effectiveness (public textbook treatment).

## Conventions

- All flows are **dry-air mass flow** m_da in kg/s. Conversion from volumetric flow
  uses specific volume v at the relevant state: m_da = V̇ / v. (Web layer's concern.)
- Duties in kW; positive = heat added to the air, negative = heat removed.
- Moisture rates (condensate, steam, evaporated water) in kg/s, reported positive.
- Pressure constant through a process (fan pressure rises ignored for state points).
- All states are `PsychroState`; all outputs are frozen dataclasses.

## Functions

### `mix(state_a, m_da_a, state_b, m_da_b, p) -> MixResult`
Adiabatic mixing, mass and energy balance on dry air:
w_mix = (m_a·w_a + m_b·w_b)/(m_a+m_b); h_mix likewise. State resolved from (h, w).
If the mixed point falls above the saturation curve (possible mixing warm humid with
cold air — fog region), settle to the saturated state with the same enthalpy
(iterate t where h_sat(t) = h_mix); report `condensate` = m_total·(w_mix − w_sat)
and `fog = True`.
`MixResult(state, m_da, fog, condensate)`

### `sensible(state_in, m_da, t_out) -> ProcessResult`
Constant-w heating or cooling. Validation: resulting state must not be
supersaturated (for cooling, t_out ≥ dew point; otherwise the caller wants
`cooling_coil`). q = m_da·(h_out − h_in).
`ProcessResult(state, q_sensible, q_latent=0, q_total)`

### `cooling_coil(state_on, m_da, *, t_adp, t_off | bypass_factor) -> CoilResult`
Real-world apparatus-dew-point / bypass-factor coil. A cooling coil cannot set
dry-bulb and moisture independently: air-on `(T1, W1)` and ADP on the saturation
curve lock a straight process chord; off-coil air sits on that chord.

Provide **`t_adp`** plus either **`t_off`** (how far along the chord) or
**`bypass_factor`** in `[0, 1)`:
- `BF = (T_off − T_ADP) / (T_on − T_ADP)`  (or rearrange for `T_off` when BF given)
- Wet coil (`T_ADP` < entering dew point):
  `W_off = W_ADP + BF · (W_on − W_ADP)` with `W_ADP = W_s(T_ADP)`
- Dry coil (`T_ADP` ≥ entering dew point): constant-`W` sensible cooling to `T_off`
- Leaving RH is a **result** (typically ~0.90–0.95 for a wet coil), not an input.

Legacy convenience for AHU simulation: `t_off` + `rh_off` (no `t_adp`) solves for
the ADP at the saturation intersection of the chord through the prescribed
off-coil point, then runs the forward model.

Duties:
- q_total = m_da·(h_off − h_on)  (negative)
- q_sensible = m_da·(h(t_off, w_on) − h(t_on, w_on))
- q_latent = q_total − q_sensible
- SHR = q_sensible / q_total
- condensate = m_da·(w_on − w_off)
- contact factor CF = 1 − BF
- **frost_risk = True if ADP ≤ 0 °C**

`CoilResult(state, q_sensible, q_latent, q_total, shr, condensate, t_adp,
contact_factor, bypass_factor, frost_risk)`

### `steam_humidify(state_in, m_da, w_out) -> HumidifyResult`
Isothermal steam injection (dry saturated steam adds ~negligible sensible heat at
typical injection rates; modelled at constant dry bulb — the standard chart
treatment). Validation: w_out ≥ w_in; result must not supersaturate.
steam_rate = m_da·(w_out − w_in); q_latent = m_da·(h_out − h_in).
`HumidifyResult(state, steam_rate, q_latent)`

### `adiabatic_humidify(state_in, m_da, effectiveness) -> AdiabaticResult`
Evaporative/adiabatic humidifier along the constant thermodynamic wet-bulb line:
t_out = t_in − ε·(t_in − t_wb,in), 0 < ε ≤ 1. w_out from (t_out, twb = t_wb,in).
water_rate = m_da·(w_out − w_in). Enthalpy change is small and non-zero (wet-bulb,
not enthalpy, is conserved exactly); report q_total for completeness.
`AdiabaticResult(state, water_rate, q_total)`

### `fan_gain(state_in, m_da, power_kw | dt) -> ProcessResult`
Sensible pick-up across a fan at constant moisture content. Given absorbed power:
ΔT = P / (m_da · c_p,moist), with c_p,moist = 1.006 + 1.86·W kJ/kg·K (the moist-air
specific heat implied by HOF eqn 30). For an in-airstream motor (typical AHU plug
fan) effectively the whole electrical input appears as heat in the air; assume
fraction = 1 unless the motor is external.

Where fan power is unknown at design stage, estimate from **specific fan power**:
P (W) = SFP (W per l/s) × V̇ (l/s). Building Regulations Approved Document L
Volume 2 (2021, England) maximum SFPs for new buildings: central balanced system
with heating and cooling 2.0 W/(l/s); heating only 1.9; other central balanced 1.5;
zonal supply 1.1; zonal extract 0.5. Using the AD L limit is a conservative
(upper-bound) estimate of fan gain. (Web layer converts SFP → kW; the engine takes
power or ΔT only.)

### `simulate_ahu(config) -> AhuResult`
Chains stages in fixed order, any of which may be absent:

1. **Intake/mixing:** outdoor state (+ return state + %OA by dry-air mass) → mixed
2. **Frost coil (preheat):** sensible to t_frost_off (winter protection)
3. **Supply fan, if blow-through:** fan_gain before the coils
4. **Cooling coil:** to (t_off, rh_off)
5. **Heating coil (reheat):** sensible to t_reheat
6. **Humidifier:** steam to w target or %RH target at current t, or adiabatic by ε
7. **Supply fan, if draw-through (default):** fan_gain as the final element

Fan position matters: a blow-through fan raises the on-coil condition (adding to
the cooling coil duty in summer); a draw-through fan adds its gain after the coil
(raising the supply temperature and eroding reheat requirement instead). Stage
label `FAN` when blow-through; when draw-through the gain is shown on the `SUP`
stage.

Input flow is supply volumetric flow V̇ at the final state or dry-air mass flow
directly. Output: ordered list of labelled stage points
(`OA`, `RA`, `MA`, `FROST`, `CC`, `HC`, `HUM`, `SUP`) with the process result and
duty for each active stage, plus totals (net heating kW, net cooling kW, moisture
added/removed kg/s) and any frost-risk flag raised by the cooling coil or by a
mixed/off-coil state below 0 °C saturation.

### `design_ahu_to_supply(config) -> AhuResult`
Inverse of `simulate_ahu`: instead of specifying the off-coil condition and reading
off the supply, the user specifies the **required supply (off-unit) condition** — the
state delivered into the room — and the solver derives the intermediate stages that
reach it. This is the everyday design question ("I need to supply air at X; what must
the coil do?").

Intake is identical to `simulate_ahu`: outdoor state (+ return + %OA by dry-air mass)
mix to the on-coil condition A. Given the required supply state D, compare its moisture
content w_sup with the on-coil w_on:

- **w_sup > w_on** (supply wetter than on-coil): unreachable by cooling alone — a
  cooling coil can only remove moisture. Raise with a clear message that the duty needs
  humidification (not yet sized by this tool).
- **w_sup ≈ w_on** (within ~0.01 g/kg, no net moisture change): a purely sensible duty.
  If t_sup < t_A it is sensible (dry) cooling A→D; if t_sup > t_A it is heating-only
  A→D; if equal, no duty.
- **w_sup < w_on** (dehumidification): off-coil C holds the supply moisture at a
  target off-coil RH (`coil_rh_off`, default **0.90** — matching `simulate_ahu` and
  typical wet-coil practice). `coil_rh_off=1.0` recovers the idealised CF = 1 case
  (saturated at the supply dew point). The path is:
  A → B saturation onset (sensible cooling at constant w_on to the on-coil dew point) →
  C off-coil (at w_sup and coil_rh_off) →
  D supply (sensible reheat at constant w_sup to the supply dry bulb when needed).
  B is a zero-duty chart waypoint; the whole coil duty A→C is reported on the CC
  stage; the reheat C→D on the HC stage when t_off < t_sup.

Coil duty (dehumidification): q_total = m_da·(h_C − h_A) (negative); q_sensible =
m_da·(h(t_C, w_on) − h(t_A, w_on)); q_latent = q_total − q_sensible; condensate =
m_da·(w_on − w_sup). **frost_risk = True if the off-coil temperature (supply dew point)
≤ 0 °C.**

Optional supply fan gain (same SFP/kW basis as `fan_gain`): a **draw-through** fan sits
after reheat, so its rise is added last and the reheat coil targets t_sup − ΔT_fan so
the air arrives at t_sup after the fan; a **blow-through** fan raises the on-coil
condition A before the coil. Reachability note added if the fan gain alone overshoots the
reheat requirement.

Output is the same `AhuResult` shape as `simulate_ahu` — ordered labelled stages
(`OA`, `RA`, `MA`, `FAN`, `SAT`, `CC`, `HC`, `SUP`) with per-stage duty, totals, and any
frost/fog/reachability warnings. The final `SUP` stage equals the requested supply
state (within tolerance); a warning is raised if it cannot.

## Second-variable input convention (web layer)

Every psychrometric **state** input across all tools uses the same pair: **dry-bulb
temperature as the base**, plus one selectable second variable — **relative humidity
(%), wet-bulb temperature (°C), moisture ratio (g/kg), or dew-point temperature (°C)**.
These map to the `state()` property pairs (`rh`, `twb`, `w`, `tdp`) in
SPEC-psychrometrics.md. The selector is identical on the single-point, mixed-air,
cooling-coil (on- and off-coil) and AHU (outdoor, return, required-supply) inputs so
the interaction is consistent everywhere.

## Acceptance tests

- **Mixing mass balance:** equal dry-air flows of (30 °C, w=0.010) and (10 °C,
  w=0.005) → w_mix = 0.0075 exactly; h_mix = mean of enthalpies; t_mix within
  0.2 K of 20 °C (slightly off the arithmetic mean — chart mixing is along h, w).
- **Mixing fog case:** −5 °C/90% mixed 50:50 with 25 °C/60% → if computed point is
  supersaturated, result is saturated (rh = 1.0) and condensate ≥ 0.
- **Sensible energy balance:** 1 kg/s heated 10→30 °C at w = 0.005:
  q = h(30, 0.005) − h(10, 0.005) ≈ 20.3 kW (±0.3). Cooling below dew point raises.
- **Coil worked case:** 28 °C/50% on-coil, ADP 9 °C, t_off 12 °C at 1 kg/s dry air:
  leaving RH ≈ 0.90 (±0.03); q_total ≈ −26.4 kW (±1.5); condensate > 0; 0 < SHR < 1;
  BF = (12−9)/(28−9); frost_risk False. Legacy `t_off=12, rh_off=0.90` recovers the
  same chord with ADP between 4 and 12 °C.
- **Coil frost case:** ADP ≤ 0 °C (e.g. on-coil 16 °C/30%, ADP −2 °C, t_off 2 °C) →
  frost_risk True.
- **Coil validation:** t_off > t_on raises; t_off < t_ADP raises; legacy rh_off giving
  w_off > w_on raises.
- **Steam:** 20 °C/30% to w giving 50% RH: t unchanged (±0.01), steam_rate > 0.
- **Adiabatic:** 28 °C/30%, ε = 0.85: t_wb conserved (±0.05 K), t drops, w rises.
- **AHU chain:** winter case (OA −5/90%, RA 21/50%, 30% OA, frost coil to 5 °C,
  reheat to 21 °C, steam to 40% RH at 21 °C): stage list ordered, each stage's
  inlet = previous stage's outlet, net heating > 0, moisture added > 0.
- **AHU summer case:** OA 28/50%, RA 23/50%, 30% OA, coil to 12/90%, reheat 14 °C:
  cooling negative, reheat positive, supply state = reheat outlet.
- **Supply-driven cool+reheat:** on-coil 28/50%, required supply 14 °C/90%: w_sup <
  w_on → dehumidification; off-coil = supply dew point saturated; cooling < 0, reheat > 0,
  condensate > 0; final SUP within 0.1 K / 0.05 g/kg of the requested supply.
- **Supply-driven sensible cooling:** on-coil 26 °C/8 g/kg, supply 18 °C at the same
  moisture (both above the dew point): single sensible CC stage, no reheat, no condensate.
- **Supply-driven heating only:** on-coil 15 °C/50%, supply 22 °C at the same moisture:
  single HC stage, cooling = 0, heating > 0.
- **Supply-driven reachability:** supply moisture above on-coil moisture raises
  (needs humidification).
- **Supply-driven frost:** required supply with a dew point below 0 °C → frost_risk True.
- **Supply-driven continuity:** each stage inlet = previous stage outlet; OA/RA mix to MA.
