# Climate design-condition validation (ERA5 vs station tables)

**Purpose:** Evidence for launch / professional queries that the app’s ERA5-derived
design conditions are *not* licensed ASHRAE/CIBSE station values, and to quantify
typical deltas.

**Method (app):** ASHRAE HOF Ch.14 percentiles — per calendar year, then average —
implemented in `hvac_engine.climate`, fed by Open-Meteo `era5_seamless`
(ERA5-Land where available) via `web/app/weather_client.py`. Run date for ERA5
column below: 2026-07-26; 20-year archive pull.

**Reference (published):** NCEI *Engineering Weather Data* SI station sheets
(1988–2017 POR) — annual 0.4% / 99.6% occurrence dry-bulb (same percentile labels
as ASHRAE; not a licensed ASHRAE Handbook extract). Sources linked per row.

| Location | Lat / Lon | Elev (m) | NCEI 0.4% DB / MCWB (°C) | NCEI 99.6% DB (°C) | ERA5 0.4% DB / MCWB (°C) | ERA5 99.6% DB (°C) | Δ Cool DB (K) | Δ Heat DB (K) | NCEI sheet |
|---|---|---:|---|---:|---|---:|---:|---:|---|
| London Heathrow (EGLL) | 51.48 / −0.46 | 25 | 28 / 18 | −2 | 26.2 / 19.7 | −2.4 | **−1.8** | −0.4 | [ICAO_EGLL](https://www.ncei.noaa.gov/pub/access/cebrequests/engineeringwx/ICAO_EGLL_EWD_SI.pdf) |
| Amsterdam Schiphol (EHAM) | 52.31 / 4.76 | −3 | 28 / 20 | −6 | 26.6 / 20.9 | −3.5 | **−1.4** | +2.5 | [ICAO_EHAM](https://www.ncei.noaa.gov/pub/access/cebrequests/engineeringwx/ICAO_EHAM_EWD_SI.pdf) |
| Brussels Nat’l (EBBR) | 50.90 / 4.48 | 56 | 29 / 20 | −6 | 28.8 / 21.0 | −4.5 | −0.2 | +1.5 | [ICAO_EBBR](https://www.ncei.noaa.gov/pub/access/cebrequests/engineeringwx/ICAO_EBBR_EWD_SI.pdf) |
| Dublin (EIDW) | 53.42 / −6.27 | 74 | 22 / 17 | −2 | 20.7 / 16.9 | −0.2 | **−1.3** | +1.8 | [ICAO_EIDW](https://www.ncei.noaa.gov/pub/access/cebrequests/engineeringwx/ICAO_EIDW_EWD_SI.pdf) |
| Edinburgh (EGPH) | 55.95 / −3.37 | 41 | 22 / 17 | −5 | 21.5 / 17.6 | −3.3 | −0.5 | +1.7 | [ICAO_EGPH](https://www.ncei.noaa.gov/pub/access/cebrequests/engineeringwx/ICAO_EGPH_EWD_SI.pdf) |
| Paris Orly (LFPO) | 48.73 / 2.36 | 89 | 31 / 20 | −5 | 30.3 / 20.9 | −3.7 | −0.7 | +1.3 | [ICAO_LFPO](https://www.ncei.noaa.gov/pub/access/cebrequests/engineeringwx/ICAO_LFPO_EWD_SI.pdf) |
| Madrid Barajas (LEMD) | 40.49 / −3.57 | 610 | 37 / 19 | −4 | 36.2 / 18.0 | −2.0 | −0.8 | +2.0 | [ICAO_LEMD](https://www.ncei.noaa.gov/pub/access/cebrequests/engineeringwx/ICAO_LEMD_EWD_SI.pdf) |

**Reading the deltas**

- **Cooling extremes:** ERA5 dry-bulb is systematically lower (damped) vs station
  0.4% values — typically ~0.5–1.8 K for this set. That matches the known
  reanalysis “grid-cell average” behaviour called out in code/spec comments.
- **Heating extremes:** ERA5 99.6% is often milder (less cold) by ~0.5–2.5 K.
- **MCWB:** Coincident wet-bulb can run slightly higher or lower; treat as
  indicative when using reanalysis.

**Product implications**

1. UI must disclose ERA5 / not licensed ASHRAE–CIBSE provenance wherever design
   conditions are shown (see Weather page + Methodology page).
2. No silent correction factor is applied today — licensed station data is the
   planned Pro path. If reanalysis stays as a fallback, prefer a more
   conservative cooling percentile or an explicit uplift after further QA; do
   not ship a hidden fudge.
3. For critical plant: always verify against ASHRAE Weather Data Viewer /
   CIBSE Guide A (or equivalent) for the nearest published station.

**Re-run**

```bash
cd web && .venv/bin/python -c "
import sys; sys.path[:0]=['../engine/src','.']
from app.weather_client import fetch_design_conditions
# lat, lon, elev_m for each site…
"
```
