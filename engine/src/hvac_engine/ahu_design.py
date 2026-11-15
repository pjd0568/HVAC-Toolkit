"""Supply-driven AHU design — the inverse of ``processes.simulate_ahu``.

Implemented from SPEC-ahu-processes.md (``design_ahu_to_supply``). Instead of
specifying the off-coil condition and reading off the supply, the user gives the
**required supply (off-unit) condition** and the solver derives the intermediate
stages that reach it: mix OA/RA to the on-coil condition, then choose a path
from the moisture balance:

- supply drier than on-coil → cooling coil on the apparatus-dew-point /
  bypass-factor chord (ADP from chilled water or DX evaporating temperature),
  sized so off-coil moisture equals the supply moisture, then reheat to the
  supply dry bulb when needed;
- supply wetter than on-coil → heat then steam humidify (winter path);
- equal moisture → purely sensible cool or heat.

If the ADP is at or above the on-coil dew point the coil is dry (sensible only)
and cannot dehumidify — the caller must lower ADP.

Pure Python; depends only on ``hvac_engine.psychrometrics`` and the shared result
types / elementary processes in ``hvac_engine.processes``.
"""

from __future__ import annotations

from hvac_engine import psychrometrics as psy
from hvac_engine.psychrometrics import PsychroState
from hvac_engine.processes import (
    AhuResult,
    AhuStage,
    cooling_coil,
    heat_and_humidify,
    mix,
    sensible,
    steam_humidify,
)

_W_TOL = 1e-5  # kg/kg (~0.01 g/kg): smaller differences are "no net moisture change"
_T_TOL = 1e-3  # degC


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
    t_adp: float | None = None,
    fan_position: str = "none",
    fan_power_kw: float | None = None,
    fan_pickup_dt: float = 0.0,
) -> AhuResult:
    """Design the AHU stages needed to deliver a required supply condition.

    Mixes fresh air and return air to the on-coil condition A (``oa_fraction``
    in ``[0, 1]``; ``0`` is all return air), then derives stages from the moisture
    balance between on-coil and supply:

    - dehumidification (``W_sup < W_on``): apparatus dew point ``t_adp`` on the
      saturation curve and the bypass-factor chord through air-on; bypass factor
      is chosen so off-coil moisture equals ``W_sup``, then reheat to the supply
      dry bulb when needed. ``t_adp`` must be below the on-coil dew point;
    - humidification (``W_sup > W_on``): heating coil then isothermal steam to the
      supply moisture (winter path);
    - equal moisture: purely sensible cooling or heating.

    A blow-through fan raises the on-coil condition before the coils; a
    draw-through fan sits after the last coil/humidifier, so the heating coil
    targets ``t_sup − ΔT_fan``. Returns the same ``AhuResult`` shape as
    ``simulate_ahu``.
    """
    if m_da <= 0:
        raise ValueError("mass flow must be positive")
    if not (0.0 <= oa_fraction <= 1.0):
        raise ValueError("outdoor air fraction must be in [0, 1]")
    if oa_fraction < 1.0 and return_air is None:
        raise ValueError("return air state required when outdoor air fraction is below 1")
    if fan_position not in ("none", "blow", "draw"):
        raise ValueError("fan_position must be 'none', 'blow' or 'draw'")

    stages: list[AhuStage] = []
    warnings: list[str] = []
    frost = False

    # 1. Intake / mixing -> on-coil condition A.
    # oa_fraction == 0 is all return air (no outdoor stage).
    if oa_fraction <= 0.0:
        assert return_air is not None
        stages.append(AhuStage("RA", "Return air", return_air))
        air_on = return_air
    else:
        stages.append(AhuStage("OA", "Fresh air", outdoor))
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
                AhuStage("MA", "Mixed air", mx.state,
                         moisture=-mx.condensate, note=note)
            )
            air_on = mx.state

    p = air_on.p

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

    # A draw-through fan sits after the last process stage: target t_sup - dt_fan
    # so the air arrives at the supply temperature once the fan gain is added.
    dt_draw = _fan_dt(supply) if fan_position == "draw" else 0.0
    reheat_target = supply.t_db - dt_draw

    W_on = air_on.w
    W_sup = supply.w

    def _finish(pre_fan: PsychroState) -> PsychroState:
        """Apply the draw-through fan (if any) and append the SUP stage."""
        if fan_position == "draw" and dt_draw > 0.0:
            r = sensible(pre_fan, m_da, pre_fan.t_db + dt_draw)
            stages.append(
                AhuStage("SUP", "Off AHU (after draw-through fan)", r.state,
                         q_sensible=r.q_sensible, q_total=r.q_total,
                         note=f"Fan gain +{dt_draw:.2f} K")
            )
            return r.state
        stages.append(AhuStage("SUP", "Off AHU", pre_fan))
        return pre_fan

    if abs(W_sup - W_on) <= _W_TOL:
        # ── Purely sensible duty (no net moisture change) ───────────────────────
        if reheat_target < air_on.t_db - _T_TOL:
            # Prefer the dry ADP coil when ADP is at/above the dew point; otherwise
            # a plain sensible process (constant W) matches the required leaving T.
            if t_adp is not None and t_adp >= air_on.t_dp - 1e-9:
                c = cooling_coil(air_on, m_da, t_adp=t_adp, t_off=reheat_target)
                frost = frost or c.frost_risk
                note = (
                    f"Dry coil — ADP {t_adp:.1f} °C is at or above the on-coil "
                    f"dew point {air_on.t_dp:.1f} °C (sensible only)."
                )
                stages.append(
                    AhuStage("CC", "Cooling coil (sensible)", c.state,
                             q_sensible=c.q_sensible, q_total=c.q_total, note=note)
                )
                final = _finish(c.state)
            else:
                c = sensible(air_on, m_da, reheat_target)
                note = ""
                if reheat_target <= 0.0:
                    frost = True
                    note = (
                        f"Frost risk: off-coil temperature {reheat_target:.1f} degC is "
                        "at or below freezing."
                    )
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
    elif W_sup > W_on + _W_TOL:
        # ── Humidification (winter): heat then isothermal steam ─────────────────
        hum_note = "Humidification required (on-coil drier than supply)."
        if reheat_target < air_on.t_db - _T_TOL:
            # Unusual: on-coil warmer than supply but drier — cool then steam.
            c = sensible(air_on, m_da, reheat_target)
            stages.append(
                AhuStage("CC", "Cooling coil (sensible)", c.state,
                         q_sensible=c.q_sensible, q_total=c.q_total, note=hum_note)
            )
            hm = steam_humidify(c.state, m_da, W_sup)
            stages.append(
                AhuStage("HUM", "Steam humidifier", hm.state,
                         q_latent=hm.q_latent, q_total=hm.q_latent,
                         moisture=hm.steam_rate, note=hum_note)
            )
            final = _finish(hm.state)
        else:
            hh = heat_and_humidify(
                air_on, m_da, t_out=reheat_target, w_out=W_sup
            )
            if abs(hh.state_x.t_db - air_on.t_db) > _T_TOL:
                stages.append(
                    AhuStage("HC", "Heating coil", hh.state_x,
                             q_sensible=hh.q_sensible, q_total=hh.q_sensible,
                             note=hum_note)
                )
            if hh.steam_rate > 1e-12:
                stages.append(
                    AhuStage("HUM", "Steam humidifier", hh.state,
                             q_latent=hh.q_latent, q_total=hh.q_latent,
                             moisture=hh.steam_rate, note=hum_note)
                )
                pre_fan = hh.state
            else:
                pre_fan = hh.state_x
            final = _finish(pre_fan)
    else:
        # ── Dehumidification: ADP / bypass-factor chord to supply moisture ─────
        if t_adp is None:
            raise ValueError(
                "apparatus dew point is required to dehumidify — enter chilled-water "
                "flow or evaporating temperature (plus approach), or ADP directly"
            )
        if t_adp >= air_on.t_dp - 1e-9:
            raise ValueError(
                f"Apparatus dew point {t_adp:.1f} °C is at or above the on-coil "
                f"dew point {air_on.t_dp:.1f} °C — the coil is dry (sensible only) "
                "and cannot remove moisture. Lower the chilled-water or evaporating "
                "temperature (or the approach) so ADP sits below the dew point."
            )
        w_adp = psy.saturation_humidity_ratio(t_adp, p)
        if W_sup < w_adp - 1e-9:
            raise ValueError(
                f"Off-AHU moisture {W_sup * 1000:.2f} g/kg is below the ADP "
                f"saturation moisture {w_adp * 1000:.2f} g/kg at {t_adp:.1f} °C. "
                "Lower the apparatus dew point to dehumidify further."
            )
        denom = W_on - w_adp
        if abs(denom) < 1e-12:
            raise ValueError("on-coil moisture equals ADP saturation — no dehumidification margin")
        # W_off = W_ADP + BF·(W_on − W_ADP) → BF for the required supply moisture.
        bf = (W_sup - w_adp) / denom
        if not (0.0 <= bf < 1.0):
            raise ValueError(
                f"bypass factor {bf:.3f} is outside [0, 1) for this ADP and "
                "off-AHU moisture — check the apparatus dew point"
            )
        c = cooling_coil(air_on, m_da, t_adp=t_adp, bypass_factor=bf)
        frost = frost or c.frost_risk
        note = (
            f"Wet coil on ADP {t_adp:.1f} °C, bypass factor {c.bypass_factor:.2f} "
            f"(leaving RH {c.state.rh * 100:.0f}%). Process is the straight "
            "ON→ADP chord — off-coil sits above saturation because of bypass."
        )
        if c.frost_risk:
            frost_note = (
                f"Frost risk: apparatus dew point {t_adp:.1f} °C is at or below "
                "freezing — consider glycol, DX defrost or face-and-bypass."
            )
            note = f"{note} {frost_note}"
            warnings.append(frost_note)
        stages.append(
            AhuStage("CC", "Cooling coil", c.state,
                     q_sensible=c.q_sensible, q_latent=c.q_latent, q_total=c.q_total,
                     moisture=-c.condensate, note=note)
        )

        t_off = c.state.t_db
        if reheat_target > t_off + _T_TOL:
            r = sensible(c.state, m_da, reheat_target)
            stages.append(
                AhuStage("HC", "Heating coil (reheat)", r.state,
                         q_sensible=r.q_sensible, q_total=r.q_total)
            )
            pre_fan = r.state
        else:
            pre_fan = c.state
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


def supply_process_title(result: AhuResult) -> str:
    """Name the treatment path ``design_ahu_to_supply`` selected.

    Fan gain is a stage duty, not part of this name. The title follows the
    moisture balance: dehumidify (and reheat when the off-coil is colder than
    the supply), sensible cooling, heating, humidification, or a combination.
    """
    cool_latent = False
    cool_sensible = False
    heat = False
    humidify = False
    for stage in result.stages:
        if stage.label == "CC":
            if stage.q_latent < -1e-6:
                cool_latent = True
            elif stage.q_total < -1e-6:
                cool_sensible = True
        elif stage.label == "HC" and stage.q_total > 1e-6:
            heat = True
        elif stage.label == "HUM" and (stage.moisture > 1e-9 or stage.q_total > 1e-6):
            humidify = True
    if cool_latent and heat:
        return "Dehumidification and reheat"
    if cool_latent:
        return "Cooling and dehumidification"
    if cool_sensible and humidify:
        return "Sensible cooling and humidification"
    if cool_sensible:
        return "Sensible cooling only"
    if heat and humidify:
        return "Heating and humidification"
    if heat:
        return "Heating"
    if humidify:
        return "Humidification"
    return "No coil duty — mixed air already meets the off-AHU condition"
