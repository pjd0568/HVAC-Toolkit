# Functional Spec — Unit Conversions Module

**Module:** `hvac_engine.units`
**Status:** implemented (SI/IP display layer). Standalone Unit Converter *tool* still to come.
**Standards cited:** NIST SP 811 (2008), BIPM SI brochure — exact unit definitions only.

## Purpose

The engine is canonical SI: every calculation and every `PsychroState` field is in
SI. Users, though, work in either **SI (metric)** or **IP (imperial)**. This module is
the presentation-side bridge — it maps a quantity's canonical SI value to/from the
value shown or entered under a chosen unit *system*. It never runs inside a
calculation, so the physics stays SI and untouched.

This is deliberately the base layer for two things: (1) the per-user SI/IP preference
that every tool renders through, and (2) the future standalone Unit Converter tool.

## Model

A **quantity** (e.g. `temperature`, `power`) has a canonical SI unit — the unit the
engine actually holds. For each quantity and each system there is a `_Unit` with:

- `symbol` — display label (e.g. `°C`, `°F`, `Btu/h`);
- `to_si(display) -> si` and `from_si(si) -> display` — a matched pair;
- `decimals` — default display precision.

Temperature is **affine** (offset): `°C = (°F − 32) × 5/9`. Every other quantity is a
single linear factor, `si = display × k`, so `to_si`/`from_si` just multiply/divide.

Dimensionless ratios (relative humidity, sensible-heat ratio, contact/bypass factor)
are **not** units and are absent by design — callers render those directly as `%`.

## Quantities, canonical SI unit, and IP display

| quantity          | canonical SI      | SI display | IP display | exact factor (1 display = …)      |
|-------------------|-------------------|------------|------------|-----------------------------------|
| `temperature`     | °C                | °C         | °F         | affine, °F = °C·9/5 + 32           |
| `humidity_ratio`  | kg/kg dry air     | g/kg       | gr/lb      | 1 kg/kg = 7000 gr/lb              |
| `enthalpy`        | kJ/kg dry air     | kJ/kg      | Btu/lb     | 1 Btu/lb = 2.326 kJ/kg (exact)   |
| `pressure`        | kPa               | kPa        | inHg       | 1 inHg(32 °F) = 3.386389 kPa      |
| `vol_flow`        | m³/h              | m³/h       | CFM        | 1 CFM = 1.699010796 m³/h         |
| `mass_flow`       | kg/s dry air      | kg/s       | lb/h       | 1 kg = 2.204622622 lb            |
| `power`           | kW                | kW         | Btu/h      | 1 kW = 3412.141633 Btu/h         |
| `density`         | kg/m³             | kg/m³      | lb/ft³     | 1 kg/m³ = 0.06242796058 lb/ft³   |
| `specific_volume` | m³/kg dry air     | m³/kg      | ft³/lb     | 1 m³/kg = 16.01846337 ft³/lb     |
| `moisture_rate`   | kg/s              | kg/h       | lb/h       | condensate / steam / spray water |

For most quantities the canonical unit equals the SI *display* unit (identity). Two
differ for readability: `humidity_ratio` (canonical kg/kg, shown g/kg) and
`moisture_rate` (canonical kg/s, shown kg/h). `vol_flow` is canonically m³/h — the
volumetric-flow figure the tools take — not m³/s.

**IP conventions chosen (Paul, 3 Jul 2026):** duty in Btu/h (not tons/MBH), humidity
ratio in grains/lb, pressure in inHg. Fan ratings (SFP W/(l/s), fan power kW) stay
metric on both systems — they are equipment ratings, not air properties.

## API

```
symbol(quantity, system) -> str
to_si(quantity, display_value, system) -> float      # user input  -> engine
from_si(quantity, si_value, system) -> float         # engine value -> display
decimals(quantity, system) -> int
```

`SYSTEMS = ("SI", "IP")`. Unknown quantity or system raises `ValueError`.

## Where it is consumed

The web layer owns *which* system is active and *when* to convert:

- `web/app/units.py` — `get_unit_system()` (session today; logged-in user preference
  once auth lands — a one-function change), `set_unit_system()`, and `UnitView` (`U` in
  templates) which wraps this module bound to the active system.
- Blueprints convert form inputs with `U.to_si(quantity, value)` **before** calling the
  engine; templates render with `U.fmt(quantity, si_value)` + `U.sym(quantity)`.

So a new tool gets units for free: take inputs through `U.to_si`, render through
`U.fmt`/`U.sym`, and add any missing quantity here.

## Clean-room note

Factors are the exact definitions from NIST SP 811 / BIPM only. The quantity list was
decided fresh for this product; no prior app's category taxonomy was referenced.

## Not yet done

- A user-facing **Unit Converter** tool (the "Utilities" nav item) built on this module:
  free conversion between any two units of a category, more categories (length, area,
  volume, velocity, energy). This spec covers the display layer only.
- Chart axes remain SI (the psychrometric chart is drawn in °C / kg-per-kg); an IP chart
  is a later item.
- Persisting the preference against a user record (waits on auth/DB).
