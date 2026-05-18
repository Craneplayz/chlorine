from __future__ import annotations

import numpy as np

from .chemistry import (
    chlorine_atom_count_for_label,
    log_activity,
    species_chlorine_counts,
    term_species_id,
)
from .config import (
    ALPHA_LAMBDA_INITIAL_BOUND,
    ALPHA_MASS_BALANCE_ITERATIONS,
    ALPHA_MODEL_CHECK_TOLERANCE,
    BALANCE_TOLERANCE,
    REGION_E_STEP,
    REGION_PH_STEP,
    SPECIES,
)


def alpha_species_order(boundary_defs: list[dict]) -> list[str]:
    species_ids = [species["id"] for species in SPECIES]
    active_species = set()
    for defn in boundary_defs:
        if defn.get("kind") == "water":
            continue
        if defn.get("regionReference") or defn.get("plotBoundary") is False:
            continue
        for side_name in ("reactants", "products"):
            for term in defn[side_name]:
                species_id = term_species_id(term["label"])
                if species_id is not None:
                    active_species.add(species_id)
                elif chlorine_atom_count_for_label(term["label"]) > 0:
                    raise ValueError(
                        f"Boundary {defn['id']} uses unmapped chlorine term "
                        f"{term['label']!r}"
                    )
    return [species_id for species_id in species_ids if species_id in active_species]

def alpha_constraint_boundaries(boundary_defs: list[dict]) -> list[dict]:
    constraints = []
    for defn in boundary_defs:
        if defn.get("kind") == "water":
            continue
        if defn.get("regionReference") or defn.get("plotBoundary") is False:
            continue
        constraints.append(defn)
    return constraints

def reaction_species_coefficients(defn: dict, species_index: dict[str, int]) -> np.ndarray:
    coefficients = np.zeros(len(species_index))

    for term in defn["reactants"]:
        species_id = term_species_id(term["label"])
        if species_id is not None and species_id in species_index:
            coefficients[species_index[species_id]] -= float(term["coefficient"])

    for term in defn["products"]:
        species_id = term_species_id(term["label"])
        if species_id is not None and species_id in species_index:
            coefficients[species_index[species_id]] += float(term["coefficient"])

    return coefficients

def reaction_known_log_q(defn: dict, ph: np.ndarray, log_c: float) -> np.ndarray:
    known = np.zeros_like(ph, dtype=float)
    for term in defn["products"]:
        if term_species_id(term["label"]) is None:
            known += float(term["coefficient"]) * log_activity(term, ph, log_c)
    for term in defn["reactants"]:
        if term_species_id(term["label"]) is None:
            known -= float(term["coefficient"]) * log_activity(term, ph, log_c)
    return known

def alpha_constraint_solver(
    boundary_defs: list[dict],
    species_ids: list[str],
) -> tuple[np.ndarray, list[dict], np.ndarray]:
    species_index = {species_id: index for index, species_id in enumerate(species_ids)}
    constraints = []
    rows = []
    for defn in alpha_constraint_boundaries(boundary_defs):
        row = reaction_species_coefficients(defn, species_index)
        if np.any(np.abs(row) > BALANCE_TOLERANCE):
            constraints.append(defn)
            rows.append(row)
    if not rows:
        raise ValueError("Alpha model has no usable half-reaction constraints")

    matrix = np.vstack(rows)
    return np.linalg.pinv(matrix), constraints, matrix

def reaction_known_log_q_coefficients(defn: dict) -> dict[str, float]:
    coefficients = {"constant": 0.0, "pH": 0.0, "logC": 0.0}

    for side_name, sign in (("products", 1.0), ("reactants", -1.0)):
        for term in defn[side_name]:
            if term_species_id(term["label"]) is not None:
                continue
            model = term.get("logActivity", {})
            term_coefficient = sign * float(term["coefficient"])
            for key in coefficients:
                coefficients[key] += term_coefficient * float(model.get(key, 0.0))

    return coefficients

def composition_model(boundary_defs: list[dict], nernst_factor: float) -> dict:
    species_ids = alpha_species_order(boundary_defs)
    solver, constraints, _matrix = alpha_constraint_solver(boundary_defs, species_ids)
    target_coefficients = []

    for defn in constraints:
        known = reaction_known_log_q_coefficients(defn)
        nernst_scale = float(defn["electronCount"]) / nernst_factor
        target_coefficients.append(
            [
                nernst_scale * float(defn["standardPotentialV"]) - known["constant"],
                -known["pH"],
                -nernst_scale,
                -known["logC"],
            ]
        )

    relative_coefficients = solver @ np.array(target_coefficients)
    chlorine_counts = species_chlorine_counts(species_ids)

    return {
        "kind": "mass-balanced-alpha-linear",
        "concentrationBasis": "molecular",
        "massBalance": "sum(chlorineCount * concentration) = 10^logC",
        "variables": ["constant", "pH", "E", "logC"],
        "species": [
            {
                "id": species_id,
                "chlorineCount": int(count)
                if abs(count - round(count)) < BALANCE_TOLERANCE
                else float(count),
                "coefficients": {
                    "constant": float(coefficients[0]),
                    "pH": float(coefficients[1]),
                    "E": float(coefficients[2]),
                    "logC": float(coefficients[3]),
                },
            }
            for species_id, count, coefficients in zip(
                species_ids, chlorine_counts, relative_coefficients
            )
        ],
    }

def log10sumexp(values: np.ndarray, axis: int = 0) -> np.ndarray:
    maximum = np.max(values, axis=axis, keepdims=True)
    summed = np.sum(np.power(10.0, values - maximum), axis=axis, keepdims=True)
    result = maximum + np.log10(summed)
    return np.squeeze(result, axis=axis)

def log_total_chlorine_for_lambda(
    base_atom_logs: np.ndarray,
    chlorine_counts: np.ndarray,
    lambdas: np.ndarray,
) -> np.ndarray:
    return log10sumexp(
        base_atom_logs + chlorine_counts[:, np.newaxis] * lambdas[np.newaxis, :],
        axis=0,
    )

def solve_mass_balance_lambda(
    base_atom_logs: np.ndarray,
    chlorine_counts: np.ndarray,
    log_c: float,
) -> np.ndarray:
    point_count = base_atom_logs.shape[1]
    lower = np.full(point_count, -ALPHA_LAMBDA_INITIAL_BOUND)
    upper = np.full(point_count, ALPHA_LAMBDA_INITIAL_BOUND)

    for _iteration in range(12):
        lower_total = log_total_chlorine_for_lambda(
            base_atom_logs, chlorine_counts, lower
        )
        mask = lower_total > log_c
        if not np.any(mask):
            break
        lower[mask] -= ALPHA_LAMBDA_INITIAL_BOUND

    for _iteration in range(12):
        upper_total = log_total_chlorine_for_lambda(
            base_atom_logs, chlorine_counts, upper
        )
        mask = upper_total < log_c
        if not np.any(mask):
            break
        upper[mask] += ALPHA_LAMBDA_INITIAL_BOUND

    if np.any(log_total_chlorine_for_lambda(base_atom_logs, chlorine_counts, lower) > log_c):
        raise ValueError("Could not bracket lower mass-balance lambda")
    if np.any(log_total_chlorine_for_lambda(base_atom_logs, chlorine_counts, upper) < log_c):
        raise ValueError("Could not bracket upper mass-balance lambda")

    for _iteration in range(ALPHA_MASS_BALANCE_ITERATIONS):
        middle = (lower + upper) / 2
        middle_total = log_total_chlorine_for_lambda(
            base_atom_logs, chlorine_counts, middle
        )
        lower[middle_total < log_c] = middle[middle_total < log_c]
        upper[middle_total >= log_c] = middle[middle_total >= log_c]

    return (lower + upper) / 2

def alpha_log_fractions(
    relative_log_activities: np.ndarray,
    chlorine_counts: np.ndarray,
    log_c: float,
) -> np.ndarray:
    atom_count_logs = np.log10(chlorine_counts)[:, np.newaxis]
    base_atom_logs = atom_count_logs + relative_log_activities
    lambdas = solve_mass_balance_lambda(base_atom_logs, chlorine_counts, log_c)
    molecular_log_activities = (
        relative_log_activities
        + chlorine_counts[:, np.newaxis] * lambdas[np.newaxis, :]
    )
    alpha_logs = atom_count_logs + molecular_log_activities - log_c
    alpha_sum_logs = log10sumexp(alpha_logs, axis=0)
    if np.max(np.abs(alpha_sum_logs)) > ALPHA_MODEL_CHECK_TOLERANCE:
        raise ValueError(
            "Alpha mass-balance check failed: "
            f"max log10(sum alpha) error = {np.max(np.abs(alpha_sum_logs))}"
        )
    return alpha_logs

def classified_alpha_region_grid(
    log_c: float,
    boundary_defs: list[dict],
    nernst_factor: float,
    axes: dict,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    ph_min = float(axes["pH"]["min"])
    ph_max = float(axes["pH"]["max"])
    e_min = float(axes["E"]["min"])
    e_max = float(axes["E"]["max"])

    ph_edges = np.linspace(
        ph_min,
        ph_max,
        int(round((ph_max - ph_min) / REGION_PH_STEP)) + 1,
    )
    e_edges = np.linspace(
        e_min,
        e_max,
        int(round((e_max - e_min) / REGION_E_STEP)) + 1,
    )
    ph_centers = (ph_edges[:-1] + ph_edges[1:]) / 2
    e_centers = (e_edges[:-1] + e_edges[1:]) / 2
    ph_grid, e_grid = np.meshgrid(ph_centers, e_centers)

    species_ids = alpha_species_order(boundary_defs)
    solver, constraints, _matrix = alpha_constraint_solver(boundary_defs, species_ids)
    target_rows = []
    for defn in constraints:
        known_log_q = reaction_known_log_q(defn, ph_grid, log_c)
        target = (
            float(defn["electronCount"])
            / nernst_factor
            * (float(defn["standardPotentialV"]) - e_grid)
            - known_log_q
        )
        target_rows.append(target.reshape(1, -1))

    target_matrix = np.vstack(target_rows)
    relative_log_activities = solver @ target_matrix
    chlorine_counts = species_chlorine_counts(species_ids)
    alpha_logs = alpha_log_fractions(
        relative_log_activities, chlorine_counts, log_c
    )
    classification = np.argmax(alpha_logs, axis=0).reshape(e_grid.shape)
    return classification, ph_edges, e_edges, species_ids
