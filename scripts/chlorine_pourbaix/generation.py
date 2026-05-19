from __future__ import annotations

import json
from datetime import datetime, timezone

from .alpha import classified_alpha_region_grid, composition_model
from .chemistry import boundary_for_output, normalize_half_reaction_payload, nernst_factor_v
from .config import (
    DEFAULT_TEMPERATURE_C,
    HALF_REACTIONS_IN,
    LOG_C_VALUES,
    OUT,
    ROOT,
    SPECIES,
    STATIC_LOG_C,
    STATIC_TEMPERATURE_C,
    TEMPERATURE_C_VALUES,
)
from .geometry import (
    active_region_pairs,
    active_segments_for_edges,
    derived_dominance_boundaries,
    redox_edges,
    regions_from_classification,
)


def make_slice(
    log_c: float,
    boundary_defs: list[dict],
    nernst_factor: float,
    axes: dict,
) -> dict:
    edges = redox_edges(boundary_defs)
    regions = []
    derived_boundaries = []
    active_pairs: set[tuple[str, str]] = set()
    active_segments_by_id: dict[str, list[dict]] = {}

    if edges:
        classification, ph_edges, e_edges, species_ids = classified_alpha_region_grid(
            log_c, boundary_defs, nernst_factor, axes
        )
        active_pairs = active_region_pairs(classification, species_ids)
        active_segments_by_id = active_segments_for_edges(
            edges,
            log_c,
            nernst_factor,
            classification,
            ph_edges,
            e_edges,
            species_ids,
        )
        regions = regions_from_classification(
            classification, ph_edges, e_edges, species_ids, log_c
        )
        derived_boundaries = derived_dominance_boundaries(
            classification, ph_edges, e_edges, species_ids
        )

    boundaries = [
        boundary_for_output(
            defn,
            log_c,
            nernst_factor,
            active_pairs,
            active_segments_by_id,
        )
        for defn in boundary_defs
    ]

    return {
        "logC": log_c,
        "boundaries": boundaries,
        "derivedBoundaries": derived_boundaries,
        "regions": regions,
        "activeRegionPairs": [
            {"species": list(pair)}
            for pair in sorted(active_pairs)
        ],
    }

def slice_for_log_c(slices: list[dict], log_c: float) -> dict:
    for slice_def in slices:
        if abs(float(slice_def["logC"]) - log_c) < 1e-9:
            return slice_def

    raise ValueError(f"No Pourbaix slice found for logC={log_c}")

def axes_config(temperature_values: list[float]) -> dict:
    temperature_axis = {
        "min": min(temperature_values),
        "max": max(temperature_values),
        "unit": "C",
        "values": temperature_values,
    }
    if len(temperature_values) > 1:
        temperature_axis["step"] = temperature_values[1] - temperature_values[0]

    return {
        "pH": {"min": 0, "max": 14, "unit": "pH"},
        "E": {"min": -0.9, "max": 2.0, "unit": "V vs SHE"},
        "logC": {
            "min": min(LOG_C_VALUES),
            "max": max(LOG_C_VALUES),
            "unit": "log10 molal total chlorine",
            "values": LOG_C_VALUES,
        },
        "temperatureC": temperature_axis,
    }

def temperature_slice_payload(
    raw_half_reaction_payload: dict,
    temperature_c: float,
    axes: dict,
    explicit_cl2_gas: bool = False,
) -> dict:
    normalized_payload = normalize_half_reaction_payload(
        raw_half_reaction_payload,
        temperature_c,
        explicit_cl2_gas=explicit_cl2_gas,
    )
    nernst_factor = nernst_factor_v(temperature_c)
    boundary_defs = normalized_payload["boundaries"]
    slices = [
        make_slice(log_c, boundary_defs, nernst_factor, axes)
        for log_c in LOG_C_VALUES
    ]

    return {
        "temperatureC": temperature_c,
        "nernstFactorV": round(nernst_factor, 8),
        "compositionModel": composition_model(boundary_defs, nernst_factor),
        "slices": slices,
    }

def temperature_payload_for_value(
    temperature_slices: list[dict],
    temperature_c: float,
) -> dict:
    for temperature_payload in temperature_slices:
        if abs(float(temperature_payload["temperatureC"]) - temperature_c) < 1e-9:
            return temperature_payload

    raise ValueError(f"No Pourbaix temperature slice found for T={temperature_c:g} C")

def generate_interactive_payload(
    raw_half_reaction_payload: dict,
    temperature_values: list[float] | None = None,
    explicit_cl2_gas: bool = False,
) -> dict:
    temperature_values = temperature_values or TEMPERATURE_C_VALUES
    axes = axes_config(temperature_values)
    metadata = raw_half_reaction_payload.get("metadata", {})
    temperature_slices = [
        temperature_slice_payload(
            raw_half_reaction_payload,
            temperature_c,
            axes,
            explicit_cl2_gas=explicit_cl2_gas,
        )
        for temperature_c in temperature_values
    ]
    default_temperature_payload = temperature_payload_for_value(
        temperature_slices,
        DEFAULT_TEMPERATURE_C,
    )
    default_slice = slice_for_log_c(
        default_temperature_payload["slices"],
        STATIC_LOG_C,
    )

    return {
        "metadata": {
            "title": "Teaching-scale chlorine Pourbaix diagram",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "temperatureC": DEFAULT_TEMPERATURE_C,
            "defaultTemperatureC": DEFAULT_TEMPERATURE_C,
            "staticTemperatureC": STATIC_TEMPERATURE_C,
            "staticLogC": STATIC_LOG_C,
            "nernstFactorV": default_temperature_payload["nernstFactorV"],
            "source": "scripts/chlorine.py",
            "halfReactionSource": str(HALF_REACTIONS_IN.relative_to(ROOT)),
            "temperatureGridC": temperature_values,
            "logCGrid": LOG_C_VALUES,
            "modelOptions": {
                "explicitCl2Gas": explicit_cl2_gas,
                "cl2GasLiquidEquilibrium": (
                    "Cl2(g) half-reactions are analytically converted to "
                    "Cl2(aq) through the independent Henry-law equilibrium "
                    "log10(aCl2(aq)/fCl2)=log10(KH). Dominance regions remain "
                    "on the aqueous total-chlorine basis."
                )
                if explicit_cl2_gas
                else None,
            },
            "warning": metadata.get(
                "warning",
                "Schematic teaching data. Replace constants with a vetted "
                "thermodynamic database before quantitative interpretation.",
            ),
        },
        "axes": axes,
        "species": [dict(species) for species in SPECIES],
        "compositionModel": default_temperature_payload["compositionModel"],
        "regions": default_slice["regions"],
        "slices": default_temperature_payload["slices"],
        "temperatureSlices": temperature_slices,
    }

def write_interactive_json(payload: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}")
