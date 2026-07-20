"""Unit converter — rich multi-unit catalog, categorised by quantity.

Implemented from SPEC-unit-converter.md. Public NIST SP 811 / BIPM exact unit
definitions only; the category and unit selection was decided fresh for this product.

The user picks a category, enters one value in one unit, and ``convert_all`` returns
that value in *every* unit of the category, each with the relationship used printed
beside it (a constant factor for linear units, or the closed-form formula for the
affine temperature scale).

This is a superset sibling of ``hvac_engine.units`` (the SI/IP display layer, one unit
per system): both are canonical-SI and share the same exact factors, so they agree on
any shared quantity. Everything here is pure Python — no calculation runs through it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Data model ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Unit:
    id: str
    name: str
    symbol: str
    group: str            # "Metric" | "Imperial" | "Other" | "Common"
    factor: float         # base units per one of this unit (linear categories only)


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    base_symbol: str
    units: tuple[Unit, ...]
    kind: str = "linear"  # "linear" | "temperature"

    def unit(self, unit_id: str) -> Unit:
        for u in self.units:
            if u.id == unit_id:
                return u
        raise ValueError(f"unknown unit {unit_id!r} in category {self.id!r}")


@dataclass(frozen=True)
class UnitResult:
    unit_id: str
    name: str
    symbol: str
    group: str
    value: float
    display: str          # value formatted to ~6 significant figures
    notation: str         # relationship used, e.g. "1 in = 25.4 mm"
    is_input: bool        # True for the row the user typed into


@dataclass(frozen=True)
class ConversionResult:
    category_id: str
    category_name: str
    value: float
    from_unit: Unit
    results: list[UnitResult]
    base_symbol: str
    warning: str | None = None


# ── Formatting ──────────────────────────────────────────────────────────────────

def format_value(x: float) -> str:
    """~6 significant figures, switching to scientific for very large/small numbers."""
    if x == 0.0:
        return "0"
    return f"{x:.6g}"


def _factor_str(k: float) -> str:
    return f"{k:.6g}"


# ── Linear-unit builder ─────────────────────────────────────────────────────────

def _u(uid: str, name: str, symbol: str, group: str, factor: float) -> Unit:
    return Unit(uid, name, symbol, group, factor)


M, I, O, C = "Metric", "Imperial", "Other", "Common"


# ── Temperature (affine) ────────────────────────────────────────────────────────

_TEMP_TO_K = {
    "K": lambda v: v,
    "degC": lambda v: v + 273.15,
    "degF": lambda v: (v + 459.67) * 5.0 / 9.0,
    "degR": lambda v: v * 5.0 / 9.0,
}
_TEMP_FROM_K = {
    "K": lambda k: k,
    "degC": lambda k: k - 273.15,
    "degF": lambda k: k * 9.0 / 5.0 - 459.67,
    "degR": lambda k: k * 9.0 / 5.0,
}
# Closed-form formula for each ordered (from, to) pair — printed beside the result.
_TEMP_FORMULA = {
    ("degC", "degF"): "°F = °C × 9/5 + 32",
    ("degC", "K"): "K = °C + 273.15",
    ("degC", "degR"): "°R = (°C + 273.15) × 9/5",
    ("degF", "degC"): "°C = (°F − 32) × 5/9",
    ("degF", "K"): "K = (°F + 459.67) × 5/9",
    ("degF", "degR"): "°R = °F + 459.67",
    ("K", "degC"): "°C = K − 273.15",
    ("K", "degF"): "°F = K × 9/5 − 459.67",
    ("K", "degR"): "°R = K × 9/5",
    ("degR", "degC"): "°C = °R × 5/9 − 273.15",
    ("degR", "degF"): "°F = °R − 459.67",
    ("degR", "K"): "K = °R × 5/9",
}

_TEMPERATURE = Category(
    "temperature", "Temperature", "K",
    units=(
        _u("degC", "Celsius", "°C", M, 0.0),
        _u("K", "Kelvin", "K", M, 0.0),
        _u("degF", "Fahrenheit", "°F", I, 0.0),
        _u("degR", "Rankine", "°R", O, 0.0),
    ),
    kind="temperature",
)


# ── Catalog (linear categories) ─────────────────────────────────────────────────
# Factor = base units per one of this unit. Base unit given in each Category.

_CATEGORIES: list[Category] = [
    Category("length", "Length", "m", (
        _u("nm", "Nanometre", "nm", M, 1e-9),
        _u("um", "Micrometre", "µm", M, 1e-6),
        _u("mm", "Millimetre", "mm", M, 1e-3),
        _u("cm", "Centimetre", "cm", M, 1e-2),
        _u("m", "Metre", "m", M, 1.0),
        _u("km", "Kilometre", "km", M, 1e3),
        _u("mil", "Thou / mil", "mil", I, 2.54e-5),
        _u("in", "Inch", "in", I, 0.0254),
        _u("ft", "Foot", "ft", I, 0.3048),
        _u("yd", "Yard", "yd", I, 0.9144),
        _u("mile", "Mile", "mi", I, 1609.344),
        _u("nmi", "Nautical mile", "nmi", O, 1852.0),
    )),
    Category("area", "Area", "m²", (
        _u("mm2", "Square millimetre", "mm²", M, 1e-6),
        _u("cm2", "Square centimetre", "cm²", M, 1e-4),
        _u("m2", "Square metre", "m²", M, 1.0),
        _u("ha", "Hectare", "ha", M, 1e4),
        _u("km2", "Square kilometre", "km²", M, 1e6),
        _u("in2", "Square inch", "in²", I, 0.00064516),
        _u("ft2", "Square foot", "ft²", I, 0.09290304),
        _u("yd2", "Square yard", "yd²", I, 0.83612736),
        _u("acre", "Acre", "acre", I, 4046.8564224),
        _u("mile2", "Square mile", "mi²", I, 2589988.110336),
    )),
    Category("volume", "Volume", "m³", (
        _u("ml", "Millilitre", "ml", M, 1e-6),
        _u("l", "Litre", "l", M, 1e-3),
        _u("m3", "Cubic metre", "m³", M, 1.0),
        _u("in3", "Cubic inch", "in³", I, 1.6387064e-5),
        _u("ft3", "Cubic foot", "ft³", I, 0.028316846592),
        _u("usgal", "US gallon", "US gal", I, 0.003785411784),
        _u("usfloz", "US fluid ounce", "US fl oz", I, 2.95735295625e-5),
        _u("impgal", "Imperial gallon", "imp gal", I, 0.00454609),
        _u("imppint", "Imperial pint", "imp pt", I, 0.0005682612532),
    )),
    Category("mass", "Mass", "kg", (
        _u("mg", "Milligram", "mg", M, 1e-6),
        _u("g", "Gram", "g", M, 1e-3),
        _u("kg", "Kilogram", "kg", M, 1.0),
        _u("tonne", "Tonne", "t", M, 1000.0),
        _u("gr", "Grain", "gr", I, 6.479891e-5),
        _u("oz", "Ounce", "oz", I, 0.028349523125),
        _u("lb", "Pound", "lb", I, 0.45359237),
        _u("stone", "Stone", "st", I, 6.35029318),
        _u("uston", "US ton (short)", "ton (US)", I, 907.18474),
        _u("longton", "Long ton", "ton (long)", I, 1016.0469088),
    )),
    Category("force", "Force", "N", (
        _u("N", "Newton", "N", M, 1.0),
        _u("kN", "Kilonewton", "kN", M, 1000.0),
        _u("kgf", "Kilogram-force", "kgf", M, 9.80665),
        _u("lbf", "Pound-force", "lbf", I, 4.4482216152605),
        _u("kip", "Kip", "kip", I, 4448.2216152605),
    )),
    Category("pressure", "Pressure", "Pa", (
        _u("Pa", "Pascal", "Pa", M, 1.0),
        _u("kPa", "Kilopascal", "kPa", M, 1000.0),
        _u("MPa", "Megapascal", "MPa", M, 1e6),
        _u("bar", "Bar", "bar", M, 1e5),
        _u("mbar", "Millibar", "mbar", M, 100.0),
        _u("mmH2O", "Millimetre of water", "mmH₂O", M, 9.80665),
        _u("psi", "Pound per sq inch", "psi", I, 6894.757293168),
        _u("inH2O", "Inch of water", "inH₂O", I, 249.08891),
        _u("inHg", "Inch of mercury", "inHg", I, 3386.389),
        _u("atm", "Atmosphere", "atm", O, 101325.0),
        _u("torr", "Torr", "torr", O, 133.32236842105),
    )),
    _TEMPERATURE,
    Category("speed", "Speed / velocity", "m/s", (
        _u("mps", "Metre per second", "m/s", M, 1.0),
        _u("kmh", "Kilometre per hour", "km/h", M, 0.2777777777778),
        _u("fps", "Foot per second", "ft/s", I, 0.3048),
        _u("fpm", "Foot per minute", "ft/min", I, 0.00508),
        _u("mph", "Mile per hour", "mph", I, 0.44704),
        _u("knot", "Knot", "kn", O, 0.5144444444444),
    )),
    Category("vol_flow", "Volumetric flow", "m³/s", (
        _u("m3s", "Cubic metre / second", "m³/s", M, 1.0),
        _u("m3h", "Cubic metre / hour", "m³/h", M, 0.0002777777777778),
        _u("ls", "Litre / second", "l/s", M, 1e-3),
        _u("lmin", "Litre / minute", "l/min", M, 1.666666666667e-5),
        _u("cfm", "Cubic foot / minute", "CFM", I, 0.0004719474432),
        _u("cfh", "Cubic foot / hour", "CFH", I, 7.86579072e-6),
        _u("usgpm", "US gallon / minute", "US GPM", I, 6.30901964e-5),
    )),
    Category("mass_flow", "Mass flow", "kg/s", (
        _u("kgs", "Kilogram / second", "kg/s", M, 1.0),
        _u("kgh", "Kilogram / hour", "kg/h", M, 0.0002777777777778),
        _u("gs", "Gram / second", "g/s", M, 1e-3),
        _u("tonneh", "Tonne / hour", "t/h", M, 0.2777777777778),
        _u("lbs", "Pound / second", "lb/s", I, 0.45359237),
        _u("lbh", "Pound / hour", "lb/h", I, 0.000125997880556),
        _u("lbmin", "Pound / minute", "lb/min", I, 0.00755987283333),
    )),
    Category("power", "Power", "W", (
        _u("W", "Watt", "W", M, 1.0),
        _u("kW", "Kilowatt", "kW", M, 1000.0),
        _u("MW", "Megawatt", "MW", M, 1e6),
        _u("btuh", "Btu / hour", "Btu/h", I, 0.29307107017),
        _u("hp", "Horsepower (mech.)", "hp", I, 745.69987158227),
        _u("ftlbfs", "Foot-pound / second", "ft·lbf/s", I, 1.35581794833),
        _u("tonref", "Ton of refrigeration", "ton", O, 3516.8528420667),
    )),
    Category("energy", "Energy", "J", (
        _u("J", "Joule", "J", M, 1.0),
        _u("kJ", "Kilojoule", "kJ", M, 1000.0),
        _u("MJ", "Megajoule", "MJ", M, 1e6),
        _u("Wh", "Watt-hour", "Wh", M, 3600.0),
        _u("kWh", "Kilowatt-hour", "kWh", M, 3.6e6),
        _u("MWh", "Megawatt-hour", "MWh", M, 3.6e9),
        _u("Btu", "British thermal unit", "Btu", I, 1055.05585262),
        _u("ftlbf", "Foot-pound", "ft·lbf", I, 1.35581794833),
        _u("cal", "Calorie (IT)", "cal", O, 4.1868),
        _u("kcal", "Kilocalorie (IT)", "kcal", O, 4186.8),
        _u("therm", "Therm (US)", "therm", O, 1.05505585262e8),
    )),
    Category("time", "Time", "s", (
        _u("s", "Second", "s", C, 1.0),
        _u("min", "Minute", "min", C, 60.0),
        _u("h", "Hour", "h", C, 3600.0),
        _u("day", "Day", "day", C, 86400.0),
        _u("week", "Week", "week", C, 604800.0),
    )),
    Category("angle", "Angle", "rad", (
        _u("rad", "Radian", "rad", M, 1.0),
        _u("deg", "Degree", "°", C, 0.01745329251994),
        _u("grad", "Gradian", "grad", C, 0.01570796326795),
        _u("arcmin", "Arcminute", "′", C, 2.908882086657e-4),
    )),
    Category("density", "Density", "kg/m³", (
        _u("kgm3", "Kilogram / cubic metre", "kg/m³", M, 1.0),
        _u("gcm3", "Gram / cubic centimetre", "g/cm³", M, 1000.0),
        _u("lbft3", "Pound / cubic foot", "lb/ft³", I, 16.018463374),
        _u("lbin3", "Pound / cubic inch", "lb/in³", I, 27679.904710203),
    )),
    Category("humidity_ratio", "Humidity ratio", "kg/kg", (
        _u("kgkg", "Kilogram / kilogram dry air", "kg/kg", M, 1.0),
        _u("gkg", "Gram / kilogram dry air", "g/kg", M, 1e-3),
        _u("grlb", "Grain / pound dry air", "gr/lb", I, 1.0 / 7000.0),
    )),
    Category("enthalpy", "Enthalpy (specific)", "J/kg", (
        _u("Jkg", "Joule / kilogram", "J/kg", M, 1.0),
        _u("kJkg", "Kilojoule / kilogram", "kJ/kg", M, 1000.0),
        _u("Btulb", "Btu / pound", "Btu/lb", I, 2326.0),
    )),
]

CATEGORIES: dict[str, Category] = {c.id: c for c in _CATEGORIES}
GROUP_ORDER = (M, I, O, C)


def list_categories() -> list[tuple[str, str]]:
    """(id, name) for every category, in catalog order — for the tool's dropdown."""
    return [(c.id, c.name) for c in _CATEGORIES]


def get_category(category_id: str) -> Category:
    try:
        return CATEGORIES[category_id]
    except KeyError:
        raise ValueError(f"unknown category: {category_id!r}")


# ── Conversion ──────────────────────────────────────────────────────────────────

def _convert_linear(cat: Category, value: float, src: Unit, dst: Unit) -> float:
    return value * src.factor / dst.factor


def _notation_linear(src: Unit, dst: Unit) -> str:
    k = src.factor / dst.factor
    return f"1 {src.symbol} = {_factor_str(k)} {dst.symbol}"


def _convert_temperature(value: float, src_id: str, dst_id: str) -> float:
    return _TEMP_FROM_K[dst_id](_TEMP_TO_K[src_id](value))


def convert_all(category_id: str, value: float, from_unit_id: str) -> ConversionResult:
    """Convert ``value`` (in ``from_unit_id``) into every unit of the category.

    Returns a ConversionResult whose ``results`` list carries one UnitResult per unit,
    each with the converted value, a display string (~6 sig figs) and the relationship
    used (a factor, or the temperature formula). The entered unit is flagged is_input.
    """
    cat = get_category(category_id)
    src = cat.unit(from_unit_id)

    results: list[UnitResult] = []
    warning: str | None = None

    for dst in cat.units:
        if cat.kind == "temperature":
            out = _convert_temperature(value, src.id, dst.id)
            if dst.id == src.id:
                notation = "entered value"
            else:
                notation = _TEMP_FORMULA[(src.id, dst.id)]
        else:
            out = _convert_linear(cat, value, src, dst)
            notation = "entered value" if dst.id == src.id else _notation_linear(src, dst)

        results.append(UnitResult(
            unit_id=dst.id, name=dst.name, symbol=dst.symbol, group=dst.group,
            value=out, display=format_value(out), notation=notation,
            is_input=(dst.id == src.id),
        ))

    if cat.kind == "temperature":
        kelvin = _TEMP_TO_K[src.id](value)
        if kelvin < 0.0:
            warning = "That is below absolute zero (0 K) — physically unreachable."

    return ConversionResult(
        category_id=cat.id, category_name=cat.name, value=value, from_unit=src,
        results=results, base_symbol=cat.base_symbol, warning=warning,
    )


__all__ = [
    "Unit", "Category", "UnitResult", "ConversionResult",
    "CATEGORIES", "GROUP_ORDER", "list_categories", "get_category",
    "convert_all", "format_value",
]
