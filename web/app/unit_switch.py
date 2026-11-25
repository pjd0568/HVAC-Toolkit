"""Rewrite calculator query strings when the SI/IP toggle flips.

GET-driven tools keep inputs in the URL. The unit toggle used to change only
the session preference and redirect to the same query string, so a load of
``50`` stayed ``50`` while the label moved from kW to Btu/h. Convert known
display fields from the previous system into the new one so the physical
values stay put.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from hvac_engine import units as eng_units

# Exact query keys → engine quantity (or the special temperature_difference).
_FIXED_FIELDS: dict[str, str] = {
    "load": "power",
    "lwt": "temperature",
    "delta_t": "temperature_difference",
    "lift": "duct_run_length",
    "altitude": "altitude",
    "s_t": "temperature",
    "a_t": "temperature",
    "b_t": "temperature",
    "adp_t": "temperature",
    "off_t": "temperature",
    "ra_t": "temperature",
    "sup_t": "temperature",
    "flow": "vol_flow",
    "flow_a": "vol_flow",
    "flow_b": "vol_flow",
    "oa_flow": "vol_flow",
    "q_sensible": "power",
    "steam_rate": "moisture_rate",
    "moisture_duty": "moisture_rate",
    "max_velocity": "velocity",
    "max_friction_rate": "friction_rate",
    "rect_width": "duct_dimension",
    "rect_height": "duct_dimension",
    "oval_major": "duct_dimension",
    "oval_minor": "duct_dimension",
    "stage_length": "duct_run_length",
    "stage_dp": "velocity_pressure",
}

# Indexed / prefixed row fields: key startswith prefix → quantity.
_PREFIX_FIELDS: tuple[tuple[str, str], ...] = (
    ("sys_length_", "duct_run_length"),
    ("sys_dp_", "velocity_pressure"),
    ("leg_length_", "duct_run_length"),
    ("leg_dp_", "velocity_pressure"),
    ("leg_diameter_", "duct_dimension"),
    ("leg_width_", "duct_dimension"),
    ("leg_height_", "duct_dimension"),
    ("leg_major_", "duct_dimension"),
    ("leg_minor_", "duct_dimension"),
)

# Second-property value fields: depend on the matching *_prop selector.
_PROP_VALUE_FIELDS: dict[str, str] = {
    "s_val": "s_prop",
    "a_val": "a_prop",
    "b_val": "b_prop",
    "target_val": "target_prop",
}

_PROP_QUANTITIES: dict[str, str] = {
    "twb": "temperature",
    "tdp": "temperature",
    "w": "humidity_ratio",
    # rh is a percentage — leave unchanged.
}


def _quantity_for(key: str, params: dict[str, str]) -> str | None:
    if key in _FIXED_FIELDS:
        return _FIXED_FIELDS[key]
    if key == "volume":
        return "duct_volume"
    if key == "target_value":
        basis = params.get("basis", "velocity")
        return "velocity" if basis == "velocity" else "friction_rate"
    if key == "leg_volume" or key.startswith("leg_volume_"):
        return "duct_volume"
    prop_key = _PROP_VALUE_FIELDS.get(key)
    if prop_key:
        return _PROP_QUANTITIES.get((params.get(prop_key) or "").lower())
    for prefix, quantity in _PREFIX_FIELDS:
        if key.startswith(prefix):
            return quantity
    return None


def _format(quantity: str, si_value: float, system: str) -> str:
    dp = eng_units.decimals(quantity, system)
    value = eng_units.from_si(quantity, si_value, system)
    if dp == 0:
        # Keep whole numbers clean for power (Btu/h) and similar.
        return str(int(round(value)))
    text = f"{value:.{dp}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _convert_delta_t(raw: float, from_system: str, to_system: str) -> str:
    """ΔT is a difference — scale by 9/5, do not apply the °F offset."""
    if from_system == to_system:
        return f"{raw:g}"
    if from_system == "SI" and to_system == "IP":
        value = raw * 9.0 / 5.0
    elif from_system == "IP" and to_system == "SI":
        value = raw * 5.0 / 9.0
    else:
        return f"{raw:g}"
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def _convert_duct_volume(raw: float, from_system: str, to_system: str, flow_unit: str) -> str:
    from app.blueprints.duct import duct_volume_to_m3h, fmt_duct_volume
    from app.units import UnitView

    from_view = UnitView(from_system)
    to_view = UnitView(to_system)
    unit_from = flow_unit if from_system == "SI" else "m3s"
    unit_to = flow_unit if to_system == "SI" else "m3s"
    m3h = duct_volume_to_m3h(raw, unit_from, from_view)
    return fmt_duct_volume(m3h, unit_to, to_view)


def convert_value(
    quantity: str,
    raw: str,
    *,
    from_system: str,
    to_system: str,
    duct_flow_unit: str = "m3s",
) -> str | None:
    """Convert one display value. Returns None when the raw text is not numeric."""
    if from_system == to_system:
        return raw
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    if quantity == "temperature_difference":
        return _convert_delta_t(number, from_system, to_system)
    if quantity == "duct_volume":
        return _convert_duct_volume(number, from_system, to_system, duct_flow_unit)
    try:
        si = eng_units.to_si(quantity, number, from_system)
        return _format(quantity, si, to_system)
    except ValueError:
        return None


def convert_query_params(
    params: list[tuple[str, str]],
    *,
    from_system: str,
    to_system: str,
) -> list[tuple[str, str]]:
    """Convert unit-bearing query pairs; leave everything else unchanged."""
    if from_system == to_system or from_system not in eng_units.SYSTEMS or to_system not in eng_units.SYSTEMS:
        return list(params)
    as_dict = {k: v for k, v in params}
    flow_unit = as_dict.get("duct_flow_unit") or "m3s"
    out: list[tuple[str, str]] = []
    for key, value in params:
        quantity = _quantity_for(key, as_dict)
        if not quantity or value in ("", None):
            out.append((key, value))
            continue
        converted = convert_value(
            quantity,
            value,
            from_system=from_system,
            to_system=to_system,
            duct_flow_unit=flow_unit,
        )
        out.append((key, converted if converted is not None else value))
    return out


def rewrite_next_url(next_url: str, *, from_system: str, to_system: str) -> str:
    """Rewrite the relative ``next`` redirect target for a unit-system change."""
    if not next_url or from_system == to_system:
        return next_url
    parts = urlsplit(next_url)
    if parts.scheme or parts.netloc:
        # Absolute / off-site targets are rejected by the caller; leave alone.
        return next_url
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    if not pairs:
        return next_url
    converted = convert_query_params(pairs, from_system=from_system, to_system=to_system)
    return urlunsplit(("", "", parts.path, urlencode(converted), parts.fragment))
