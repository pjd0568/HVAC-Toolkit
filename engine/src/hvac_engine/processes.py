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
    t_off: float,
    rh_off: float,
) -> CoilResult:
    """Dehumidifying (or dry) cooling coil defined by its off-coil condition."""
    if m_da <= 0:
        raise ValueError("mass flow must be positive")
    if t_off >= state_on.t_db:
        raise ValueError("off-coil temperature must be below on-coil temperature")
    s_off = psy.state(t_off, rh=rh_off, p=state_on.p)
    if s_off.w > state_on.w * (1.0 + 1e-9):
        raise ValueError(
            "off-coil moisture content exceeds on-coil: a cooling coil cannot "
            "humidify — reduce off-coil RH or raise off-coil temperature"
        )

    q_total = m_da * (s_off.h - state_on.h)
    q_sensible = m_da * (
        psy.enthalpy(t_off, state_on.w) - psy.enthalpy(state_on.t_db, state_on.w)
    )
    q_latent = q_total - q_sensible
    shr = q_sensible / q_total if q_total != 0 else 1.0
    condensate = m_da * (state_on.w - s_off.w)

    t_adp = _apparatus_dew_point(state_on, s_off)
    if t_adp is not None and abs(state_on.t_db - t_adp) > 1e-9:
        cf = (state_on.t_db - t_off) / (state_on.t_db - t_adp)
        bf = 1.0 - cf
    else:
        cf = bf = None
    frost = t_adp is not None and t_adp <= 0.0

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

    # A saturated off-coil condition IS the apparatus dew point.
    if s_off.rh >= 1.0 - 1e-9:
        return s_off.t_db

    # Subsaturated points sit below the saturation curve, so f(t_off) < 0.
    # Extending the line to lower temperatures, W_s(t) falls away exponentially
    # and the line crosses it at the ADP (f becomes >= 0). Walk down for the
    # sign change, then bisect. No crossing above T_MIN -> no ADP (line steeper
    # than the curve; effectively a dry/sensible process).
    hi = s_off.t_db
    lo = hi
    step = 1.0
    while lo > psy.T_MIN:
        lo = max(lo - step, psy.T_MIN)
        if f(lo) >= 0.0:
            break
        step *= 2.0
    if f(lo) < 0.0:
        return None  # no intersection within the valid range

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
        c = cooling_coil(current, m_da, coil_t_off, coil_rh_off)
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
