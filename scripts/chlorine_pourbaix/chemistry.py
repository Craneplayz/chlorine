from __future__ import annotations

import json
from copy import deepcopy

import numpy as np

from .config import (
    BALANCE_TOLERANCE,
    DEFAULT_TEMPERATURE_C,
    DISPLAY_ARROW,
    FARADAY_CONSTANT,
    GAS_CONSTANT,
    HALF_REACTIONS_IN,
    HPLUS_LOG_ACTIVITY,
    KELVIN_OFFSET,
    LOG10_E,
    CL2_GAS_HENRY_KH,
    CL2_GAS_HENRY_LOG10_KH,
    NORMALIZATION_CHECK_LOG_C_VALUES,
    NORMALIZATION_CHECK_PH_VALUES,
    OH_LOG_ACTIVITY,
    PH_VALUES,
    REGION_SPECIES_ALIASES,
    SPECIES,
    TERM_SPECIES_ALIASES,
    WATER_LOG_ACTIVITY,
)
from .display import normalize_reaction_arrow


def nernst_factor_v(temperature_c: float) -> float:
    temperature_k = temperature_c + KELVIN_OFFSET
    return GAS_CONSTANT * temperature_k * LOG10_E / FARADAY_CONSTANT

def numeric_model_value(model: dict, key: str) -> float:
    return float(model.get(key, 0.0))

def log_activity_model_matches(actual: dict, expected: dict) -> bool:
    keys = set(actual) | set(expected)
    return all(
        abs(numeric_model_value(actual, key) - numeric_model_value(expected, key))
        < BALANCE_TOLERANCE
        for key in keys
    )

def assert_log_activity_model(term: dict, expected: dict, boundary_id: str) -> None:
    actual = term.get("logActivity", {})
    if not log_activity_model_matches(actual, expected):
        raise ValueError(
            f"Boundary {boundary_id} uses unsupported {term['label']} activity model: "
            f"{actual!r}; expected {expected!r}"
        )

def add_term(
    terms_by_label: dict[str, dict],
    label: str,
    coefficient: float,
    log_activity_model: dict,
    boundary_id: str,
) -> None:
    if abs(coefficient) < BALANCE_TOLERANCE:
        return

    if label in terms_by_label:
        existing = terms_by_label[label]
        if not log_activity_model_matches(
            existing.get("logActivity", {}), log_activity_model
        ):
            raise ValueError(
                f"Boundary {boundary_id} has incompatible activity models for {label}"
            )
        existing["coefficient"] = float(existing["coefficient"]) + coefficient
    else:
        terms_by_label[label] = {
            "label": label,
            "coefficient": coefficient,
            "logActivity": deepcopy(log_activity_model),
        }

def compact_terms(terms_by_label: dict[str, dict]) -> list[dict]:
    terms = []
    for term in terms_by_label.values():
        coefficient = float(term["coefficient"])
        if abs(coefficient) < BALANCE_TOLERANCE:
            continue
        output_term = {
            "label": term["label"],
            "coefficient": int(coefficient)
            if abs(coefficient - round(coefficient)) < BALANCE_TOLERANCE
            else coefficient,
            "logActivity": term.get("logActivity", {}),
        }
        terms.append(output_term)
    return terms

def coefficient_for_label(terms: list[dict], label: str) -> float:
    return sum(
        float(term["coefficient"]) for term in terms if term["label"] == label
    )

def cancel_common_term(
    reactants: dict[str, dict],
    products: dict[str, dict],
    label: str,
) -> None:
    if label not in reactants or label not in products:
        return

    common = min(
        float(reactants[label]["coefficient"]),
        float(products[label]["coefficient"]),
    )
    reactants[label]["coefficient"] = float(reactants[label]["coefficient"]) - common
    products[label]["coefficient"] = float(products[label]["coefficient"]) - common
    if abs(float(reactants[label]["coefficient"])) < BALANCE_TOLERANCE:
        del reactants[label]
    if abs(float(products[label]["coefficient"])) < BALANCE_TOLERANCE:
        del products[label]

def pkw_from_oh_terms(defn: dict) -> float | None:
    pkw_values = []
    for side_name in ("reactants", "products"):
        for term in defn[side_name]:
            if term["label"] != "OH-":
                continue
            assert_log_activity_model(term, OH_LOG_ACTIVITY, defn["id"])
            pkw_values.append(-float(term.get("logActivity", {}).get("constant", 0.0)))

    if not pkw_values:
        return None
    if any(abs(pkw_value - pkw_values[0]) > BALANCE_TOLERANCE for pkw_value in pkw_values):
        raise ValueError(f"Boundary {defn['id']} has inconsistent OH- activity models")
    return pkw_values[0]

def normalize_oh_terms_to_hplus(defn: dict, nernst_factor: float) -> dict:
    pkw = pkw_from_oh_terms(defn)
    if pkw is None:
        normalized = deepcopy(defn)
        validate_half_reaction_balance(normalized)
        return normalized

    source_defn = deepcopy(defn)
    reactants_by_label: dict[str, dict] = {}
    products_by_label: dict[str, dict] = {}

    for term in defn["reactants"]:
        coefficient = float(term["coefficient"])
        if term["label"] == "OH-":
            add_term(
                reactants_by_label,
                "H2O",
                coefficient,
                WATER_LOG_ACTIVITY,
                defn["id"],
            )
            add_term(
                products_by_label,
                "H+",
                coefficient,
                HPLUS_LOG_ACTIVITY,
                defn["id"],
            )
        else:
            add_term(
                reactants_by_label,
                term["label"],
                coefficient,
                term.get("logActivity", {}),
                defn["id"],
            )

    for term in defn["products"]:
        coefficient = float(term["coefficient"])
        if term["label"] == "OH-":
            add_term(
                reactants_by_label,
                "H+",
                coefficient,
                HPLUS_LOG_ACTIVITY,
                defn["id"],
            )
            add_term(
                products_by_label,
                "H2O",
                coefficient,
                WATER_LOG_ACTIVITY,
                defn["id"],
            )
        else:
            add_term(
                products_by_label,
                term["label"],
                coefficient,
                term.get("logActivity", {}),
                defn["id"],
            )

    for label in ("H+", "H2O"):
        cancel_common_term(reactants_by_label, products_by_label, label)

    normalized = deepcopy(defn)
    delta_oh = coefficient_for_label(defn["products"], "OH-") - coefficient_for_label(
        defn["reactants"], "OH-"
    )
    electron_count = float(defn["electronCount"])
    standard_potential_shift = nernst_factor / electron_count * pkw * delta_oh
    normalized["sourceEquation"] = defn["equation"]
    normalized["sourceStandardPotentialV"] = defn["standardPotentialV"]
    normalized["reactants"] = compact_terms(reactants_by_label)
    normalized["products"] = compact_terms(products_by_label)
    normalized["standardPotentialV"] = (
        float(defn["standardPotentialV"]) + standard_potential_shift
    )
    normalized["equation"] = format_half_reaction_equation(normalized)
    normalized["normalization"] = {
        "method": "oh_to_hplus_using_kw",
        "pKw": pkw,
        "deltaOH": int(delta_oh)
        if abs(delta_oh - round(delta_oh)) < BALANCE_TOLERANCE
        else delta_oh,
        "standardPotentialShiftV": standard_potential_shift,
    }

    validate_half_reaction_balance(normalized)
    assert_no_oh_terms(normalized)
    assert_equivalent_boundary_potentials(source_defn, normalized, nernst_factor)
    return normalized

def species_formula_and_charge(label: str) -> tuple[str, int]:
    formula = label.split("(", 1)[0]
    charge = 0
    if formula.endswith("+"):
        formula = formula[:-1]
        charge = 1
    elif formula.endswith("-"):
        formula = formula[:-1]
        charge = -1
    return formula, charge

def formula_atoms(formula: str) -> dict[str, int]:
    atoms: dict[str, int] = {}
    index = 0
    while index < len(formula):
        if not formula[index].isupper():
            raise ValueError(f"Cannot parse formula {formula!r}")

        symbol = formula[index]
        index += 1
        if index < len(formula) and formula[index].islower():
            symbol += formula[index]
            index += 1

        count_digits = []
        while index < len(formula) and formula[index].isdigit():
            count_digits.append(formula[index])
            index += 1
        count = int("".join(count_digits)) if count_digits else 1
        atoms[symbol] = atoms.get(symbol, 0) + count

    return atoms

def chlorine_atom_count_for_label(label: str) -> int:
    formula, _charge = species_formula_and_charge(label)
    return formula_atoms(formula).get("Cl", 0)

def species_chlorine_counts(species_ids: list[str]) -> np.ndarray:
    species_by_id = {species["id"]: species for species in SPECIES}
    counts = []
    for species_id in species_ids:
        count = chlorine_atom_count_for_label(species_by_id[species_id]["label"])
        if count <= 0:
            raise ValueError(f"Species {species_id} does not contain chlorine")
        counts.append(float(count))
    return np.array(counts)

def term_species_id(label: str) -> str | None:
    species_id = TERM_SPECIES_ALIASES.get(label)
    if species_id is None:
        return None
    return canonical_region_species(species_id)

def side_atoms(terms: list[dict]) -> dict[str, float]:
    atoms: dict[str, float] = {}
    for term in terms:
        formula, _charge = species_formula_and_charge(term["label"])
        coefficient = float(term["coefficient"])
        for element, count in formula_atoms(formula).items():
            atoms[element] = atoms.get(element, 0.0) + coefficient * count
    return atoms

def side_charge(terms: list[dict]) -> float:
    charge = 0.0
    for term in terms:
        _formula, species_charge = species_formula_and_charge(term["label"])
        charge += float(term["coefficient"]) * species_charge
    return charge

def validate_half_reaction_balance(defn: dict) -> None:
    reactant_atoms = side_atoms(defn["reactants"])
    product_atoms = side_atoms(defn["products"])
    all_elements = set(reactant_atoms) | set(product_atoms)
    for element in all_elements:
        if (
            abs(reactant_atoms.get(element, 0.0) - product_atoms.get(element, 0.0))
            > BALANCE_TOLERANCE
        ):
            raise ValueError(
                f"Boundary {defn['id']} is not atom-balanced for {element}: "
                f"{reactant_atoms.get(element, 0.0)} != {product_atoms.get(element, 0.0)}"
            )

    reactant_charge = side_charge(defn["reactants"]) - float(defn["electronCount"])
    product_charge = side_charge(defn["products"])
    if abs(reactant_charge - product_charge) > BALANCE_TOLERANCE:
        raise ValueError(
            f"Boundary {defn['id']} is not charge-balanced: "
            f"{reactant_charge} != {product_charge}"
        )

def assert_no_oh_terms(defn: dict) -> None:
    for side_name in ("reactants", "products"):
        if any(term["label"] == "OH-" for term in defn[side_name]):
            raise ValueError(f"Boundary {defn['id']} still contains OH- after normalization")

def format_coefficient(coefficient: float) -> str:
    if abs(coefficient - 1) < BALANCE_TOLERANCE:
        return ""
    if abs(coefficient - round(coefficient)) < BALANCE_TOLERANCE:
        return str(int(round(coefficient)))
    return f"{coefficient:g}"

def format_term(term: dict) -> str:
    return f"{format_coefficient(float(term['coefficient']))}{term['label']}"

def format_electron_term(electron_count: float) -> str:
    return f"{format_coefficient(electron_count)}e-"

def format_half_reaction_equation(defn: dict) -> str:
    electron_count = float(defn["electronCount"])
    reactants = [format_term(term) for term in defn["reactants"]]
    reactants.append(format_electron_term(electron_count))
    products = [format_term(term) for term in defn["products"]]
    return f"{' + '.join(reactants)} {DISPLAY_ARROW} {' + '.join(products)}"

def assert_equivalent_boundary_potentials(
    source_defn: dict,
    normalized_defn: dict,
    nernst_factor: float,
) -> None:
    for ph in NORMALIZATION_CHECK_PH_VALUES:
        for log_c in NORMALIZATION_CHECK_LOG_C_VALUES:
            source_potential = boundary_potential(
                source_defn, ph, log_c, nernst_factor
            )
            normalized_potential = boundary_potential(
                normalized_defn, ph, log_c, nernst_factor
            )
            if abs(source_potential - normalized_potential) > 1e-9:
                raise ValueError(
                    f"Boundary {normalized_defn['id']} normalization changed E at "
                    f"pH={ph:g}, logC={log_c:g}: "
                    f"{source_potential} != {normalized_potential}"
                )

def normalize_half_reaction_payload(
    payload: dict,
    temperature_c: float = DEFAULT_TEMPERATURE_C,
    explicit_cl2_gas: bool = False,
) -> dict:
    normalized_payload = deepcopy(payload)
    metadata = normalized_payload.setdefault("metadata", {})
    metadata["temperatureC"] = temperature_c
    nernst_factor = nernst_factor_v(temperature_c)
    boundaries = [
        normalize_oh_terms_to_hplus(boundary, nernst_factor)
        for boundary in normalized_payload["boundaries"]
    ]
    if explicit_cl2_gas:
        boundaries = [
            apply_cl2_gas_liquid_equilibrium(boundary, metadata, nernst_factor)
            for boundary in boundaries
        ]
        boundaries.append(
            cl2_gas_liquid_equilibrium_reference(metadata)
        )
    normalized_payload["boundaries"] = boundaries
    return normalized_payload

def apply_cl2_gas_liquid_equilibrium(
    defn: dict,
    metadata: dict,
    nernst_factor: float,
) -> dict:
    gas_reactant_count = coefficient_for_label(defn["reactants"], "Cl2(g)")
    gas_product_count = coefficient_for_label(defn["products"], "Cl2(g)")
    if abs(gas_reactant_count) < BALANCE_TOLERANCE and abs(gas_product_count) < BALANCE_TOLERANCE:
        return defn

    henry = metadata.get("henryLaw", {}).get("cl2GasProxy", {})
    log10_kh = float(henry.get("log10KH", CL2_GAS_HENRY_LOG10_KH))
    log_q_offset = (gas_reactant_count - gas_product_count) * log10_kh
    transformed = deepcopy(defn)
    transformed["sourceEquation"] = defn["equation"]
    transformed["sourceStandardPotentialV"] = defn["standardPotentialV"]
    transformed["standardPotentialV"] = float(defn["standardPotentialV"]) - (
        nernst_factor / float(defn["electronCount"])
    ) * log_q_offset
    transformed["gasLiquidEquilibrium"] = {
        "model": "Cl2(g) <=> Cl2(aq)",
        "log10KH": log10_kh,
        "logQOffset": log_q_offset,
        "standardPotentialShiftV": transformed["standardPotentialV"]
        - float(defn["standardPotentialV"]),
    }

    for species_key in ("species", "regionSpecies"):
        if species_key in transformed:
            transformed[species_key] = [
                "cl2" if species_id == "cl2_g" else species_id
                for species_id in transformed[species_key]
            ]

    for side_name in ("reactants", "products"):
        for term in transformed[side_name]:
            if term["label"] == "Cl2(g)":
                term["label"] = "Cl2(aq)"
                term["logActivity"] = {}

    transformed["equation"] = format_half_reaction_equation(transformed)
    note = transformed.get("note", "")
    henry_note = (
        "Cl2(g) terms are converted to Cl2(aq) using the explicit Henry-law "
        f"equilibrium log10(aCl2(aq)/fCl2) = {log10_kh:g}."
    )
    transformed["note"] = f"{note} {henry_note}".strip()
    validate_half_reaction_balance(transformed)
    return transformed

def cl2_gas_liquid_equilibrium_reference(metadata: dict) -> dict:
    henry = metadata.get("henryLaw", {}).get("cl2GasProxy", {})
    kh = float(henry.get("KH", CL2_GAS_HENRY_KH))
    log10_kh = float(henry.get("log10KH", CL2_GAS_HENRY_LOG10_KH))

    return {
        "id": "cl2_g_cl2_aq_henry_equilibrium",
        "kind": "gasLiquidEquilibrium",
        "label": "Cl2(g) / Cl2(aq)",
        "species": ["cl2_g", "cl2"],
        "plotBoundary": False,
        "color": "#9b6acb",
        "equation": "Cl2(g) ⇌ Cl2(aq)",
        "note": (
            "Independent Henry-law gas-liquid equilibrium: "
            f"log10(aCl2(aq)/fCl2) = log10(KH) = {log10_kh:g}; "
            f"KH = {kh:g} molal/bar."
        ),
        "equilibriumLogK": log10_kh,
        "reactants": [
            {"label": "Cl2(g)", "coefficient": 1, "logActivity": {}},
        ],
        "products": [
            {"label": "Cl2(aq)", "coefficient": 1, "logActivity": {}},
        ],
    }

def validate_half_reaction_payload(payload: dict) -> None:
    if "boundaries" not in payload or not isinstance(payload["boundaries"], list):
        raise ValueError(f"{HALF_REACTIONS_IN} must define a 'boundaries' list")

    for boundary in payload["boundaries"]:
        for key in ("id", "standardPotentialV", "electronCount", "reactants", "products"):
            if key not in boundary:
                raise ValueError(f"Boundary {boundary.get('id', '<unknown>')} is missing {key!r}")
        if boundary["electronCount"] <= 0:
            raise ValueError(f"Boundary {boundary['id']} must use a positive electronCount")

def load_half_reaction_payload() -> dict:
    with HALF_REACTIONS_IN.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    validate_half_reaction_payload(payload)
    return payload

def log_activity(term: dict, ph: float, log_c: float) -> float:
    model = term.get("logActivity", {})
    return (
        float(model.get("constant", 0.0))
        + float(model.get("pH", 0.0)) * ph
        + float(model.get("logC", 0.0)) * log_c
    )

def side_log_activity(terms: list[dict], ph: float, log_c: float) -> float:
    return sum(float(term["coefficient"]) * log_activity(term, ph, log_c) for term in terms)

def reaction_log_q(defn: dict, ph: float, log_c: float) -> float:
    product_log_activity = side_log_activity(defn["products"], ph, log_c)
    reactant_log_activity = side_log_activity(defn["reactants"], ph, log_c)
    return product_log_activity - reactant_log_activity

def boundary_potential(defn: dict, ph: float, log_c: float, nernst_factor: float) -> float:
    return float(defn["standardPotentialV"]) - (
        nernst_factor / float(defn["electronCount"])
    ) * reaction_log_q(defn, ph, log_c)

def boundary_points(defn: dict, log_c: float, nernst_factor: float) -> list[dict[str, float]]:
    points = []
    for ph in PH_VALUES:
        e = boundary_potential(defn, ph, log_c, nernst_factor)
        points.append({"pH": ph, "E": round(e, 4)})
    return points

def canonical_region_species(species_id: str) -> str:
    return REGION_SPECIES_ALIASES.get(species_id, species_id)

def boundary_region_species(defn: dict) -> list[str]:
    return [
        canonical_region_species(species_id)
        for species_id in defn.get("regionSpecies", defn.get("species", []))
    ]

def boundary_for_output(
    defn: dict,
    log_c: float,
    nernst_factor: float,
    active_pairs: set[tuple[str, str]] | None = None,
    active_segments_by_id: dict[str, list[dict]] | None = None,
) -> dict:
    boundary = {
        key: value
        for key, value in defn.items()
        if key not in {"reactants", "products"}
    }
    for equation_key in ("equation", "sourceEquation"):
        if equation_key in boundary:
            boundary[equation_key] = normalize_reaction_arrow(boundary[equation_key])
    if defn.get("kind") == "gasLiquidEquilibrium":
        boundary["points"] = []
        boundary["activeSegments"] = []
        boundary["activeRegionBoundary"] = False
        return boundary

    boundary["points"] = boundary_points(defn, log_c, nernst_factor)
    boundary_species = defn.get("species", [])
    region_species = boundary_region_species(defn)
    if region_species != boundary_species:
        boundary["regionSpecies"] = region_species

    active_segments = (
        active_segments_by_id.get(defn["id"], [])
        if active_segments_by_id is not None
        else []
    )
    if defn.get("kind") != "water":
        boundary["activeSegments"] = active_segments

    if defn.get("kind") == "water":
        boundary["activeRegionBoundary"] = True
    elif defn.get("plotBoundary") is False:
        boundary["activeRegionBoundary"] = False
    elif active_segments_by_id is not None:
        boundary["activeRegionBoundary"] = bool(active_segments)
    elif active_pairs is None:
        boundary["activeRegionBoundary"] = True
    elif len(region_species) == 2:
        boundary["activeRegionBoundary"] = tuple(sorted(region_species)) in active_pairs
    else:
        boundary["activeRegionBoundary"] = False
    return boundary
