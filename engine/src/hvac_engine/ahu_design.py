"""Supply-driven AHU design — the inverse of ``processes.simulate_ahu``.

Implemented from SPEC-ahu-processes.md (``design_ahu_to_supply``). Instead of
specifying the off-coil condition and reading off the supply, the user gives the
**required supply (off-unit) condition** and the solver derives the intermediate
stages that reach it: mix OA/RA to the on-coil condition, check the supply is
reachable, then cool to the supply moisture at a target off-coil RH (default
90%, matching ``simulate_ahu`` / typical wet-coil practice) and reheat to the
supply dry bulb. ``coil_rh_off=1.0`` recovers the idealised CF = 1 model
(saturated at the supply dew point).

Pure Python; depends only on ``hvac_engine.psychrometrics`` and the shared result
types / elementary processes in ``hvac_engine.processes``.
"""

from __future__ import annotations

from hvac_engine import psychrometrics as psy
from hvac_engine.psychrometrics import PsychroState
from hvac_engine.processes import AhuResult, AhuStage, mix, sensible

_W_TOL = 1e-5  # kg/kg (~0.01 g/kg): smaller differences are "no net moisture change"
_T_TOL = 1e-3  # degC


def _t_db_at_w_rh(w: float, rh: float, p: float) -> float:
    """Dry-bulb temperature at which (w, rh) is a valid psychrometric state.

    At rh = 1 the solution is the dew point. For rh < 1 the dry bulb sits above
    the dew point; solved by bisection on humidity_ratio_from_rh(t, rh) − w.
    """
    if not (0.0 < rh <= 1.0):
        raise ValueError("off-coil RH must be in (0, 1]")
    if w < 0.0:
        raise ValueError("humidity ratio must be >= 0")
    t_dp = psy.dew_point(w, p)
    if rh >= 1.0 - 1e-12:
        return t_dp
    # Upper bound: walk up until the RH isotherm carries at least w.
    lo, hi = t_dp, t_dp + 1.0
    while hi < psy.T_MAX and psy.humidity_ratio_from_rh(hi, rh, p) < w:
        hi += max(hi - t_dp, 1.0)
    if psy.humidity_ratio_from_rh(hi, rh, p) < w:
        raise ValueError(
            f"cannot reach humidity ratio {w * 1000:.2f} g/kg at "
            f"{rh * 100:.0f}% RH within the valid temperature range"
        )
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if psy.humidity_ratio_from_rh(mid, rh, p) < w:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-9:
            break
    return 0.5 * (lo + hi)


def _ahu_totals(
    stages: list[AhuStage], m_da: float, frost: bool, warnings: list[str]
) -> AhuResult:
    """Roll per-stage duties/moisture up into an AhuResult (shared with simulate_ahu)."""
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


def design_ahu_to_supply(
    *,
    m_da: float,
    supply: PsychroState,
    outdoor: PsychroState,
    return_air: PsychroState | None = None,
    oa_fraction: float = 1.0,
    coil_rh_off: float = 0.90,
    fan_position: str = "none",
    fan_power_kw: float | None = None,
    fan_pickup_dt: float = 0.0,
) -> AhuResult:
    """Design the AHU stages needed to deliver a required supply condition.

    Mixes OA/RA to the on-coil condition A, checks the required supply state is
    reachable by cooling (a coil cannot add moisture), then derives:

    - dehumidification: off-coil C holds the supply moisture at ``coil_rh_off``
      (default 0.90, matching ``simulate_ahu``); reheat C→D to the supply dry bulb.
      ``coil_rh_off=1.0`` is the idealised CF = 1 case (saturated at the supply
      dew point);
    - or a purely sensible cooling or heating duty when the supply moisture equals
      the on-coil moisture.

    A blow-through fan raises the on-coil condition before the coil; a draw-through
    fan sits after reheat, so the reheat coil targets ``t_sup − ΔT_fan``. Returns
    the same ``AhuResult`` shape as ``simulate_ahu``.
    """
    if m_da <= 0:
        raise ValueError("mass flow must be positive")
    if not (0.0 < oa_fraction <= 1.0):
        raise ValueError("outdoor air fraction must be in (0, 1]")
    if oa_fraction < 1.0 and return_air is None:
        raise ValueError("return air state required when oa_fraction < 1")
    if not (0.0 < coil_rh_off <= 1.0):
        raise ValueError("off-coil RH must be in (0, 1]")
    if fan_position not in ("none", "blow", "draw"):
        raise ValueError("fan_position must be 'none', 'blow' or 'draw'")

    p = outdoor.p
    stages: list[AhuStage] = []
    warnings: list[str] = []
    frost = False

    # 1. Intake / mixing -> on-coil condition A.
    stages.append(AhuStage("OA", "Outdoor air", outdoor))
    air_on = outdoor
    if oa_fraction < 1.0:
        assert return_air is not None
        stages.append(AhuStage("RA", "Return air", return_air))
        mx = mix(outdoor, m_da * oa_fraction, return_air, m_da * (1 - oa_fraction))
        note = ""
        if mx.fog:
            note = "Mixed condition is in the fog region — settled to saturation."
            warnings.append(note)
        stages.append(
            AhuStage("MA", "Mixed air (on-coil)", mx.state,
                     moisture=-mx.condensate, note=note)
        )
        air_on = mx.state

    # Fan temperature rise (constant moisture).
    def _fan_dt(s: PsychroState) -> float:
        if fan_power_kw is not None and fan_power_kw > 0.0:
            cp = 1.006 + 1.86 * s.w
            return fan_power_kw / (m_da * cp)
        return max(fan_pickup_dt, 0.0)

    # 2. Blow-through fan raises the on-coil condition before the coil.
    if fan_position == "blow":
        dt = _fan_dt(air_on)
        if dt > 0.0:
            r = sensible(air_on, m_da, air_on.t_db + dt)
            stages.append(
                AhuStage("FAN", "Supply fan (blow-through)", r.state,
                         q_sensible=r.q_sensible, q_total=r.q_total,
                         note=f"Fan gain +{dt:.2f} K")
            )
            air_on = r.state

    # A draw-through fan sits after reheat: target t_sup - dt_fan before the fan so
    # the air arrives at the supply temperature once the fan gain is added.
    dt_draw = _fan_dt(supply) if fan_position == "draw" else 0.0
    reheat_target = supply.t_db - dt_draw

    W_on = air_on.w
    W_sup = supply.w

    # Reachability: a cooling coil can only remove moisture.
    if W_sup > W_on + _W_TOL:
        raise ValueError(
            f"Required supply moisture ({W_sup * 1000:.2f} g/kg) exceeds the on-coil "
            f"moisture ({W_on * 1000:.2f} g/kg). A cooling coil can only remove "
            "moisture — this duty needs humidification, which this tool does not yet "
            "size. Lower the supply moisture, or add a humidifier stage."
        )

    def _finish(pre_fan: PsychroState) -> PsychroState:
        """Apply the draw-through fan (if any) and append the SUP stage."""
        if fan_position == "draw" and dt_draw > 0.0:
            r = sensible(pre_fan, m_da, pre_fan.t_db + dt_draw)
            stages.append(
                AhuStage("SUP", "Supply (after draw-through fan)", r.state,
                         q_sensible=r.q_sensible, q_total=r.q_total,
                         note=f"Fan gain +{dt_draw:.2f} K")
            )
            return r.state
        stages.append(AhuStage("SUP", "Supply", pre_fan))
        return pre_fan

    if abs(W_sup - W_on) <= _W_TOL:
        # ── Purely sensible duty (no net moisture change) ───────────────────────
        if reheat_target < air_on.t_db - _T_TOL:
            # Sensible (dry) cooling. sensible() guards against supersaturation.
            c = sensible(air_on, m_da, reheat_target)
            note = ""
            if reheat_target <= 0.0:
                frost = True
                note = (f"Frost risk: off-coil temperature {reheat_target:.1f} degC is "
                        "at or below freezing.")
                warnings.append(note)
            stages.append(
                AhuStage("CC", "Cooling coil (sensible)", c.state,
                         q_sensible=c.q_sensible, q_total=c.q_total, note=note)
            )
            final = _finish(c.state)
        elif reheat_target > air_on.t_db + _T_TOL:
            r = sensible(air_on, m_da, reheat_target)
            stages.append(
                AhuStage("HC", "Heating coil", r.state,
                         q_sensible=r.q_sensible, q_total=r.q_total)
            )
            final = _finish(r.state)
        else:
            final = _finish(air_on)
    else:
        # ── Dehumidification: off-coil at supply moisture + target RH ───────────
        t_off = _t_db_at_w_rh(W_sup, coil_rh_off, p)
        off = psy.state(t_off, w=W_sup, p=p)

        # Saturation-onset waypoint B (constant-w_on sensible cooling to the on-coil
        # dew point) — a zero-duty chart point when there is real sensible pre-cool.
        t_b = air_on.t_dp
        if air_on.t_db - t_b > _T_TOL:
            b = psy.state(t_b, w=W_on, p=p)
            stages.append(AhuStage("SAT", "Saturation onset", b,
                                   note="Waypoint — cooling continues to the coil."))

        q_total = m_da * (off.h - air_on.h)
        q_sensible = m_da * (
            psy.enthalpy(t_off, W_on) - psy.enthalpy(air_on.t_db, W_on)
        )
        q_latent = q_total - q_sensible
        condensate = m_da * (W_on - W_sup)
        note = (
            f"Off-coil modelled at {coil_rh_off * 100:.0f}% RH "
            f"(supply moisture {W_sup * 1000:.2f} g/kg)."
        )
        if t_off <= 0.0:
            frost = True
            frost_note = (
                f"Frost risk: off-coil temperature {t_off:.1f} degC is at "
                "or below freezing — consider glycol, DX defrost or face-and-bypass."
            )
            note = f"{note} {frost_note}"
            warnings.append(frost_note)
        stages.append(
            AhuStage("CC", "Cooling coil", off,
                     q_sensible=q_sensible, q_latent=q_latent, q_total=q_total,
                     moisture=-condensate, note=note)
        )

        if reheat_target > t_off + _T_TOL:
            r = sensible(off, m_da, reheat_target)
            stages.append(
                AhuStage("HC", "Heating coil (reheat)", r.state,
                         q_sensible=r.q_sensible, q_total=r.q_total)
            )
            pre_fan = r.state
        else:
            pre_fan = off
            if reheat_target < t_off - _T_TOL:
                warnings.append(
                    "Draw-through fan gain exceeds the reheat requirement: the air "
                    "leaves the coil colder than target and the fan alone lifts it — "
                    "the supply may overshoot. Reduce fan power or raise the off-coil."
                )
        final = _finish(pre_fan)

    # Sanity: the delivered supply should match the requested one.
    if abs(final.t_db - supply.t_db) > 0.1 or abs(final.w - supply.w) > 5e-5:
        warnings.append(
            f"Delivered supply ({final.t_db:.1f} degC, {final.w * 1000:.2f} g/kg) "
            f"differs from the requested ({supply.t_db:.1f} degC, "
            f"{supply.w * 1000:.2f} g/kg) — check the inputs."
        )

    return _ahu_totals(stages, m_da, frost, warnings)
