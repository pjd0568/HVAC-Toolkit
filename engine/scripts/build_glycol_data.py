"""One-off generator: Hydratech_Glycol_Data.xlsx -> hvac_engine/glycol_data.py"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]
XLSX = ROOT.parent / "Support" / "Hydratech Glycol Data Sheets" / "Hydratech_Glycol_Data.xlsx"
OUT = Path(__file__).resolve().parents[1] / "src" / "hvac_engine" / "glycol_data.py"

MAP = {"PPG": "ppg", "EG": "epg", "DTX": "dtx"}
NAMES = {
    "ppg": "Coolflow NTP (PPG)",
    "epg": "Coolflow IGE (EG)",
    "dtx": "Coolflow DTX (DTX)",
}


def main() -> None:
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb["All Data (Tidy)"]
    rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if r[0]]

    grids: dict[str, dict[int, list[tuple[float, float, float, float, float]]]] = {
        fid: {} for fid in NAMES
    }

    for code, _name, conc, fp, t, rho, nu_mm2, cp_kj, _k in rows:
        fid = MAP[str(code)]
        pct = int(conc)
        if t is None or rho is None or nu_mm2 is None or cp_kj is None:
            continue
        mu = nu_mm2 * 1e-6 * rho
        cp = cp_kj * 1000.0
        grids[fid].setdefault(pct, []).append((float(t), float(rho), float(mu), float(cp), float(fp)))

    concs = {fid: sorted(grids[fid]) for fid in NAMES}
    for fid in grids:
        for pct in grids[fid]:
            grids[fid][pct] = tuple(sorted(grids[fid][pct], key=lambda x: x[0]))

    lines = [
        '"""Hydratech Coolflow glycol property grids.',
        "",
        "Transcribed from Support/Hydratech Glycol Data Sheets/Hydratech_Glycol_Data.xlsx",
        "(All Data (Tidy) sheet). Kinematic viscosity converted to dynamic viscosity",
        "at the tabulated density. Specific heat converted kJ/kg·K -> J/kg·K.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Literal",
        "",
        'FluidId = Literal["dtx", "epg", "ppg"]',
        "",
        "FLUID_LABELS: dict[FluidId, str] = {",
    ]
    for fid, label in NAMES.items():
        lines.append(f'    "{fid}": "{label}",')
    lines.append("}")
    lines.append("")
    lines.append("GLYCOL_CONCENTRATIONS_PCT: dict[FluidId, tuple[int, ...]] = {")
    for fid in ("dtx", "epg", "ppg"):
        lines.append(f'    "{fid}": {concs[fid]},')
    lines.append("}")
    lines.append("")
    lines.append(
        "_GLYCOL_GRIDS: dict[FluidId, dict[int, tuple[tuple[float, float, float, float, float], ...]]] = {"
    )
    for fid in ("dtx", "epg", "ppg"):
        lines.append(f'    "{fid}": {{')
        for pct in concs[fid]:
            lines.append(f"        {pct}: (")
            for t, rho, mu, cp, fp in grids[fid][pct]:
                lines.append(f"            ({t:g}, {rho:g}, {mu:.6g}, {cp:g}, {fp:g}),")
            lines.append("        ),")
        lines.append("    },")
    lines.append("}")
    lines.append("")
    lines.append("")
    lines.append("def glycol_concentrations(fluid: FluidId) -> tuple[int, ...]:")
    lines.append("    return GLYCOL_CONCENTRATIONS_PCT[fluid]")
    lines.append("")
    lines.append("")
    lines.append("def glycol_grid(fluid: FluidId, concentration_pct: int):")
    lines.append("    try:")
    lines.append("        return _GLYCOL_GRIDS[fluid][concentration_pct]")
    lines.append("    except KeyError as exc:")
    lines.append('        raise ValueError(f"no data for {fluid!r} at {concentration_pct}%") from exc')
    lines.append("")
    lines.append("__all__ = [")
    lines.append('    "FLUID_LABELS",')
    lines.append('    "FluidId",')
    lines.append('    "GLYCOL_CONCENTRATIONS_PCT",')
    lines.append('    "glycol_concentrations",')
    lines.append('    "glycol_grid",')
    lines.append("]")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT} ({len(lines)} lines)")
    print("Concentrations:", concs)


if __name__ == "__main__":
    main()
