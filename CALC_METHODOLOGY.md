# Calculation Methodology

Faithful extract of what the HVAC Toolkit calculation engine currently does.
This document does **not** validate correctness or suitability — it records
formulas, constants, assumptions, validation, and stated references as they
appear in code and specs.

**Canonical engine location:** `engine/src/hvac_engine/` (pure Python, SI).  
**Web layer:** converts units, orchestrates calls, applies safety margins; does
not re-implement physics except for dry-air mass-flow from volume flow and
weather wet-bulb ranking helpers.

**Not present:** building room-load / heat-gain / tonnage sizing. Closest load
math is hydronic `Q = ṁ · Cp · ΔT` → flow, and AHU coil duties in kW.

---

## Summary of calculations covered

| # | Calculation | Category | Primary location |
|---|-------------|----------|------------------|
| 1 | Saturation vapour pressure (Hyland–Wexler) | Psychrometrics | `psychrometrics.saturation_pressure` |
| 2 | Humidity ratio ↔ vapour pressure | Psychrometrics | `humidity_ratio_from_vapour_pressure` / inverse |
| 3 | Relative humidity ↔ humidity ratio | Psychrometrics | `relative_humidity` / `humidity_ratio_from_rh` |
| 4 | Moist-air enthalpy | Psychrometrics | `enthalpy` / `dry_bulb_from_enthalpy` |
| 5 | Specific volume & moist-air density | Psychrometrics | `specific_volume` / `density` |
| 6 | Humidity ratio from wet-bulb | Psychrometrics | `humidity_ratio_from_wet_bulb` |
| 7 | Wet-bulb (bisection) | Psychrometrics | `wet_bulb` |
| 8 | Dew point (bisection) | Psychrometrics | `dew_point` |
| 9 | Barometric pressure from altitude (ISA) | Psychrometrics | `pressure_from_altitude` |
| 10 | Full psychrometric state resolution | Psychrometrics | `state` / `_from_w` |
| 11 | Dry-air mass flow from volume flow | Air processes (web) | `web/.../psychro._m_da` |
| 12 | Adiabatic mixing (+ fog settlement) | Air processes | `processes.mix` |
| 13 | Sensible heating/cooling (constant W) | Air processes | `processes.sensible` |
| 14 | Cooling coil (off-coil defined) | Air processes | `processes.cooling_coil` |
| 15 | Apparatus dew point / contact & bypass factor | Air processes | `_apparatus_dew_point` |
| 16 | Steam humidification | Air processes | `steam_humidify` |
| 17 | Adiabatic (evaporative) humidification | Air processes | `adiabatic_humidify` |
| 18 | Fan sensible gain | Air processes | `fan_gain` |
| 19 | AHU duty simulation (forward) | Air processes | `simulate_ahu` |
| 20 | Supply-driven AHU design (inverse) | Air processes | `ahu_design.design_ahu_to_supply` |
| 21 | Darcy friction factor (Swamee–Jain) | Duct / pipe shared method | `fluid_mechanics.swamee_jain` |
| 22 | Circular duct velocity & friction rate | Duct sizing | `velocity_circular` / `friction_rate_circular` |
| 23 | Velocity pressure (air) | Duct sizing | `duct.velocity_pressure` |
| 24 | Circular duct size solver | Duct sizing | `size_circular` / `propose_circular` |
| 25 | Rectangular equivalent diameter (Huebscher) | Duct sizing | `equivalent_diameter_rectangular` |
| 26 | Rectangular duct sizing | Duct sizing | `size_rectangular` / `propose_rectangular` |
| 27 | Flat-oval area, perimeter, De | Duct sizing | `equivalent_diameter_flat_oval` etc. |
| 28 | Flat-oval sizing & catalogue snap | Duct sizing | `size_flat_oval` / `propose_flat_oval` / snap helpers |
| 29 | Flex-duct friction derate | Duct sizing | `apply_flex_derate` |
| 30 | Duct dimension snap / round to increment | Duct sizing | `snap_to_increment` / `round_to_increment` |
| 31 | Duct traffic-light status | Duct sizing | `duct.status` |
| 32 | Duct fitting / straight / accessory Δp | Duct fittings | `fittings.*` |
| 33 | Index-leg total + safety margin % | Duct (web) | `web/.../duct` leg builder |
| 34 | Fluid properties (water / glycol) | Pipe / hydronics | `pipe.fluid_properties` |
| 35 | Flow from thermal load | Pipe / hydronics | `flow_from_load` |
| 36 | Pipe velocity, Re, friction rate | Pipe / hydronics | `evaluate_size` |
| 37 | Velocity / friction status bands | Pipe / hydronics | `velocity_status` / `friction_status` |
| 38 | Recommended DN selection | Pipe / hydronics | `recommended_index` |
| 39 | Pipe shell mass per metre | Pipe / hydronics | `pipe_mass_per_m` |
| 40 | Velocity pressure (fluid) | Pipe / hydronics | `pipe.velocity_pressure` |
| 41 | Hydrostatic / pump head breakdown | Pipe / hydronics | `hydrostatic_pressure_pa` / `head_breakdown` |
| 42 | Pipe fitting / straight / device Δp | Pipe fittings | `pipe_fittings.*` |
| 43 | System total + safety margin % | Pipe (web) | `web/.../pipe` system builder |
| 44 | Design DB percentiles + MCWB | Climate | `climate.design_conditions` |
| 45 | Extreme annual Gumbel return values | Climate | `gumbel_return_value` / `extreme_series` |
| 46 | Extreme wet-bulb via enthalpy ranking | Climate (web) | `weather_client._year_wet_bulb_extremes` |
| 47 | SI ↔ IP display conversion | Units | `units.to_si` / `from_si` |
| 48 | Head pressure display triplet | Units | `units.head_pressure_triplet` |
| 49 | Multi-unit converter | Units | `converter.convert_all` |

---

## Cross-cutting notes (as implemented)

### Units in the engine

| Domain | Typical units |
|--------|----------------|
| Psychrometrics / AHU | °C, kPa, kg/kg dry air, kJ/kg dry air, m³/kg dry air, kg/s dry air, kW |
| Duct | m³/h, m, m/s, Pa/m, Pa, kg/m³, m²/s |
| Pipe | m³/h, m, m/s, Pa/m, Pa, kg/m³, Pa·s, J/(kg·K), kW |
| Climate | °C (SI throughout) |

**Inconsistency (as-is):** Psychrometrics computes moist-air density from state;
duct sizing defaults to fixed standard-air density `ρ = 1.2 kg/m³` and does not
use site altitude or psychrometric state. Pipe friction uses fluid density from
property tables. Barometric pressure is in **kPa**; duct/pipe pressure drops are
in **Pa**.

### Shared friction-factor method

Both `duct` and `pipe` import `fluid_mechanics.swamee_jain` (identical formula;
regression test asserts they cannot diverge).

---

## 1. Psychrometrics

**File:** `engine/src/hvac_engine/psychrometrics.py`  
**Spec:** `specs/SPEC-psychrometrics.md`  
**Stated references:** ASHRAE Handbook — Fundamentals (2017) Chapter 1; Hyland & Wexler (1983).

### 1.1 Saturation vapour pressure

**What it does:** Computes saturation pressure of water vapour over ice (T < 0 °C)
or liquid water (T ≥ 0 °C).

**Formula / logic:**

Over ice (HOF eqn 5), T in kelvin, p in Pa then converted to kPa:

```
ln(p) = C1/T + C2 + C3·T + C4·T² + C5·T³ + C6·T⁴ + C7·ln(T)
p_kPa = exp(ln(p)) / 1000
```

Over liquid water (HOF eqn 6):

```
ln(p) = C8/T + C9 + C10·T + C11·T² + C12·T³ + C13·ln(T)
p_kPa = exp(ln(p)) / 1000
```

**Variables:** `t_c` dry-bulb (°C); `T = t_c + 273.15` (K); result kPa.

**Constants (Hyland–Wexler):**

| Set | Values |
|-----|--------|
| Ice `_ICE` | −5.6745359×10³, 6.3925247, −9.677843×10⁻³, 6.2215701×10⁻⁷, 2.0747825×10⁻⁹, −9.484024×10⁻¹³, 4.1635019 |
| Water `_WATER` | −5.8002206×10³, 1.3914993, −4.8640239×10⁻², 4.1764768×10⁻⁵, −1.4452093×10⁻⁸, 6.5459673 |

**Assumptions:** Phase switch exactly at 0 °C; no metastable liquid below freezing.

**Source:** `saturation_pressure`

**Validation:** `T_MIN ≤ t_c ≤ T_MAX` with `T_MIN = −60`, `T_MAX = 90` (°C).

**Reference:** ASHRAE HOF eqns 5/6; Hyland & Wexler (1983) — stated in module docstring.

---

### 1.2 Humidity ratio ↔ partial vapour pressure

**What it does:** Converts between humidity ratio W and partial vapour pressure p_w.

**Formulas (HOF eqn 22):**

```
W = 0.621945 · p_w / (p − p_w)
p_w = p · W / (0.621945 + W)
```

**Variables:** `W` kg water / kg dry air; `p_w`, `p` kPa; default `p = P_ATM = 101.325` kPa.

**Constant:** `_MW_RATIO = 0.621945` (molecular mass ratio water vapour : dry air).

**Assumptions:** Ideal-gas mixture of dry air and water vapour; fixed barometric default sea level unless caller passes `p`.

**Source:** `humidity_ratio_from_vapour_pressure`, `vapour_pressure_from_humidity_ratio`

**Validation:** `p_w ≥ 0`; `p_w < p`; `W ≥ 0`.

**Reference:** ASHRAE HOF eqn 22 — stated in code.

---

### 1.3 Saturation humidity ratio & relative humidity

**What it does:** `W_s = f(p_ws(T), p)`; `φ = p_w / p_ws`; `W` from `φ` and T.

**Formulas:**

```
W_s = humidity_ratio_from_vapour_pressure(saturation_pressure(t_c), p)
φ = vapour_pressure_from_humidity_ratio(W, p) / saturation_pressure(t_c)
W = humidity_ratio_from_vapour_pressure(φ · saturation_pressure(t_c), p)
```

**Source:** `saturation_humidity_ratio`, `relative_humidity`, `humidity_ratio_from_rh`

**Validation:** RH must be in `[0, 1]`.

**Reference:** HOF eqn 12 for RH — stated in code.

---

### 1.4 Enthalpy

**What it does:** Specific enthalpy of moist air per kg dry air; inverse for dry-bulb.

**Formulas (HOF eqn 30):**

```
h = 1.006 · t + W · (2501 + 1.86 · t)
t = (h − 2501 · W) / (1.006 + 1.86 · W)
```

Also used when resolving state from `(t_db, h)`:

```
W = (h − 1.006 · t_db) / (2501 + 1.86 · t_db)
```

**Variables:** `h` kJ/kg dry air; `t` °C; `W` kg/kg.

**Constants:** dry-air Cp ≈ 1.006 kJ/(kg·K); latent heat / vapour terms 2501 and 1.86 (as in HOF eqn 30).

**Assumptions:** Linear ASHRAE approximate enthalpy correlation (not a full IAPWS property model).

**Source:** `enthalpy`, `dry_bulb_from_enthalpy`, and `state` branch for key `"h"`

**Reference:** ASHRAE HOF eqn 30 — stated in code.

---

### 1.5 Specific volume and density

**What it does:** Specific volume of moist air per kg dry air; moist density.

**Formulas (HOF eqn 26 for v):**

```
v = 0.287042 · (t + 273.15) · (1 + 1.607858 · W) / p
ρ = (1 + W) / v
```

**Variables:** `v` m³/kg dry air; `ρ` kg moist air / m³; `p` kPa.

**Constants:** 0.287042, 1.607858 (HOF eqn 26 coefficients as coded).

**Source:** `specific_volume`, `density`

**Reference:** ASHRAE HOF eqn 26 — stated in code.

---

### 1.6 Humidity ratio from thermodynamic wet-bulb

**What it does:** Computes W from dry-bulb and wet-bulb using HOF wet-bulb equations.

**Formulas:**

Let `W_s_wb = saturation_humidity_ratio(t_wb, p)`.

If `t_wb ≥ 0`:

```
num = (2501 − 2.326 · t_wb) · W_s_wb − 1.006 · (t_db − t_wb)
den = 2501 + 1.86 · t_db − 4.186 · t_wb
W = num / den
```

If `t_wb < 0`:

```
num = (2830 − 0.24 · t_wb) · W_s_wb − 1.006 · (t_db − t_wb)
den = 2830 + 1.86 · t_db − 2.1 · t_wb
W = num / den
```

**Source:** `_w_from_wet_bulb_raw`, `humidity_ratio_from_wet_bulb`

**Validation:** Ranges on T and T_wb; `t_wb ≤ t_db`; rejects `W < 0` (below saturation curve).

**Reference:** ASHRAE HOF eqns 33/35 — stated in code.

---

### 1.7 Wet-bulb temperature (inversion)

**What it does:** Bisects wet-bulb so that `_w_from_wet_bulb_raw(t_db, mid, p) = W`.

**Logic:** Bisection on `[T_MIN, t_db]`, up to 200 iterations, stop when `hi − lo < 1e−9`.

**Source:** `wet_bulb`

**Reference:** Inversion of HOF 33/35 — stated in code.

---

### 1.8 Dew-point temperature (inversion)

**What it does:** Finds T_dp such that `saturation_pressure(T_dp) = p_w(W, p)`.

**Logic:** Bisection on `[T_MIN, T_MAX]`, same iteration/tolerance as wet-bulb.

**Source:** `dew_point`

**Validation:** Rejects if p_w outside saturation pressure at T_MIN/T_MAX.

**Reference:** not documented beyond inversion of saturation_pressure (HOF implied).

---

### 1.9 Pressure from altitude (standard atmosphere)

**What it does:** Design barometric pressure at site elevation (not live weather p).

**Formula (HOF Ch.1 eqn 3 / US Standard Atmosphere troposphere):**

```
p = 101.325 · (1 − 2.25577×10⁻⁵ · z)^5.2559
```

**Variables:** `z` metres above sea level; `p` kPa.

**Constants:** `P_ATM = 101.325`; `_ISA_LAPSE_COEFF = 2.25577e-5` (1/m); `_ISA_EXPONENT = 5.2559`.

**Assumptions:** Standard troposphere lapse model; design pressure only.

**Source:** `pressure_from_altitude`

**Validation:** `Z_MIN = −500` … `Z_MAX = 9000` m.

**Reference:** ASHRAE HOF (2017) Ch.1 eqn 3 — stated in code.

---

### 1.10 Full psychrometric state

**What it does:** Builds `PsychroState` (DB, WB, DP, W, RH, h, v, ρ, p_w, p) from a valid property pair.

**Accepted pairs:** `(t_db, rh) | (t_db, w) | (t_db, twb) | (t_db, tdp) | (t_db, h) | (h, w)`.

**Logic:** Resolve W (or t from h,W), then `_from_w`. Supersaturation rejected if `W > W_s · (1 + 1e−9)`. Dew point set to `−inf` if `W ≤ 1e−12`.

**Source:** `state`, `_from_w`

**Validation:** Exactly one companion property with `t_db` (or exactly h+w without t_db); dew point ≤ dry-bulb; temperature range; non-negative W.

**Reference:** Module cites ASHRAE HOF Ch.1 / Hyland–Wexler.

---

## 2. Air processes and AHU

**Files:** `engine/src/hvac_engine/processes.py`, `ahu_design.py`  
**Web glue:** `web/app/blueprints/psychro.py`  
**Spec:** `specs/SPEC-ahu-processes.md`, `specs/SPEC-interactive-psych-chart.md` (POC process map)  
**Stated references:** ASHRAE HOF 2017 Ch.1 process relations; ADP/bypass-factor coil model; constant-wet-bulb evaporative cooling; CIBSE Guide B mentioned in spec.

### 2.0 Interactive chart — map any two states (POC)

**What it does:** Describes heat/cool and humidify/dehumidify needed to go from state 1 → 2; with airflow, reports kW and kg/h.

**Formulas:**

```
ΔT = T2 − T1
ΔW = W2 − W1
Δh = h2 − h1
Q_total = m_da · Δh
Q_sensible = m_da · (h(T2, W1) − h1)   # constant-moisture leg
Q_latent = Q_total − Q_sensible
ṁ_w (kg/h) = m_da · ΔW · 3600
```

**Source:** `processes.map_state_process`

**Assumptions:** Straight chord on the chart (not a coil ADP model). Mass flow from entering-state specific volume when volumetric flow is given.

### 2.1 Dry-air mass flow from volume flow (web)

**What it does:** Converts entered volume flow to dry-air mass flow for process duties.

**Formula:**

```
m_da = (Q_m3h / 3600) / v
```

where `v` is the state’s specific volume (m³/kg dry air).

**Source:** `web/app/blueprints/psychro.py` → `_m_da`

**Assumptions:** Volume flow is interpreted at the state whose `v` is used (on-coil or supply depending on tool).

**Reference:** not documented in code (orchestration helper).

---

### 2.2 Adiabatic mixing

**What it does:** Mixes two airstreams by dry-air mass and energy balance.

**Formulas:**

```
m = m_a + m_b
W_mix = (m_a·W_a + m_b·W_b) / m
h_mix = (m_a·h_a + m_b·h_b) / m
```

If `(h_mix, W_mix)` is supersaturated: settle to saturated state at same `h_mix` by bisection (`_saturated_state_at_enthalpy`); condensate `m · max(W_mix − W_sat, 0)`.

**Source:** `processes.mix`

**Validation:** Mass flows ≥ 0 and sum > 0; same barometric pressure within `1e−6` kPa.

**Reference:** ASHRAE HOF process relations — module docstring / SPEC.

---

### 2.3 Sensible process (constant moisture)

**What it does:** Heat or cool to `t_out` at constant W; duty from enthalpy change.

**Formulas:**

```
state_out = state(t_out, w=W_in, p=p)
Q = m_da · (h_out − h_in)     # q_sensible = q_total; q_latent = 0
```

**Sign convention:** Positive Q = heat added to the air (kW).

**Source:** `processes.sensible`

**Validation:** `m_da > 0`; `state()` raises if supersaturated.

**Reference:** SPEC-ahu-processes / HOF — stated at module level.

---

### 2.4 Cooling coil (ADP / bypass-factor model)

**What it does:** Forward apparatus-dew-point coil. Air-on and ADP lock the
psychrometric chord; off-coil dry bulb (or BF) sets position on that chord.
Leaving RH/W, duties, SHR, condensate, CF/BF, and frost flag are results.

**Formulas:**

```
BF = (t_off − t_ADP) / (t_on − t_ADP)     # or t_off = t_ADP + BF·(t_on − t_ADP)
W_off = W_s(t_ADP) + BF · (W_on − W_s(t_ADP))   # wet coil (t_ADP < t_dp,on)
W_off = W_on                                     # dry coil (t_ADP ≥ t_dp,on)

Q_total = m_da · (h_off − h_on)
Q_sensible = m_da · (enthalpy(t_off, W_on) − enthalpy(t_on, W_on))
Q_latent = Q_total − Q_sensible
SHR = Q_sensible / Q_total   (or 1 if Q_total == 0)
condensate = m_da · max(W_on − W_off, 0)
CF = 1 − BF
frost_risk = (t_ADP ≤ 0)
```

**Legacy:** `t_off` + `rh_off` (AHU sim) finds ADP as the saturation intersection of
the chord through the prescribed off-coil point, then runs the forward model.

**Source:** `cooling_coil`, `_apparatus_dew_point`

**Validation:** `m_da > 0`; `t_ADP < t_on`; `t_ADP ≤ t_off ≤ t_on` (or BF in `[0,1)`);
dry-coil `t_off` must stay at/above entering dew point.

**Assumptions:** Straight ON→ADP chord (standard bypass-factor model); not a UA/LMTD
tube-side coil model. Leaving RH is typically ~90–95% for a wet coil because the
chord sits above the curved saturation line.

**Reference:** Standard ADP/bypass-factor model — module docstring / SPEC; CIBSE Guide B in SPEC.

---

### 2.5 Steam humidification

**What it does:** Isothermal steam injection to target W.

**Formulas:**

```
state_out = state(t_db_in, w=W_out, p)
steam_rate = m_da · (W_out − W_in)
Q_latent = m_da · (h_out − h_in)
```

**Assumptions:** Dry-bulb unchanged (isothermal steam model as coded).

**Source:** `steam_humidify`

**Validation:** `m_da > 0`; `W_out` not below `W_in`; no supersaturation.

**Reference:** SPEC-ahu-processes — module level.

---

### 2.6 Adiabatic humidification

**What it does:** Evaporative humidification along constant wet-bulb.

**Formulas:**

```
t_out = t_db − ε · (t_db − t_wb)
state_out = state(t_out, twb=t_wb_in, p)
water_rate = m_da · (W_out − W_in)
Q_total = m_da · (h_out − h_in)
```

**Variables:** `ε` effectiveness in `(0, 1]`.

**Assumptions:** Constant wet-bulb process; effectiveness linear in dry-bulb approach to WB.

**Source:** `adiabatic_humidify`

**Reference:** Constant-wet-bulb evaporative cooling — module docstring.

---

### 2.6a Adiabatic / evaporative cooling (calculator API)

**What it does:** Same constant wet-bulb process as §2.6, with Mode A
(effectiveness or leaving RH) and Mode B (sensible cooling duty → ε).

**Formulas:**

```
ε = (T_db1 − T_db2) / (T_db1 − T_wb1)
state_out = state(T_db2, twb=T_wb1, p)
Q_sensible = m_da · (1.006 + 1.86·W_in) · (T_db1 − T_db2)   # positive cooling
water_rate = m_da · (W_out − W_in)
```

Duty mode rejects T_db2 &lt; T_wb1.

**Source:** `adiabatic_cool`

**Reference:** SPEC-ahu-processes — adiabatic_cool.

---

### 2.6b Desiccant dehumidification

**What it does:** Isenthalpic / near-isenthalpic drying. Leaving dry-bulb rises as
moisture falls; optional ηd < 1 adds heat of adsorption above the isenthalpic line.

**Formulas:**

```
h_out = h_in + (1 − η_d) · 2501 · (W_in − W_out)     # kJ/kg
state_out = state(h=h_out, w=W_out, p)                 # solves T_db
ΔW = W_in − W_out
moisture_removed = m_da · ΔW                           # kg/s
Q_total = m_da · (h_out − h_in)                        # 0 when η_d = 1
```

Mode B: `W_out = W_in − moisture_removed / m_da`. RH target: bisect W_out on the
process line until leaving RH matches.

**Source:** `desiccant_dehumidify`

**Validation:** `m_da > 0`; `0 < η_d ≤ 1`; exactly one of `w_out` / `rh_out` /
`moisture_removed`; `W_out < W_in`.

**Reference:** SPEC-ahu-processes — desiccant section.

---

### 2.6c Sensible heating + steam humidification

**What it does:** Two-stage process — heat at constant W to state X, then
isothermal steam to state 2.

**Formulas:**

```
state_X = state(t_out, w=W_in)
Q_sensible = m_da · (h_X − h_in)
state_2 = state(t_out, w=W_out)          # isothermal steam
steam_rate = m_da · (W_out − W_in)
Q_latent = m_da · (h_2 − h_X)
Q_total = Q_sensible + Q_latent
```

Duty mode: `t_out = t_in + Q_s / (m_da · (1.006 + 1.86·W_in))`,
`W_out = W_in + steam_rate / m_da`.

**Source:** `heat_and_humidify`

**Reference:** SPEC-ahu-processes — heat_and_humidify.

---

### 2.7 Fan sensible gain

**What it does:** Temperature rise across fan at constant moisture.

**Formulas:**

```
c_p,moist = 1.006 + 1.86 · W     # kJ/(kg·K)
ΔT = P_kW / (m_da · c_p,moist)   # if power given
else use given ΔT
then sensible(state_in, m_da, t_db + ΔT)
```

**Assumptions:** All specified fan power absorbed by airstream (in-airstream motor interpretation stated in docstring).

**Source:** `fan_gain`

**Validation:** Exactly one of `power_kw` or `dt`; both ≥ 0 where applicable.

**Reference:** SPEC fan_gain — stated in docstring.

---

### 2.8 AHU simulation (forward)

**What it does:** Chains optional stages: OA → mix → frost/preheat → (blow fan) → cooling coil → reheat → humidifier → (draw fan) → supply.

**Logic summary:**

- `oa_fraction` by dry-air mass; mix if `< 1`.
- Frost coil: sensible heat if `frost_coil_t > current t_db`.
- Cooling: `cooling_coil(..., coil_t_off, coil_rh_off)` default RH off = 0.90.
- Reheat if `reheat_t > current t_db`.
- Steam OR adiabatic humidify (not both).
- Fan via `fan_power_kw` or `fan_pickup_dt`.
- Totals: sum positive duties = heating_total; sum negative = cooling_total; moisture added/removed from stage moisture signs.

**Source:** `processes.simulate_ahu`

**Validation:** `oa_fraction ∈ (0, 1]`; return air required if OA fraction < 1; fan_position ∈ {`blow`,`draw`}; mutually exclusive humidifiers.

**Reference:** SPEC-ahu-processes.

---

### 2.9 Supply-driven AHU design (inverse)

**What it does:** Given required supply state, derives mix / cool / reheat / fan path.

**Logic:**

1. Mix OA/RA → on-coil.
2. Optional blow-through fan raises on-coil T.
3. Draw-through: reheat targets `t_sup − ΔT_fan`.
4. If `|W_sup − W_on| ≤ 1e−5`: sensible cool/heat/no-op only.
5. Else dehumidification: off-coil at supply moisture and `coil_rh_off` (default **0.90**); `coil_rh_off=1.0` is CF = 1 (saturated at supply dew point); optional SAT waypoint at on-coil dew point; reheat to target when needed; condensate `m_da · (W_on − W_sup)`.
6. Warn if delivered supply differs by > 0.1 °C or > 5×10⁻⁵ kg/kg.

**Fan ΔT:** same `c_p = 1.006 + 1.86·W` as `fan_gain`.

**Assumptions / simplifications:** Default off-coil RH 90% (aligned with `simulate_ahu`); when W_sup > W_on the inverse path sizes heating then steam humidification; no frost/preheat coil stage in this inverse path.

**Source:** `ahu_design.design_ahu_to_supply`

**Validation:** `m_da > 0`; OA fraction; `coil_rh_off` in (0, 1]; fan_position ∈ {`none`,`blow`,`draw`}; moisture reachability.

**Reference:** SPEC-ahu-processes (`design_ahu_to_supply`) — stated in module docstring.

---

## 3. Duct sizing

**File:** `engine/src/hvac_engine/duct.py`  
**Spec:** `specs/SPEC-duct-sizing.md`  
**Stated references:** CIBSE Guide C §4; ASHRAE HOF Ch.21 / Ch.32; Swamee–Jain (1976); Huebscher; Lindab catalogue sizes.

### 3.1 Standard air & roughness constants

| Constant | Value | Role |
|----------|-------|------|
| `RHO_STD` | 1.2 kg/m³ | Standard air density (CIBSE “standard air” 20 °C, 101.325 kPa — stated) |
| `NU_STD` | 1.51×10⁻⁵ m²/s | Kinematic viscosity of standard air |
| `ROUGHNESS_GALV_STEEL` | 0.00009 m (0.09 mm) | Absolute roughness, galvanized steel |
| `DEFAULT_MAX_VELOCITY` | 8.0 m/s | Default recommended velocity limit |
| `DEFAULT_MAX_FRICTION_RATE` | 1.0 Pa/m | Default recommended friction limit |
| `MAX_ASPECT_RATIO` | 4.0 | Rectangular aspect warning threshold |
| `FLEX_DUCT_DERATE` | 1.5 | Flex vs rigid friction multiplier |

**Inconsistency (as-is):** Fixed `RHO_STD` / `NU_STD` — not site-adjusted; psychrometrics density not used. Module comments note site-adjusted density is Phase A out of scope.

---

### 3.2 Darcy friction factor (Swamee–Jain)

**Formula:**

```
Re = V · D / ν
if Re ≤ 0:     f = 0
if Re < 2300:  f = 64 / Re
else:          f = 0.25 / [log10(ε/D / 3.7 + 5.74 / Re^0.9)]²
```

**Assumptions:** Laminar fallback below Re 2300; Swamee–Jain instead of iterative Colebrook–White; stated validity roughly 4×10³ < Re < 10⁸, ε/D < 0.05.

**Source:** `duct._swamee_jain`

**Reference:** Swamee–Jain (1976); CIBSE/ASHRAE duct design context — stated in docstring.

---

### 3.3 Circular velocity, velocity pressure, friction rate

**Formulas:**

```
A = π · D² / 4
V = (Q_m3h / 3600) / A
Pv = 0.5 · ρ · V²
Δp/L = f · (1/D) · (ρ · V² / 2)
```

**Source:** `velocity_circular`, `velocity_pressure`, `friction_rate_circular`, `_friction_rate_from_v_d`

**Reference:** Darcy–Weisbach; Bernoulli dynamic pressure — stated.

---

### 3.4 Circular size solver

**What it does:** Given exactly two of {volume, velocity, diameter, friction_rate}, solves the rest.

**Logic:** Closed form where possible; bisection on D ∈ [0.02, 3.0] m or V ∈ [0.1, 50] m/s when needed. Then re-derives all fields from (Q, D).

**Propose:** Target V or Δp/L → size; optional snap up to Lindab catalogue diameter (`snap_to_standard_diameter` never undersizes).

**Source:** `size_circular`, `propose_circular`, `snap_to_standard_diameter`

**Validation:** Exactly two knowns; all knowns > 0; target reachable in search range.

**Reference:** SPEC-duct-sizing; Lindab Big Blue Book catalogue — stated in code.

---

### 3.5 Rectangular duct (Huebscher)

**Equivalent diameter:**

```
De = 1.30 · (a·b)^0.625 / (a+b)^0.25
```

**Actual velocity:** `V = (Q/3600) / (a·b)`  
**Friction rate:** evaluated as circular duct at `De` with same Q.

**Inverse at aspect ratio r = width/height ≥ 1:**

```
width = De · r^0.625 · (1 + 1/r)^0.25 / 1.30
height = width / r
```

**Propose:** Size circular for target V or Δp/L, convert via Huebscher at chosen aspect ratio.

**Note (as coded):** Target velocity is equivalent round-duct velocity; actual rectangular V is usually lower.

**Source:** `equivalent_diameter_rectangular`, `rectangular_from_equivalent_diameter`, `rectangular_other_side`, `size_rectangular`, `propose_rectangular`

**Validation:** Positive sides/volume; aspect_ratio ≥ 1 for inverse; aspect warning if AR > 4.

**Reference:** ASHRAE Fundamentals Ch.21 Huebscher — stated in code.

---

### 3.6 Flat-oval duct

**Geometry:**

```
A = b·(a − b) + (π/4)·b²
P = 2·(a − b) + π·b
De = 1.55 · A^0.625 / P^0.25
```

**Assumptions:** Coefficient **1.55** from ASHRAE Fundamentals Ch.21 / Heyt & Diaz (1975) — verified; unit test worked example 24×12 in → De ≈ 17.745 in.

**Sizing:** Same pattern as rectangular via circular De; catalogue snap to Lindab flat-oval pairs; catalogue-locked major/minor steppers.

**Source:** `_flat_oval_area`, `_flat_oval_perimeter`, `equivalent_diameter_flat_oval`, `size_flat_oval`, `propose_flat_oval`, snap/step helpers

**Validation:** `major ≥ minor > 0`; volume > 0.

**Reference:** ASHRAE Handbook — Fundamentals Ch.21 (Heyt and Diaz 1975).

---

### 3.7 Flex derate, increments, traffic light

```
friction_flex = friction_rigid · 1.5     # default FLEX_DUCT_DERATE
```

`snap_to_increment`: ceil to increment (default 25 mm).  
`round_to_increment`: nearest increment (rectangular fabricator grid).

```
status: red if value ≥ limit; amber if ≥ 0.85·limit; else green
```

**Source:** `apply_flex_derate`, `snap_to_increment`, `round_to_increment`, `status`

**Assumptions:** Flex multiplier is a planning figure; real flex depends on extension/kinks — stated in comments.

**Reference:** not a named standard for the 1.5 factor — planning figure (stated).

---

## 4. Duct fittings (index leg)

**File:** `engine/src/hvac_engine/fittings.py`  
**Web:** `web/app/blueprints/duct.py` (sums rows + safety margin %)  
**Spec:** Phase C of `SPEC-duct-sizing.md`  
**Stated references:** ASHRAE Fundamentals Ch.32; CIBSE Guide C §4 — method; K values are **representative** single-point figures, not full geometry tables (explicitly flagged).

### 4.1 Pressure-drop accounting

```
dp_fitting = K · Pv
dp_straight = L · (Δp/L)
dp_accessory = user-entered Pa   (pass-through)
```

**Pv** from `duct.velocity_pressure` at that row’s velocity (ρ default 1.2 unless overridden upstream).

**Catalogue K values (as coded):**

| Key / label (abbrev.) | K |
|-----------------------|---|
| Round 90° smooth r/D 1.5 | 0.22 |
| Round 90° smooth r/D 1.0 | 0.33 |
| Round 90° mitred | 1.20 |
| Round 45° smooth | 0.15 |
| Round tee branch / straight | 1.00 / 0.15 |
| Round gradual reducer / enlarger | 0.05 / 0.20 |
| Round damper open / entry / exit | 0.20 / 0.50 / 1.00 |
| Rect 90° mitred no vanes / with vanes | 1.30 / 0.40 |
| Rect 90° radiused r/W 1.0 | 0.25 |
| Rect tee / transitions / damper | same pattern as round family values above |

**Web safety margin:**

```
margin_pa = total_pa · (safety_margin_% / 100)
total_with_margin = total_pa + margin_pa
```

**Source:** `fitting_pressure_drop`, `straight_pressure_drop`, `accessory_pressure_drop`; web leg builder

**Validation:** Length > 0; accessory dp ≥ 0.

**Reference:** Method ASHRAE Ch.32 / CIBSE Guide C §4; individual K values — **not documented as page-specific primary tables** (planning figures).

---

## 5. Pipe / hydronics

**Files:** `engine/src/hvac_engine/pipe.py`, `glycol_data.py`, `standard_glycol.py`  
**Spec:** `specs/SPEC-pipe-sizing.md`  
**Stated references:** CIBSE Guide C; EN 10255 / EN 1057 / DIN 11850; ASHRAE
secondary coolants (EG / MPG); Hydratech Coolflow data; Swamee–Jain; BIPM/ISO for `g`.

### 5.1 Fluid properties

**Water:** Linear interpolation of table `(T, ρ, μ, Cp)` from 0–100 °C (CIBSE/ASHRAE anchor table — stated). Outside range: clamp to end-point row.

**Standard glycol (`eg`, `mpg`):** ASHRAE aqueous ethylene / monopropylene glycol
correlations (CoolProp AEG / APG polynomials; volume %). Catalogue % v/v matches
Coolflow IGE and NTP respectively. Freeze point from the concentration-only
exponential polynomial. Temperature clamped to the correlation envelope and not
below freeze.

**Hydratech glycol (`dtx`, `epg`, `ppg`):** Coolflow DTX / EPG / PPG grids at
fixed % concentrations; interpolate `(T, ρ, μ, Cp, freeze_point)`. Freeze point
from first grid row’s freeze column via `glycol_freeze_point_c`.

**Mean water temperature for duty:**

```
T_mean = LWT + ΔT / 2
```

**Kinematic viscosity:** `ν = μ / ρ`.

**Source:** `fluid_properties`, `_interp_table`, `_interp_glycol`, `mean_water_temperature_c`, `glycol_data.*`, `standard_glycol.*`

**Validation:** Water concentration must be 0; glycol % must be in catalogue set for fluid.

**Reference:** CIBSE/ASHRAE water table; ASHRAE secondary coolants (AEG/APG);
Hydratech Excel transcription — stated.

---

### 5.2 Flow from load

**What it does:** Converts thermal load and temperature difference to mass and volume flow.

**Formulas:**

```
Q_W = load_kW · 1000
ṁ = Q_W / (Cp · ΔT)          # Cp in J/(kg·K)
Q_m3h = ṁ / ρ · 3600
```

**Source:** `flow_from_load`

**Validation:** `load_kw > 0`, `delta_t_k > 0`.

**Reference:** Energy balance `Q = ṁ·Cp·ΔT` — SPEC-pipe-sizing; not a named equation number in code.

---

### 5.3 Pipe friction evaluation

**Same Swamee–Jain as duct**, then:

```
A = π · D_id² / 4
V = (Q_m3h / 3600) / A
Re = V · D / ν
Δp/L = f · (1/D) · (ρ · V² / 2)
```

**Roughness ε (m):** carbon steel 0.00015; copper 0.0000015; dairy SS 0.0000015 (CIBSE Guide C §1 — stated).

**Catalogues:** EN 10255 Series 1 medium carbon steel; EN 1057 copper; DIN 11850 dairy SS with 1.5 mm wall (ID = OD − 3 mm).

**Source:** `evaluate_size`, `evaluate_catalogue`, `_swamee_jain`

**Reference:** Darcy–Weisbach + Swamee–Jain; pipe standards — stated.

**Inconsistency (as-is):** Pipe uses temperature-dependent fluid ρ and ν; duct uses fixed standard air. Different ε defaults for different materials (expected) but both friction cores are duplicated copies of Swamee–Jain.

---

### 5.4 Velocity and friction design bands (status)

**Velocity by DN** (`VELOCITY_BANDS_BY_DN`):

| DN ≤ | min | ideal_min | ideal_max | max |
|------|-----|-----------|-----------|-----|
| 50 | 0.6 | 0.8 | 1.2 | 1.5 |
| 150 | 0.6 | 1.2 | 1.8 | 2.5 |
| else | 0.6 | 1.8 | 2.5 | 3.0 |

Status: green in ideal band; amber in border bands; red outside min/max.

**Friction Pa/m** (`FRICTION_BANDS`): red < 100 or > 500; amber in 100–150, 150–200, 300–400, 400–500; green in 200–300. Lifecycle-cost framing (12 Jul 2026 comment).

**CIBSE_LIMITS:** application keys only; Table 2.2’s 1.5 m/s aligns with DN ≤ 50 max. Per-DN bands govern status (documented in UI + design-limits guide).

**Recommended DN:** smallest size with green friction and velocity not red; else first within absolute limits.

**Source:** `velocity_status`, `friction_status`, `recommended_index`, `band_status`, `status` (legacy duct-style)

**Reference:** Per-DN methodology / lifecycle bands — SPEC and comments; CIBSE Guide C Table 2.2 for small-pipe max.

---

### 5.5 Pipe mass, velocity pressure, hydrostatic head

```
m_per_m = ρ_metal · (π/4) · (OD² − ID²)
Pv = 0.5 · ρ_fluid · V²
P_static = ρ · g · h     with g = STANDARD_G = 9.80665 m/s²
```

**Pump duty:**

- Open circuit: `pump = static + friction`
- Pressurised closed: `pump = friction` only (static still reported)

**Source:** `pipe_mass_per_m`, `velocity_pressure`, `hydrostatic_pressure_pa`, `head_breakdown`

**Metal densities:** carbon steel 7850; copper 8960; dairy SS 8000 kg/m³.

**Reference:** BIPM/ISO 80000-3 for g — stated; head logic in SPEC Stage 3.

---

## 6. Pipe fittings

**File:** `engine/src/hvac_engine/pipe_fittings.py`  
**Web:** `web/app/blueprints/pipe.py`  
**Stated references:** CIBSE Guide C §4; Crane TP-410-style summaries — method; K values representative.

### 6.1 Accounting

```
dp = K · Pv(V, ρ_fluid)
dp_straight = L · (Δp/L)
dp_device = user Pa
```

**K catalogue (as coded):** elbow 90 std 0.90; LR 0.45; 45° 0.40; tee run 0.40; tee branch 1.50; sudden contraction/enlargement 0.50/1.00; entry/exit 0.50/1.00; gate 0.20; globe 10.0; ball 0.05; butterfly 0.30; swing check 2.00; Y-strainer 2.50.

**Web safety margin:** same percentage form as duct index leg.

**Source:** `fitting_pressure_drop`, `straight_pressure_drop`, `device_pressure_drop`

**Validation:** K ≥ 0; Pv ≥ 0; L > 0; friction rate ≥ 0; device dp ≥ 0.

**Reference:** Method CIBSE/Crane-style; individual K — planning figures (stated).

---

## 7. Climate / design weather

**Engine:** `engine/src/hvac_engine/climate.py`  
**I/O + WB helpers:** `web/app/weather_client.py`  
**Spec:** `specs/SPEC-weather-climate-data.md`  
**Stated references:** ASHRAE HOF Ch.14 percentile and extreme-annual (Gumbel) methods; Open-Meteo ERA5 seamless reanalysis (not licensed ASHRAE station tables).

### 7.1 Year qualification

A calendar year is used if ≥ `MIN_YEAR_COMPLETENESS = 0.95` of its hours have a dry-bulb reading; otherwise rejected.

**Source:** `_qualifying_years` / `qualifying_years`

---

### 7.2 Design dry-bulb percentiles + MCWB

**Cooling fractions:** 0.4% → 0.004; 1.0% → 0.01; 2.0% → 0.02 (high tail).  
**Heating fractions:** 99.6% → 0.004; 99% → 0.01; 98% → 0.02 (low tail).

**Per-year tail value:**

```
k = max(1, min(n, round(fraction · n)))
high: ordered[n − k]
low:  ordered[k − 1]
```

**Design DB:** average of per-year threshold values.  
**MCWB:** for hours at/above (cooling) or at/below (heating) that year’s threshold, average wet-bulbs from caller-supplied `wet_bulb_fn`, then average across years.

**Assumptions:** Per-year-then-average (not pooled multi-year sort); all hours of year used (no seasonal filter); heating MCWB computed even though traditional ASHRAE heating tables often omit coincident WB (stated in `DesignPoint` docstring).

**Web wet-bulb:** `psy.state(t_db, tdp=min(t_dp, t_db), p=pressure_from_altitude(elevation)).t_wb` with dew-point clamp for reanalysis rounding.

**Source:** `design_conditions`, `_design_point_for_tail`, `annual_percentile`; `weather_client.fetch_design_conditions`

**Also reported:** extreme max/min DB over qualifying hours with coincident DP and timestamps.

**Reference:** ASHRAE HOF Ch.14 — stated extensively in module.

---

### 7.3 Extreme annual return periods (Gumbel)

**Return periods:** 5, 10, 20, 50 years.

**Gumbel factor:**

```
F(n) = −(√6 / π) · (γ + ln(ln(n/(n−1))))
γ = 0.5772156649 (Euler–Mascheroni)
```

**Return value:**

```
high: mean + std · F(n)
low:  mean − std · F(n)
```

Sample std uses `n−1` denominator; needs ≥ 2 years.

**DB series:** per-year max/min of dry-bulb.  
**WB series (web):** rank hours by moist-air enthalpy (closed-form), solve iterative WB for top/bottom `_WB_CANDIDATES_PER_YEAR = 10` candidates; take max/min resolved WB. Assumption: thermodynamic WB ordering ≈ enthalpy ordering at fixed p.

**Note (as coded):** DB and WB extremes are independent (not coincident states).

**Source:** `_gumbel_factor`, `gumbel_return_value`, `extreme_series`; `weather_client._extreme_annual`, `_year_wet_bulb_extremes`

**Reference:** ASHRAE HOF Ch.14 extreme-annual form — stated.

**Data assumption:** ERA5 seamless reanalysis; damped extremes vs station data acknowledged in weather_client comments.

---

## 8. Unit conversion (presentation and converter tool)

### 8.1 SI/IP display layer

**File:** `engine/src/hvac_engine/units.py`  
**Spec:** `specs/SPEC-unit-conversions.md`  
**Stated references:** NIST SP 811 / BIPM exact definitions.

**Role:** Does **not** run inside physics. Maps display ↔ canonical SI for UI.

Notable canonical vs display quirks (as coded):

- Humidity ratio: canonical kg/kg; SI display g/kg; IP gr/lb.
- `duct_flow`: canonical m³/h like `vol_flow`, but SI **display** is m³/s.
- `velocity_pressure`: canonical Pa (not kPa like barometric `pressure`).
- Friction rate IP: in.wg / 100 ft via `249.0889 Pa` and `30.48 m`.

**Head triplet:** SI Pa · kPa · bar; IP psi · in.wg · ft of fluid with `h = P / (ρ·g)`, `g = 9.80665`.

**Source:** `to_si`, `from_si`, `symbol`, `decimals`, `head_pressure_triplet`

---

### 8.2 Multi-unit converter

**File:** `engine/src/hvac_engine/converter.py`  
**Spec:** `specs/SPEC-unit-converter.md`  
**Stated references:** NIST SP 811 / BIPM.

**Linear:** `value_out = value_in · factor_src / factor_dst`  
**Temperature:** convert via kelvin with affine formulas (°C/°F/K/°R); warn if below 0 K.

Categories include length, area, volume, mass, force, pressure, temperature, speed, volumetric/mass flow, power (incl. ton of refrigeration = 3516.8528420667 W), energy, time, angle, density, humidity ratio, enthalpy.

**Source:** `convert_all`

**Note:** Presentation-only sibling of `units.py`; shares NIST factors by design. Not used by psychrometric/duct/pipe physics.

---

## 9. Documented inconsistencies (as found)

1. **Air density:** Psychrometrics computes state ρ; duct defaults to 1.2 kg/m³ fixed; pipe uses fluid ρ(T).
2. **Viscosity:** Duct fixed ν; pipe μ(T)/ρ(T).
3. **Pressure units:** Psychrometrics barometric in kPa; duct/pipe losses in Pa.
4. **Coil models:** Forward and inverse AHU tools both default to 90% off-coil RH (aligned Jul 2026); inverse accepts `coil_rh_off` including 100% for CF = 1.
5. **Friction factor code:** Swamee–Jain consolidated in `fluid_mechanics.swamee_jain` (duct/pipe import shared).
6. **Flat-oval De coefficient 1.55:** Confirmed ASHRAE Ch.21 / Heyt & Diaz (1975).
7. **Fitting K-factors (duct and pipe):** Representative planning figures, not full ASHRAE/CIBSE/Crane geometry tables — disclosed in UI.
8. **Heating MCWB:** Computed for heating percentiles though traditional ASHRAE heating tables often omit it.
9. **Weather source:** Open-Meteo ERA5 reanalysis vs published ASHRAE station design tables (acknowledged; see `docs/climate-validation.md`).
10. **No building space-load engine** in this codebase despite “load” language on hydronic tools (load → flow only).
11. **Volume-flow SI display:** `vol_flow` shows m³/h; `duct_flow` shows m³/s for the same canonical unit.

---

## 10. Files outside the calculation core

The following touch calculations only as consumers/orchestrators (no independent engineering formulas beyond those noted above):

| Path | Role |
|------|------|
| `web/app/blueprints/psychro.py` | Forms → engine; `_m_da`; altitude → pressure |
| `web/app/blueprints/duct.py` | Sizer + index-leg sum + % margin |
| `web/app/blueprints/pipe.py` | Sizer + system sum + % margin + head UI |
| `web/app/weather_client.py` | Open-Meteo I/O; enthalpy ranking for extreme WB |
| `web/app/chart.py` | Chart curves via psychrometric helpers |
| `web/app/units.py` | Flask wrapper over engine `units` |
| `engine/scripts/build_glycol_data.py` | Builds `glycol_data.py` from Excel |
| `engine/tests/test_*.py` | Validation anchors, not methodology sources |

Client JS (`ductsizer.js`, `pipesystem.js`, `psychart.js`) is UI/API wiring only.

---

*Generated as a faithful extract of the codebase as of the documentation pass. Where code comments or specs cite a standard, that citation is recorded; otherwise marked as not documented in code.*
