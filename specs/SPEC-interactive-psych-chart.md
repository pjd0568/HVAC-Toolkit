# Functional Spec — Interactive Psychrometric Chart (POC)

**Module:** `hvac_engine.processes.map_state_process` + web `psychro.interactive_chart`
**Status:** v0.1 POC — 9 August 2026
**Clean-room note:** Built on SPEC-psychrometrics.md / SPEC-ahu-processes.md (ASHRAE HOF Ch.1).

## Purpose

Proof-of-concept interactive psychrometric chart: place up to four labelled state
points by long-pressing the chart, edit their properties, and map a process
between any two points (heat / cool / humidify / dehumidify), with optional
airflow → kW and kg/h rates.

## Scope (POC)

- Up to **4** points, labelled **A–D** on the chart, each with an optional text name.
- Long-press (≈500 ms) adds the next free point at the tapped (T_db, W) location.
- Points may be refined by editing dry-bulb and a second property (RH or W).
- Exactly **one** process segment at a time, between any two existing points.
- Process map reports required heating/cooling (°C) and humidification /
  dehumidification (kg/kg dry air). With volumetric airflow, also report total /
  sensible / latent duty (kW) and moisture rate (kg/h).
- Local test only first; no PDF export required for POC.

## Method

State resolution: `psychrometrics.state` (existing).

Process deltas between states 1 → 2 (dry-air basis):

- ΔT = T₂ − T₁ → **heat** if ΔT > 0, **cool** if ΔT < 0
- ΔW = W₂ − W₁ → **humidify** if ΔW > 0, **dehumidify** if ΔW < 0
- Δh = h₂ − h₁

With dry-air mass flow `m_da` (kg/s):

- Q_total = m_da · Δh                         (kW)
- Q_sensible = m_da · (h(T₂, W₁) − h(T₁, W₁)) (kW, constant-moisture leg)
- Q_latent = Q_total − Q_sensible
- moisture_rate = m_da · ΔW · 3600            (kg/h)

`m_da` from volumetric flow at the **entering** state: `m_da = (V̇ / 3600) / v₁`
with V̇ in m³/h (same convention as other psychro tools).

Clicks that land above saturation are clamped to the saturation humidity ratio
at that dry-bulb (POC UX).

## Out of scope (POC)

- Coil ADP / bypass modelling, mixing, AHU sequences
- Drag-to-move points, undo stack, persistence beyond the browser session
- PDF / chart PNG export
