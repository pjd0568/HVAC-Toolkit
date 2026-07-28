"""Air treatment processes: mixing, coils, humidification, AHU simulation.

Implemented from SPEC-ahu-processes.md (ASHRAE HOF 2017 Ch.1 process relations,
standard ADP/bypass-factor coil model, constant-wet-bulb evaporative cooling).

Flows are dry-air mass flow (kg/s). Duties kW, positive = heat added to the air.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hvac_engine import psychrometrics as psy
from hvac_engine.psychrometrics import PsychroState


# ── Result types ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MixResult:
    state: PsychroState
    m_da: float  # combined dry-air mass flow, kg/s
    fog: bool
    condensate: float  # kg/s, moisture dropped out if fog


@dataclass(frozen=True)
class ProcessResult:
    state: PsychroState
    q_sensible: float
    q_latent: float
    q_total: float


@dataclass(frozen=True)
class CoilResult:
    state: PsychroState
    q_sensible: float
    q_latent: float
    q_total: float
    shr: float
    condensate: float  # kg/s
    t_adp: float | None
    contact_factor: float | None
    bypass_factor: float | None
    frost_risk: bool


@dataclass(frozen=True)
class HumidifyResult:
    state: PsychroState
    steam_rate: float  # kg/s
    q_latent: float


@dataclass(frozen=True)
class AdiabaticResult:
    state: PsychroState
    water_rate: float  # kg/s
    q_total: float


@dataclass(frozen=True)
class DesiccantResult:
    """Outlet of a desiccant dehumidifier (isenthalpic / near-isenthalpic)."""

    state: PsychroState
    delta_w: float  # kg/kg, W_in − W_out (> 0 when drying)
    moisture_removed: float  # kg/s dry-basis water removed
    eta_d: float
    h_in: float
    h_out: float
    q_total: float  # kW to the airstream; 0 when ηd = 1 (ideal isenthalpic)
    dh_adsorption: float  # kJ/kg dry air, h_out − h_in


# Latent heat of vaporization used in the ASHRAE moist-air enthalpy equation (kJ/kg).
_H_FG = 2501.0


def desiccant_dehumidify(
    state_in: PsychroState,
    m_da: float,
    *,
    w_out: float | None = None,
    rh_out: float | None = None,
    moisture_removed: float | None = None,
    eta_d: float = 1.0,
) -> DesiccantResult:
    """Desiccant (solid/liquid) dehumidification — isenthalpic or near-isenthalpic.

    Water vapour is adsorbed/absorbed and the latent heat appears as a sensible
    temperature rise. Ideal model (``eta_d = 1``): constant enthalpy
    ``h_out = h_in``. Real-world (``eta_d < 1``): additional heat of adsorption
    / wheel heat carryover raises leaving enthalpy above the isenthalpic line::

        h_out = h_in + (1 − η_d) · h_fg · (W_in − W_out)

    Provide exactly one leaving-moisture contract:
    - ``w_out`` — target humidity ratio (kg/kg), or
    - ``rh_out`` — target leaving RH (0–1), solved with the enthalpy model, or
    - ``moisture_removed`` — water removal rate (kg/s); then
      ``W_out = W_in − moisture_removed / m_da``.
    """
    if m_da <= 0:
        raise ValueError("mass flow must be positive")
    if not (0.0 < eta_d <= 1.0):
        raise ValueError("desiccant efficiency must be in (0, 1]")

    n_targets = sum(x is not None for x in (w_out, rh_out, moisture_removed))
    if n_targets != 1:
        raise ValueError("provide exactly one of w_out, rh_out, or moisture_removed")

    if moisture_removed is not None:
        if moisture_removed <= 0:
            raise ValueError("moisture removal rate must be positive")
        w_out = state_in.w - moisture_removed / m_da
        if w_out < 0:
            raise ValueError(
                "moisture removal exceeds the water content of the airstream"
            )

    if w_out is not None:
        if w_out >= state_in.w * (1.0 - 1e-12):
            raise ValueError(
                "leaving humidity ratio must be below the entering value"
            )
        if w_out < 0:
            raise ValueError("leaving humidity ratio cannot be negative")
        s_out = _desiccant_outlet(state_in, w_out, eta_d)
    else:
        assert rh_out is not None
        if not (0.0 < rh_out <= 1.0):
            raise ValueError("leaving RH must be in (0, 1]")
        s_out = _desiccant_outlet_for_rh(state_in, rh_out, eta_d)
        w_out = s_out.w

    delta_w = state_in.w - w_out
    removed = m_da * delta_w
    dh = s_out.h - state_in.h
    return DesiccantResult(
        state=s_out,
        delta_w=delta_w,
        moisture_removed=removed,
        eta_d=eta_d,
        h_in=state_in.h,
        h_out=s_out.h,
        q_total=m_da * dh,
        dh_adsorption=dh,
    )


def _desiccant_outlet(
    state_in: PsychroState, w_out: float, eta_d: float
) -> PsychroState:
    """Leaving state at ``w_out`` on the (near-)isenthalpic process line."""
    dh_extra = (1.0 - eta_d) * _H_FG * (state_in.w - w_out)
    h_out = state_in.h + dh_extra
    return psy.state(h=h_out, w=w_out, p=state_in.p)


def _desiccant_w_floor(h_out: float, p: float) -> float:
    """Lowest humidity ratio that still resolves under ``state(h, w)``."""
    # Dew-point correlation needs p_w above sat(T_MIN).
    w_dp = psy.saturation_humidity_ratio(psy.T_MIN, p) * 1.001
    # dry_bulb_from_enthalpy must stay ≤ T_MAX as W falls (T rises).
    denom = _H_FG + psy.T_MAX * 1.86
    w_tmax = max(0.0, (h_out - psy.T_MAX * 1.006) / denom)
    return max(w_dp, w_tmax) + 1e-9


def _desiccant_outlet_for_rh(
    state_in: PsychroState, rh_out: float, eta_d: float
) -> PsychroState:
    """Solve ``W_out`` so the near-isenthalpic outlet lands at ``rh_out``."""
    # Lower W → higher T on the process line → lower RH. Bracket W below W_in.
    hi = state_in.w * (1.0 - 1e-9)
    # Floor uses the ideal (lowest) leaving enthalpy for the driest reachable state.
    h_at_floor = state_in.h  # ηd=1 lower bound; extra heat only raises T further
    lo = _desiccant_w_floor(h_at_floor, state_in.p)
    if lo >= hi:
        raise ValueError("entering state leaves no valid desiccant process range")
    s_hi = _desiccant_outlet(state_in, hi, eta_d)
    s_lo = _desiccant_outlet(state_in, lo, eta_d)
    if rh_out > s_hi.rh + 1e-9:
        raise ValueError(
            "target leaving RH is above the near-isenthalpic process line "
            "at the entering moisture — lower the RH target or raise ηd"
        )
    if rh_out < s_lo.rh - 1e-9:
        raise ValueError(
            "target leaving RH is below what the process can reach at this "
            "entering condition"
        )
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        s_mid = _desiccant_outlet(state_in, mid, eta_d)
        if s_mid.rh > rh_out:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-12:
            break
    return _desiccant_outlet(state_in, 0.5 * (lo + hi), eta_d)


# ── Elementary processes ───────────────────────────────────────────────────────

def _saturated_state_at_enthalpy(h: float, p: float) -> PsychroState:
    """Saturated state (rh = 1) with the given enthalpy, by bisection on t."""
    lo, hi = psy.T_MIN, psy.T_MAX
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        h_sat = psy.enthalpy(mid, psy.saturation_humidity_ratio(mid, p))
        if h_sat < h:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-9:
            break
    t = 0.5 * (lo + hi)
    return psy.state(t, rh=1.0, p=p)


def mix(
    state_a: PsychroState,
    m_da_a: float,
    state_b: PsychroState,
    m_da_b: float,
) -> MixResult:
    """Adiabatic mixing of two airstreams (dry-air mass & energy balance)."""
    if m_da_a < 0 or m_da_b < 0 or (m_da_a + m_da_b) <= 0:
        raise ValueError("mass flows must be positive")
    if abs(state_a.p - state_b.p) > 1e-6:
        raise ValueError("airstreams must be at the same barometric pressure")
    p = state_a.p
    m = m_da_a + m_da_b
    w_mix = (m_da_a * state_a.w + m_da_b * state_b.w) / m
    h_mix = (m_da_a * state_a.h + m_da_b * state_b.h) / m
    try:
        s = psy.state(h=h_mix, w=w_mix, p=p)
        return MixResult(state=s, m_da=m, fog=False, condensate=0.0)
    except ValueError:
        # Supersaturated mixture (fog): settle to saturation at the same enthalpy.
        s = _saturated_state_at_enthalpy(h_mix, p)
        condensate = m * max(w_mix - s.w, 0.0)
        return MixResult(state=s, m_da=m, fog=True, condensate=condensate)


def sensible(state_in: PsychroState, m_da: float, t_out: float) -> ProcessResult:
    """Constant-moisture heating or cooling to t_out."""
    if m_da <= 0:
        raise ValueError("mass flow must be positive")
    s_out = psy.state(t_out, w=state_in.w, p=state_in.p)  # raises if supersaturated
    q = m_da * (s_out.h - state_in.h)
    return ProcessResult(state=s_out, q_sensible=q, q_latent=0.0, q_total=q)


def cooling_coil(
    state_on: PsychroState,
    m_da: float,
    *,
    t_adp: float | None = None,
    t_off: float | None = None,
    bypass_factor: float | None = None,
    rh_off: float | None = None,
) -> CoilResult:
    """Real-world ADP / bypass-factor cooling coil.

    A coil cannot set dry-bulb and moisture independently. The process is the
    straight psychrometric chord from air-on ``(T1, W1)`` to the apparatus dew
    point on the saturation curve; off-coil air sits on that chord.

    Provide **apparatus dew point** ``t_adp`` plus either:
    - ``t_off`` — how far along the chord (BF follows), or
    - ``bypass_factor`` — BF in ``[0, 1)`` (``t_off`` follows).

    Legacy convenience: ``t_off`` + ``rh_off`` (no ``t_adp``) solves for the ADP
    that places the leaving state at that RH on the chord — used by AHU
    simulation when only an off-coil RH assumption is known.
    """
    if m_da <= 0:
        raise ValueError("mass flow must be positive")

    if t_adp is None:
        if t_off is None or rh_off is None:
            raise ValueError(
                "cooling coil requires t_adp with t_off or bypass_factor "
                "(or legacy t_off + rh_off)"
            )
        if t_off >= state_on.t_db:
            raise ValueError("off-coil temperature must be below on-coil temperature")
        t_adp = _solve_adp_for_leaving_rh(state_on, t_off, rh_off)
        return cooling_coil(
            state_on, m_da, t_adp=t_adp, t_off=t_off
        )

    if t_adp >= state_on.t_db - 1e-9:
        raise ValueError("apparatus dew point must be below on-coil dry bulb")

    if bypass_factor is not None and t_off is not None:
        raise ValueError("provide t_off or bypass_factor, not both")
    if bypass_factor is None and t_off is None:
        raise ValueError("provide t_off or bypass_factor with t_adp")

    if bypass_factor is not None:
        if not (0.0 <= bypass_factor < 1.0):
            raise ValueError("bypass factor must be in [0, 1)")
        t_off = t_adp + bypass_factor * (state_on.t_db - t_adp)
    else:
        assert t_off is not None
        if t_off > state_on.t_db + 1e-9:
            raise ValueError("off-coil temperature must be at or below on-coil temperature")
        if t_off < t_adp - 1e-9:
            raise ValueError(
                "off-coil temperature cannot be below the apparatus dew point"
            )
        denom = state_on.t_db - t_adp
        bypass_factor = (t_off - t_adp) / denom if abs(denom) > 1e-12 else 0.0

    bf = float(bypass_factor)
    cf = 1.0 - bf
    p = state_on.p
    wet = t_adp < state_on.t_dp - 1e-9

    if wet:
        w_adp = psy.saturation_humidity_ratio(t_adp, p)
        w_off = w_adp + bf * (state_on.w - w_adp)
        s_off = psy.state(t_off, w=w_off, p=p)
    else:
        # ADP at or above entering dew point → dry coil, constant moisture.
        if t_off < state_on.t_dp - 1e-6:
            raise ValueError(
                "dry-coil off-coil temperature is below the entering dew point; "
                "lower the apparatus dew point to dehumidify, or raise t_off"
            )
        s_off = psy.state(t_off, w=state_on.w, p=p)

    q_total = m_da * (s_off.h - state_on.h)
    q_sensible = m_da * (
        psy.enthalpy(t_off, state_on.w) - psy.enthalpy(state_on.t_db, state_on.w)
    )
    q_latent = q_total - q_sensible
    shr = q_sensible / q_total if q_total != 0 else 1.0
    condensate = m_da * max(state_on.w - s_off.w, 0.0)
    frost = t_adp <= 0.0

    return CoilResult(
        state=s_off,
        q_sensible=q_sensible,
        q_latent=q_latent,
        q_total=q_total,
        shr=shr,
        condensate=condensate,
        t_adp=t_adp,
        contact_factor=cf,
        bypass_factor=bf,
        frost_risk=frost,
    )


def _solve_adp_for_leaving_rh(
    s_on: PsychroState, t_off: float, rh_off: float
) -> float:
    """Find ADP so the forward coil model leaves at ``(t_off, rh_off)``.

    Used when only an off-coil RH design assumption is available (AHU sim).
    Extends the chord through air-on and the prescribed off-coil point to the
    saturation curve (same geometry as the forward ADP model).
    """
    if not (0.0 < rh_off <= 1.0):
        raise ValueError("off-coil RH must be in (0, 1]")
    s_off = psy.state(t_off, rh=rh_off, p=s_on.p)
    if s_off.w > s_on.w * (1.0 + 1e-9):
        raise ValueError(
            "off-coil moisture content exceeds on-coil: a cooling coil cannot "
            "humidify — reduce off-coil RH or raise off-coil temperature"
        )
    if abs(s_off.w - s_on.w) < 1e-12:
        return s_on.t_dp
    t_adp = _apparatus_dew_point(s_on, s_off)
    if t_adp is None:
        raise ValueError(
            "no apparatus dew point on the saturation curve for this off-coil "
            "state — the process is effectively dry / too shallow to dehumidify"
        )
    return t_adp


def _apparatus_dew_point(
    s_on: PsychroState, s_off: PsychroState
) -> float | None:
    """Intersection of the on→off process line with the saturation curve.

    The line is extended beyond the off-coil point toward saturation:
    w_line(t) = w_on + (t − t_on) · slope. Solved by bisection on
    f(t) = w_line(t) − W_s(t), which is positive above the curve.
    """
    p = s_on.p
    dt = s_off.t_db - s_on.t_db
    if abs(dt) < 1e-12:
        return None
    slope = (s_off.w - s_on.w) / dt

    def f(t: float) -> float:
        w_line = s_on.w + (t - s_on.t_db) * slope
        return w_line - psy.saturation_humidity_ratio(t, p)

    if s_off.rh >= 1.0 - 1e-9:
        return s_off.t_db

    hi = s_off.t_db
    lo = hi
    step = 1.0
    while lo > psy.T_MIN:
        lo = max(lo - step, psy.T_MIN)
        if f(lo) >= 0.0:
            break
        step *= 2.0
    if f(lo) < 0.0:
        return None

    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if f(mid) >= 0.0:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-9:
            break
    return 0.5 * (lo + hi)


def steam_humidify(
    state_in: PsychroState, m_da: float, w_out: float
) -> HumidifyResult:
    """Isothermal steam injection to a target humidity ratio."""
    if m_da <= 0:
        raise ValueError("mass flow must be positive")
    if w_out < state_in.w * (1.0 - 1e-9):
        raise ValueError("steam humidifier cannot reduce moisture content")
    s_out = psy.state(state_in.t_db, w=w_out, p=state_in.p)  # raises if supersat.
    steam = m_da * (w_out - state_in.w)
    q_latent = m_da * (s_out.h - state_in.h)
    return HumidifyResult(state=s_out, steam_rate=steam, q_latent=q_latent)


@dataclass(frozen=True)
class HeatHumidifyResult:
    """Sensible heat then isothermal steam humidification (AHU winter path)."""

    state_x: PsychroState  # after heating coil, before humidifier (T2, W1)
    state: PsychroState  # final leaving (T2, W2)
    q_sensible: float  # kW heating coil
    q_latent: float  # kW steam / latent to airstream
    q_total: float
    steam_rate: float  # kg/s


def heat_and_humidify(
    state_in: PsychroState,
    m_da: float,
    *,
    t_out: float | None = None,
    w_out: float | None = None,
    q_sensible: float | None = None,
    steam_rate: float | None = None,
) -> HeatHumidifyResult:
    """Sensible heating at constant W, then isothermal steam humidification.

    Process path on the psychrometric chart::

        (1) ──constant W──► (X) ──constant T──► (2)
              heating coil         steam

    Mode A — state targets: provide ``t_out`` and ``w_out``.
    Mode B — duties: provide ``q_sensible`` (kW) and ``steam_rate`` (kg/s);
    either may be zero if the other is positive.

    Sensible duty uses moist-air enthalpy at constant W (equivalent to
    ``m · (1.006 + 1.86·W) · ΔT``). Latent duty is the isothermal steam
    enthalpy rise (≈ ``m_w · h_fg``).
    """
    if m_da <= 0:
        raise ValueError("mass flow must be positive")

    state_mode = t_out is not None and w_out is not None
    duty_mode = q_sensible is not None and steam_rate is not None
    if state_mode == duty_mode:
        raise ValueError(
            "provide either t_out + w_out (state mode) or "
            "q_sensible + steam_rate (duty mode)"
        )

    if duty_mode:
        assert q_sensible is not None and steam_rate is not None
        if q_sensible < -1e-12:
            raise ValueError("sensible heating duty cannot be negative")
        if steam_rate < -1e-12:
            raise ValueError("steam rate cannot be negative")
        if q_sensible <= 1e-12 and steam_rate <= 1e-12:
            raise ValueError("provide a positive heating duty and/or steam rate")
        cp = 1.006 + 1.86 * state_in.w
        t_out = state_in.t_db + q_sensible / (m_da * cp)
        w_out = state_in.w + steam_rate / m_da

    assert t_out is not None and w_out is not None
    if t_out < state_in.t_db - 1e-9:
        raise ValueError(
            "leaving dry bulb is below entering — this process is heating only"
        )
    if w_out < state_in.w * (1.0 - 1e-9):
        raise ValueError(
            "leaving humidity ratio is below entering — steam humidification "
            "cannot dry the air"
        )

    # State X: heated to t_out at constant W1 (may equal state_in if no heat).
    if abs(t_out - state_in.t_db) < 1e-9:
        state_x = state_in
        q_s = 0.0
    else:
        heated = sensible(state_in, m_da, t_out)
        state_x = heated.state
        q_s = heated.q_total

    # State 2: isothermal steam to w_out (may equal X if no steam).
    if abs(w_out - state_in.w) < 1e-12:
        state_2 = state_x
        steam = 0.0
        q_l = 0.0
    else:
        hum = steam_humidify(state_x, m_da, w_out)
        state_2 = hum.state
        steam = hum.steam_rate
        q_l = hum.q_latent

    return HeatHumidifyResult(
        state_x=state_x,
        state=state_2,
        q_sensible=q_s,
        q_latent=q_l,
        q_total=q_s + q_l,
        steam_rate=steam,
    )


def adiabatic_humidify(
    state_in: PsychroState, m_da: float, effectiveness: float
) -> AdiabaticResult:
    """Evaporative humidification along the constant wet-bulb line."""
    if m_da <= 0:
        raise ValueError("mass flow must be positive")
    if not (0.0 < effectiveness <= 1.0):
        raise ValueError("effectiveness must be in (0, 1]")
    t_out = state_in.t_db - effectiveness * (state_in.t_db - state_in.t_wb)
    s_out = psy.state(t_out, twb=state_in.t_wb, p=state_in.p)
    water = m_da * (s_out.w - state_in.w)
    q_total = m_da * (s_out.h - state_in.h)
    return AdiabaticResult(state=s_out, water_rate=water, q_total=q_total)


def fan_gain(
    state_in: PsychroState,
    m_da: float,
    *,
    power_kw: float | None = None,
    dt: float | None = None,
) -> ProcessResult:
    """Sensible pick-up across a fan at constant moisture (SPEC: fan_gain).

    power_kw is the fan power absorbed by the airstream; for an in-airstream
    motor this is effectively the full electrical input.
    ΔT = P / (m_da · c_p,moist), c_p,moist = 1.006 + 1.86·W.
    """
    if (power_kw is None) == (dt is None):
        raise ValueError("give exactly one of power_kw or dt")
    if power_kw is not None:
        if power_kw < 0.0:
            raise ValueError("fan power must be >= 0")
        cp = 1.006 + 1.86 * state_in.w
        dt = power_kw / (m_da * cp)
    if dt < 0.0:
        raise ValueError("fan temperature rise must be >= 0")
    return sensible(state_in, m_da, state_in.t_db + dt)


# ── AHU duty simulation ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AhuStage:
    label: str  # OA / RA / MA / FROST / CC / HC / HUM / SUP
    name: str
    state: PsychroState
    q_sensible: float = 0.0
    q_latent: float = 0.0
    q_total: float = 0.0
    moisture: float = 0.0  # kg/s; + added to air, − removed (condensate)
    note: str = ""


@dataclass(frozen=True)
class AhuResult:
    stages: list[AhuStage]
    m_da: float
    heating_total: float  # kW, sum of positive duties
    cooling_total: float  # kW, sum of negative duties (negative number)
    moisture_added: float  # kg/s
    moisture_removed: float  # kg/s
    frost_risk: bool
    warnings: list[str] = field(default_factory=list)


def simulate_ahu(
    *,
    m_da: float,
    outdoor: PsychroState,
    return_air: PsychroState | None = None,
    oa_fraction: float = 1.0,
    frost_coil_t: float | None = None,
    coil_t_off: float | None = None,
    coil_rh_off: float = 0.90,
    reheat_t: float | None = None,
    steam_rh_target: float | None = None,
    adiabatic_effectiveness: float | None = None,
    fan_position: str = "draw",
    fan_power_kw: float | None = None,
    fan_pickup_dt: float = 0.0,
) -> AhuResult:
    """Chain AHU stages: mix → frost coil → cooling coil → reheat → humidifier → fan.

    m_da is the supply dry-air mass flow. oa_fraction is the outdoor-air fraction
    by dry-air mass (1.0 = full fresh air).
    """
    if not (0.0 < oa_fraction <= 1.0):
        raise ValueError("outdoor air fraction must be in (0, 1]")
    if oa_fraction < 1.0 and return_air is None:
        raise ValueError("return air state required when oa_fraction < 1")
    if steam_rh_target is not None and adiabatic_effectiveness is not None:
        raise ValueError("choose steam or adiabatic humidification, not both")
    if fan_position not in ("blow", "draw"):
        raise ValueError("fan_position must be 'blow' or 'draw'")

    def _fan(cur: PsychroState) -> ProcessResult | None:
        if fan_power_kw is not None and fan_power_kw > 0.0:
            return fan_gain(cur, m_da, power_kw=fan_power_kw)
        if fan_pickup_dt > 0.0:
            return fan_gain(cur, m_da, dt=fan_pickup_dt)
        return None

    stages: list[AhuStage] = []
    warnings: list[str] = []
    frost = False

    stages.append(AhuStage("OA", "Outdoor air", outdoor))
    current = outdoor

    if oa_fraction < 1.0:
        assert return_air is not None
        stages.append(AhuStage("RA", "Return air", return_air))
        mx = mix(outdoor, m_da * oa_fraction, return_air, m_da * (1 - oa_fraction))
        note = ""
        if mx.fog:
            note = "Mixed condition is in the fog region — settled to saturation."
            warnings.append(note)
        stages.append(
            AhuStage("MA", "Mixed air", mx.state, moisture=-mx.condensate, note=note)
        )
        current = mx.state

    if frost_coil_t is not None and frost_coil_t > current.t_db:
        r = sensible(current, m_da, frost_coil_t)
        stages.append(
            AhuStage(
                "FROST", "Frost coil (preheat)", r.state,
                q_sensible=r.q_sensible, q_total=r.q_total,
            )
        )
        current = r.state

    if fan_position == "blow":
        r = _fan(current)
        if r is not None:
            stages.append(
                AhuStage(
                    "FAN", "Supply fan (blow-through)", r.state,
                    q_sensible=r.q_sensible, q_total=r.q_total,
                    note=f"Fan gain +{r.state.t_db - current.t_db:.2f} K",
                )
            )
            current = r.state

    if coil_t_off is not None:
        c = cooling_coil(current, m_da, t_off=coil_t_off, rh_off=coil_rh_off)
        note = ""
        if c.frost_risk:
            frost = True
            note = (
                f"Frost risk: apparatus dew point {c.t_adp:.1f} degC is at or below "
                "freezing — consider glycol, DX defrost strategy or face-and-bypass."
            )
            warnings.append(note)
        stages.append(
            AhuStage(
                "CC", "Cooling coil", c.state,
                q_sensible=c.q_sensible, q_latent=c.q_latent, q_total=c.q_total,
                moisture=-c.condensate, note=note,
            )
        )
        current = c.state

    if reheat_t is not None and reheat_t > current.t_db:
        r = sensible(current, m_da, reheat_t)
        stages.append(
            AhuStage(
                "HC", "Heating coil", r.state,
                q_sensible=r.q_sensible, q_total=r.q_total,
            )
        )
        current = r.state

    if steam_rh_target is not None:
        w_target = psy.humidity_ratio_from_rh(
            current.t_db, steam_rh_target, current.p
        )
        if w_target > current.w:
            hm = steam_humidify(current, m_da, w_target)
            stages.append(
                AhuStage(
                    "HUM", "Steam humidifier", hm.state,
                    q_latent=hm.q_latent, q_total=hm.q_latent,
                    moisture=hm.steam_rate,
                )
            )
            current = hm.state
        else:
            warnings.append(
                "Steam humidifier inactive: air is already at or above the "
                "target relative humidity."
            )
    elif adiabatic_effectiveness is not None:
        ad = adiabatic_humidify(current, m_da, adiabatic_effectiveness)
        stages.append(
            AhuStage(
                "HUM", "Adiabatic humidifier", ad.state,
                q_total=ad.q_total, moisture=ad.water_rate,
            )
        )
        current = ad.state

    r = _fan(current) if fan_position == "draw" else None
    if r is not None:
        stages.append(
            AhuStage(
                "SUP", "Supply (after draw-through fan)", r.state,
                q_sensible=r.q_sensible, q_total=r.q_total,
                note=f"Fan gain +{r.state.t_db - current.t_db:.2f} K",
            )
        )
        current = r.state
    else:
        stages.append(AhuStage("SUP", "Supply", current))

    heating = sum(s.q_total for s in stages if s.q_total > 0)
    cooling = sum(s.q_total for s in stages if s.q_total < 0)
    added = sum(s.moisture for s in stages if s.moisture > 0)
    removed = -sum(s.moisture for s in stages if s.moisture < 0)

    return AhuResult(
        stages=stages,
        m_da=m_da,
        heating_total=heating,
        cooling_total=cooling,
        moisture_added=added,
        moisture_removed=removed,
        frost_risk=frost,
        warnings=warnings,
    )
