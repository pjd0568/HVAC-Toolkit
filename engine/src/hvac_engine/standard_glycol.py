"""ASHRAE aqueous ethylene / monopropylene glycol property correlations.

Coefficients are the CoolProp AEG / APG fits to ASHRAE Handbook secondary-
coolant tables (ASHRAE 2001; Skovrup 2013). Concentration input is volume
fraction — matching the pipe module's % v/v catalogue.

Catalogue mix percentages mirror the Hydratech Coolflow IGE (EG) and NTP
(PPG) grids so engineers can compare proprietary blends with uninhibited
library fluids at the same % v/v.
"""

from __future__ import annotations

from math import exp
from typing import Literal

from hvac_engine.glycol_data import GLYCOL_CONCENTRATIONS_PCT as _HYDRATECH_CONCS

FluidId = Literal["eg", "mpg"]

FLUID_LABELS: dict[FluidId, str] = {
    "eg": "Ethylene glycol (ASHRAE)",
    "mpg": "Monopropylene glycol (ASHRAE)",
}

# Same % v/v ladders as Coolflow IGE (EG) and Coolflow NTP (PPG).
GLYCOL_CONCENTRATIONS_PCT: dict[FluidId, tuple[int, ...]] = {
    "eg": tuple(_HYDRATECH_CONCS["epg"]),
    "mpg": tuple(_HYDRATECH_CONCS["ppg"]),
}

# CoolProp INCOMP::AEG / APG — rows = powers of (T − Tbase), columns = powers
# of (x − xbase). Viscosity and freeze point use exp(polynomial).
_AEG = {
    "Tbase": 305.65,
    "xbase": 0.35,
    "Tmin": 238.15,
    "Tmax": 373.15,
    "T_freeze": (
        (5.534468, -0.3574293, -0.6535113, -0.9039166, 1.048048, 4.622116),
    ),
    "density": (
        (1047.337, 140.4485, -48.70559, 71.41693, 52.4585, -693.3962),
        (-0.4505054, -0.3001582, -0.03952614, 0.02496264, -0.06817576, 0.0),
        (-0.002432696, -2.084384e-05, 0.0003108353, -0.0008979712, 0.0, 0.0),
        (-3.72545e-09, 1.044784e-06, -4.391164e-06, 0.0, 0.0, 0.0),
    ),
    "cp": (
        (3596.551, -1707.073, -444.7538, -552.7923, -715.9059, 7905.301),
        (3.096886, 5.184379, -0.7061384, 0.7949891, -0.6689394, 0.0),
        (-3.388642e-05, 0.0003639717, 0.0009169943, -0.005359818, 0.0, 0.0),
        (3.171299e-07, -2.457345e-06, 1.419543e-05, 0.0, 0.0, 0.0),
    ),
    "viscosity": (
        (-6.319551, 2.881296, 0.8374394, -19.29626, -13.10981, 252.8586),
        (-0.02410848, -0.01593008, -0.006961209, -0.06322254, -0.2651482, 0.0),
        (0.0001764482, 0.0001708786, -0.0004014337, -0.00024771, 0.0, 0.0),
        (-1.315418e-06, -1.745316e-06, 9.973464e-06, 0.0, 0.0, 0.0),
    ),
}

_APG = {
    "Tbase": 305.65,
    "xbase": 0.35,
    "Tmin": 238.15,
    "Tmax": 373.15,
    "T_freeze": (
        (5.546103, -0.326277, -0.6666873, -0.8800598, -1.071417, -1.875782),
    ),
    "density": (
        (1026.177, 72.53677, -65.32547, 34.66575, -15.82785, -213.9879),
        (-0.5350059, -0.5056296, 0.1751278, -0.092333, 0.02877433, 0.0),
        (-0.002566157, -0.0001703579, 0.001165892, -0.000207517, 0.0, 0.0),
        (-5.177362e-09, 9.673215e-09, 3.368862e-07, 0.0, 0.0, 0.0),
    ),
    "cp": (
        (3815.392, -1391.877, -1121.4, -419.3939, -243.53, 4054.145),
        (3.025751, 5.558605, -0.1073388, 0.5290725, -2.262081, 0.0),
        (4.165345e-05, -9.03207e-05, -0.003392169, 0.01079472, 0.0, 0.0),
        (-4.309483e-07, -1.33518e-06, 3.538903e-05, 0.0, 0.0, 0.0),
    ),
    "viscosity": (
        (-6.025825, 3.573663, -1.995205, -6.42511, 36.01949, 53.50879),
        (-0.03284399, -0.03838339, 0.08223532, 0.01520795, -1.123741, 0.0),
        (0.0002492009, 0.0003529886, -0.0005119547, -0.0006572286, 0.0, 0.0),
        (-1.155771e-06, -1.216539e-06, 3.230125e-06, 0.0, 0.0, 0.0),
    ),
}

_FLUIDS: dict[FluidId, dict] = {
    "eg": _AEG,
    "mpg": _APG,
}


def _eval_poly(
    coeffs: tuple[tuple[float, ...], ...],
    theta: float,
    xi: float,
) -> float:
    total = 0.0
    for i, row in enumerate(coeffs):
        for j, a in enumerate(row):
            total += a * (theta**i) * (xi**j)
    return total


def glycol_concentrations(fluid: FluidId) -> tuple[int, ...]:
    return GLYCOL_CONCENTRATIONS_PCT[fluid]


def freeze_point_c(fluid: FluidId, concentration_pct: int) -> float:
    if concentration_pct not in GLYCOL_CONCENTRATIONS_PCT[fluid]:
        allowed = GLYCOL_CONCENTRATIONS_PCT[fluid]
        raise ValueError(
            f"glycol concentration must be one of {allowed}, got {concentration_pct!r}"
        )
    model = _FLUIDS[fluid]
    xi = concentration_pct / 100.0 - model["xbase"]
    return exp(_eval_poly(model["T_freeze"], 0.0, xi)) - 273.15


def fluid_properties_si(
    fluid: FluidId,
    temperature_c: float,
    concentration_pct: int,
) -> tuple[float, float, float, float]:
    """Return (ρ kg/m³, μ Pa·s, cp J/kg·K, freeze °C) at T and % v/v."""
    if concentration_pct not in GLYCOL_CONCENTRATIONS_PCT[fluid]:
        allowed = GLYCOL_CONCENTRATIONS_PCT[fluid]
        raise ValueError(
            f"glycol concentration must be one of {allowed}, got {concentration_pct!r}"
        )
    model = _FLUIDS[fluid]
    fp_c = freeze_point_c(fluid, concentration_pct)
    t_k = temperature_c + 273.15
    # Stay inside the correlation envelope and above freeze (same clamp idea
    # as the Hydratech tabulated grids).
    t_lo = max(model["Tmin"], fp_c + 273.15)
    t_k = min(model["Tmax"], max(t_lo, t_k))
    theta = t_k - model["Tbase"]
    xi = concentration_pct / 100.0 - model["xbase"]
    rho = _eval_poly(model["density"], theta, xi)
    cp = _eval_poly(model["cp"], theta, xi)
    mu = exp(_eval_poly(model["viscosity"], theta, xi))
    return rho, mu, cp, fp_c


__all__ = [
    "FLUID_LABELS",
    "FluidId",
    "GLYCOL_CONCENTRATIONS_PCT",
    "fluid_properties_si",
    "freeze_point_c",
    "glycol_concentrations",
]
