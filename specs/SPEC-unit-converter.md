# Functional Spec — Unit Converter Tool

**Engine module:** `hvac_engine.converter`
**Web tool:** `web/app/blueprints/converter.py` → `/converter`
**Status:** to build (this spec written first, per the project's spec-first rule).
**Standards cited:** NIST SP 811 (2008) / BIPM SI brochure — exact unit definitions only.

## Purpose

A standalone converter. The user picks a **category** (length, pressure, power …),
enters **one value in one unit**, and sees that value expressed in **every other unit
of the category at once**, with the **relationship used printed beside each result**
(e.g. `1 in = 25.4 mm`, or for temperature the full formula `°F = °C × 9/5 + 32`).

This is separate from `hvac_engine.units` (the SI/IP *display layer* the calculators
render through, which has exactly one unit per system per quantity). The converter needs
a *rich* catalog — many units per category — so it is its own module. Both use the same
canonical-SI philosophy and the same exact NIST factors, so shared quantities agree.

## Method

Each category has one **canonical base unit** (SI). Every unit in the category is
defined by its relationship to that base:

- **Linear units** (all categories except temperature): a single factor `k` = "how many
  base units one of this unit is worth" (`base = value × k`). Converting value `v` from
  unit A (factor `a`) to unit B (factor `b`): `result = v × a / b`.
  The base is exact where the definition is exact (`1 in = 25.4 mm` exactly, etc.).
- **Temperature** is affine (has an offset), so it is handled specially: each unit is
  defined affine-to-kelvin, and any→any conversion composes two affine maps. The
  notation is the explicit closed-form formula for the chosen input→output pair.

Precision: results carry enough significant figures to be useful across scales
(a length of 25 mm → 0.0000155 mile). Use significant-figure formatting, not fixed
decimals, so both very large and very small equivalents read correctly.

## Notation (printed beside every result)

- **Linear:** the constant relating the two actual units, `1 <from> = <k> <to>`
  (`k = a / b`, formatted to a few significant figures). Constant regardless of the
  entered value, so it reads as a clean justification of the number.
- **Temperature:** the closed-form formula for the specific pair, e.g.
  `°F = °C × 9/5 + 32`, `K = °C + 273.15`, `°C = (°F − 32) × 5/9`,
  `°R = (°C + 273.15) × 9/5`. A small explicit table (4 units → 12 ordered pairs).

## Categories & units

Grouped for display as **Metric (SI)**, **Imperial / US**, and **Other** (absolute
scales, atmospheres, nautical units, etc.). Base unit in **bold**.

- **Length** — base **m**. Metric: nm, µm, mm, cm, m, km. Imperial/US: thou/mil, in, ft,
  yd, mile. Other: nautical mile.
- **Area** — base **m²**. Metric: mm², cm², m², ha, km². Imperial/US: in², ft², yd², acre,
  mile².
- **Volume** — base **m³**. Metric: ml, l, m³. Imperial/US: in³, ft³, US gal, US fl oz,
  imp gal, imp pint.
- **Mass** — base **kg**. Metric: mg, g, kg, tonne. Imperial/US: gr (grain), oz, lb,
  stone, US ton (short), long ton.
- **Force** — base **N**. Metric: N, kN, kgf. Imperial/US: lbf, kip.
- **Pressure** — base **Pa**. Metric: Pa, kPa, MPa, bar, mbar, mmH₂O. Imperial/US: psi,
  inH₂O, inHg. Other: atm, torr.
- **Temperature** — base **K** (affine). °C, K, °F, °R. Formula notation.
- **Speed / velocity** — base **m/s**. Metric: m/s, km/h. Imperial/US: ft/s, ft/min (fpm),
  mph. Other: knot.
- **Volumetric flow** — base **m³/s**. Metric: m³/s, m³/h, l/s, l/min. Imperial/US: CFM
  (ft³/min), CFH, US GPM.
- **Mass flow** — base **kg/s**. Metric: kg/s, kg/h, g/s, tonne/h. Imperial/US: lb/s,
  lb/h, lb/min.
- **Power** — base **W**. Metric: W, kW, MW. Imperial/US: Btu/h, hp (mechanical),
  ft·lbf/s. Other: ton of refrigeration.
- **Energy** — base **J**. Metric: J, kJ, MJ, Wh, kWh, MWh. Imperial/US: Btu, ft·lbf,
  cal, kcal. Other: therm.
- **Time** — base **s**. s, min, h, day, week. (metric/SI-common grouping)
- **Angle** — base **rad**. rad, degree, gradian, arcminute.
- **Density** — base **kg/m³**. Metric: kg/m³, g/cm³. Imperial/US: lb/ft³, lb/in³.
- **Humidity ratio** — base **kg/kg** dry air. kg/kg, g/kg (metric), gr/lb (imperial).
- **Enthalpy (specific)** — base **J/kg**. J/kg, kJ/kg (metric), Btu/lb (imperial).

(HVAC set: temperature, pressure, vol/mass flow, power, energy, density, humidity ratio,
enthalpy, velocity. Everyday-general additions: length, area, volume, mass, force, time,
angle, speed.)

## Engine API

```
CATEGORIES: dict[str, Category]          # id -> Category(name, base_symbol, units[...])
list_categories() -> [(id, name)]
convert_all(category_id, value, from_unit_id) -> ConversionResult
    .category, .value, .from_unit
    .results: [ UnitResult(unit_id, name, symbol, group, value, notation) ]   # all units
```

Errors: unknown category or unit → `ValueError`. Temperature below absolute zero is
allowed to compute (it is just arithmetic) but flagged in a `warning` field.

## Web tool

Server-rendered (consistent with the other tools). Controls: category `<select>`, value
input, from-unit `<select>`. On submit, render the full result list grouped under Metric
/ Imperial / Other headings, each row: value + unit + the notation string. The entered
unit is highlighted. Wire the "Utilities → Unit Converter" nav item and dashboard card.

## Clean-room note

Factors are exact NIST SP 811 / BIPM definitions only. Category and unit selection was
decided fresh for this product; no prior app's converter was referenced.
