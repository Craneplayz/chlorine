from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

MATPLOTLIB_CONFIG_DIR = Path(tempfile.gettempdir()) / "chlorine-pourbaix-mplconfig"
MATPLOTLIB_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ["MPLCONFIGDIR"] = str(MATPLOTLIB_CONFIG_DIR)

FONTCONFIG_CACHE_HOME = Path(tempfile.gettempdir()) / "chlorine-pourbaix-cache"
FONTCONFIG_CACHE_HOME.mkdir(parents=True, exist_ok=True)
os.environ["XDG_CACHE_HOME"] = str(FONTCONFIG_CACHE_HOME)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import patheffects as path_effects
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch

from .alpha import (
    alpha_constraint_solver,
    alpha_log_fractions,
    alpha_species_order,
    reaction_known_log_q,
)
from .chemistry import (
    boundary_potential,
    normalize_half_reaction_payload,
    nernst_factor_v,
    species_chlorine_counts,
)
from .config import (
    DEFAULT_TEMPERATURE_C,
    KINETIC_MODEL_OUT,
    KINETIC_PDF_OUT,
    KINETIC_PNG_OUT,
    ROOT,
    SPECIES,
    STATIC_LOG_C,
)
from .display import matplotlib_chemical_text
from .generation import axes_config

FAST_SPECIES = ("cl_minus", "cl2", "hocl", "ocl_minus")
KINETIC_SPECIES = FAST_SPECIES + ("clo3_minus", "clo4_minus")
SLOW_SPECIES = ("clo3_minus", "clo4_minus")
KINETIC_TIMES = (
    {"label": "1 s", "seconds": 1.0},
    {"label": "1 h", "seconds": 60.0 * 60.0},
    {"label": "1 day", "seconds": 24.0 * 60.0 * 60.0},
    {"label": "1 year", "seconds": 365.25 * 24.0 * 60.0 * 60.0},
)
KINETIC_GRID = {"pHCount": 260, "eCount": 220}
KINETIC_LOG_TIME_AXIS = {
    "min": 0.0,
    "max": 7.5,
    "step": 0.05,
    "default": round(math.log10(24.0 * 60.0 * 60.0), 5),
    "unit": "log10 seconds",
}
HOCL_PKA = 7.5
CL2_HYDROLYSIS_MIDPOINT_PH = 3.3
SIGMOID_WIDTH_V = 0.08
KINETIC_WARNING = (
    "Schematic kinetic visualization only. Rate constants are adjustable teaching "
    "parameters, not calibrated chlorine kinetics."
)
PLOT_FACE_COLOR = "#fbfaf6"
PLOT_FRAME_COLOR = "#455a64"
PLOT_GRID_COLOR = "#e6e1d8"
PLOT_EDGE_COLOR = "#cfd8dc"
WATER_BOUNDARY_COLOR = "#90a4ae"
PANEL_TITLE_SIZE = 20
AXIS_LABEL_SIZE = 17
TICK_LABEL_SIZE = 14
LEGEND_TEXT_SIZE = 13
FOOTNOTE_TEXT_SIZE = 12
REGION_LABEL_SIZE = 13
REGION_LABEL_MIN_CELLS = 90
RATE_PARAMETERS = {
    "clo3_minus": {
        "label": "chlorate formation",
        "boundaryId": "clo3_cl",
        "k0PerSecond": 2.0e-5,
        "betaPerVolt": 3.5,
        "rateLaw": "k3 = k0 * exp(beta * max(Eh - Eeq(ClO3-/Cl-), 0))",
    },
    "clo4_minus": {
        "label": "perchlorate formation from chlorate",
        "boundaryId": "clo4_cl",
        "k0PerSecond": 2.0e-8,
        "betaPerVolt": 5.5,
        "rateLaw": "k4 = k0 * exp(beta * max(Eh - Eeq(ClO4-/Cl-), 0))",
    },
}


def grid_from_axes(axes: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    ph_edges = np.linspace(
        float(axes["pH"]["min"]),
        float(axes["pH"]["max"]),
        KINETIC_GRID["pHCount"] + 1,
    )
    e_edges = np.linspace(
        float(axes["E"]["min"]),
        float(axes["E"]["max"]),
        KINETIC_GRID["eCount"] + 1,
    )
    ph_centers = (ph_edges[:-1] + ph_edges[1:]) / 2.0
    e_centers = (e_edges[:-1] + e_edges[1:]) / 2.0
    ph_grid, e_grid = np.meshgrid(ph_centers, e_centers)
    return ph_edges, e_edges, ph_grid, e_grid


def boundary_by_id(boundary_defs: list[dict], boundary_id: str) -> dict:
    for boundary_def in boundary_defs:
        if boundary_def["id"] == boundary_id:
            return boundary_def
    raise ValueError(f"Missing kinetic boundary {boundary_id!r}")


def logistic(value: np.ndarray, width: float) -> np.ndarray:
    scaled = np.clip(value / width, -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(-scaled))


def equilibrium_alpha_by_species(
    boundary_defs: list[dict],
    nernst_factor: float,
    log_c: float,
    ph_grid: np.ndarray,
    e_grid: np.ndarray,
) -> dict[str, np.ndarray]:
    species_ids = alpha_species_order(boundary_defs)
    solver, constraints, _matrix = alpha_constraint_solver(boundary_defs, species_ids)
    target_rows = []

    for boundary_def in constraints:
        known_log_q = reaction_known_log_q(boundary_def, ph_grid, log_c)
        target = (
            float(boundary_def["electronCount"])
            / nernst_factor
            * (float(boundary_def["standardPotentialV"]) - e_grid)
            - known_log_q
        )
        target_rows.append(target.reshape(1, -1))

    relative_log_activities = solver @ np.vstack(target_rows)
    chlorine_counts = species_chlorine_counts(species_ids)
    alpha_logs = alpha_log_fractions(
        relative_log_activities,
        chlorine_counts,
        log_c,
    )
    alpha_values = np.power(10.0, alpha_logs).reshape(
        len(species_ids),
        *ph_grid.shape,
    )
    return {
        species_id: alpha_values[index] for index, species_id in enumerate(species_ids)
    }


def fast_equilibrium_fractions(
    boundary_defs: list[dict],
    nernst_factor: float,
    log_c: float,
    ph_grid: np.ndarray,
    e_grid: np.ndarray,
) -> dict[str, np.ndarray]:
    ocl_boundary = boundary_by_id(boundary_defs, "ocl_cl")
    active_drive = logistic(
        e_grid - boundary_potential(ocl_boundary, ph_grid, log_c, nernst_factor),
        SIGMOID_WIDTH_V,
    )
    cl2_share = 0.35 / (1.0 + np.power(10.0, ph_grid - CL2_HYDROLYSIS_MIDPOINT_PH))
    hocl_share = 1.0 / (1.0 + np.power(10.0, ph_grid - HOCL_PKA))
    free_active = active_drive

    return {
        "cl_minus": 1.0 - free_active,
        "cl2": free_active * cl2_share,
        "hocl": free_active * (1.0 - cl2_share) * hocl_share,
        "ocl_minus": free_active * (1.0 - cl2_share) * (1.0 - hocl_share),
    }


def rate_grid(
    boundary_defs: list[dict],
    nernst_factor: float,
    log_c: float,
    ph_grid: np.ndarray,
    e_grid: np.ndarray,
    species_id: str,
) -> np.ndarray:
    parameters = RATE_PARAMETERS[species_id]
    boundary_def = boundary_by_id(boundary_defs, parameters["boundaryId"])
    overpotential = np.maximum(
        e_grid - boundary_potential(boundary_def, ph_grid, log_c, nernst_factor),
        0.0,
    )
    return float(parameters["k0PerSecond"]) * np.exp(
        float(parameters["betaPerVolt"]) * overpotential
    )


def chain_fractions(
    k3: np.ndarray,
    k4: np.ndarray,
    seconds: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    fast = np.exp(-k3 * seconds)
    chlorate = np.zeros_like(k3)
    same_rate = np.abs(k4 - k3) < 1e-20
    different_rate = ~same_rate

    chlorate[same_rate] = k3[same_rate] * seconds * np.exp(-k3[same_rate] * seconds)
    with np.errstate(divide="ignore", invalid="ignore"):
        chlorate[different_rate] = (
            k3[different_rate]
            / (k4[different_rate] - k3[different_rate])
            * (
                np.exp(-k3[different_rate] * seconds)
                - np.exp(-k4[different_rate] * seconds)
            )
        )

    perchlorate = 1.0 - fast - chlorate
    fast = np.clip(fast, 0.0, 1.0)
    chlorate = np.clip(chlorate, 0.0, 1.0)
    perchlorate = np.clip(perchlorate, 0.0, 1.0)
    total = fast + chlorate + perchlorate
    overflow = total > 1.0
    chlorate[overflow] /= total[overflow]
    perchlorate[overflow] /= total[overflow]
    fast[overflow] = 1.0 - chlorate[overflow] - perchlorate[overflow]
    return fast, chlorate, perchlorate


def kinetic_fractions_for_time(
    equilibrium_alpha: dict[str, np.ndarray],
    fast_alpha: dict[str, np.ndarray],
    k3: np.ndarray,
    k4: np.ndarray,
    seconds: float,
) -> dict[str, np.ndarray]:
    _fast_chain, chlorate_chain, perchlorate_chain = chain_fractions(k3, k4, seconds)
    slow_capacity = np.clip(
        equilibrium_alpha.get("clo3_minus", 0.0)
        + equilibrium_alpha.get("clo4_minus", 0.0),
        0.0,
        1.0,
    )
    perchlorate_share = np.divide(
        equilibrium_alpha.get("clo4_minus", 0.0),
        slow_capacity,
        out=np.zeros_like(slow_capacity),
        where=slow_capacity > 1e-12,
    )

    perchlorate = slow_capacity * perchlorate_chain * perchlorate_share
    chlorate = slow_capacity * (
        chlorate_chain + perchlorate_chain * (1.0 - perchlorate_share)
    )
    chlorate = np.clip(chlorate, 0.0, 1.0)
    perchlorate = np.clip(perchlorate, 0.0, 1.0 - chlorate)
    fast_remainder = np.clip(1.0 - chlorate - perchlorate, 0.0, 1.0)

    fractions = {
        species_id: fast_remainder * fast_alpha[species_id]
        for species_id in FAST_SPECIES
    }
    fractions["clo3_minus"] = chlorate
    fractions["clo4_minus"] = perchlorate
    return fractions


def classify_species(fractions: dict[str, np.ndarray]) -> np.ndarray:
    stacked = np.stack([fractions[species_id] for species_id in KINETIC_SPECIES])
    return np.argmax(stacked, axis=0)


def connected_components(mask: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    visited = np.zeros(mask.shape, dtype=bool)
    components = []
    start_rows, start_columns = np.where(mask)

    for start_row, start_column in zip(start_rows, start_columns):
        if visited[start_row, start_column]:
            continue

        stack = [(int(start_row), int(start_column))]
        visited[start_row, start_column] = True
        rows = []
        columns = []

        while stack:
            row, column = stack.pop()
            rows.append(row)
            columns.append(column)

            for next_row, next_column in (
                (row - 1, column),
                (row + 1, column),
                (row, column - 1),
                (row, column + 1),
            ):
                if (
                    next_row < 0
                    or next_row >= mask.shape[0]
                    or next_column < 0
                    or next_column >= mask.shape[1]
                    or visited[next_row, next_column]
                    or not mask[next_row, next_column]
                ):
                    continue
                visited[next_row, next_column] = True
                stack.append((next_row, next_column))

        components.append((np.array(rows), np.array(columns)))

    return components


def component_label_point(
    rows: np.ndarray,
    columns: np.ndarray,
    ph_grid: np.ndarray,
    e_grid: np.ndarray,
) -> tuple[float, float]:
    center_row = float(np.mean(rows))
    center_column = float(np.mean(columns))
    label_index = int(
        np.argmin((rows - center_row) ** 2 + (columns - center_column) ** 2)
    )
    row = int(rows[label_index])
    column = int(columns[label_index])
    return float(ph_grid[row, column]), float(e_grid[row, column])


def plot_region_labels(
    ax: plt.Axes,
    classification: np.ndarray,
    ph_grid: np.ndarray,
    e_grid: np.ndarray,
    species_by_id: dict[str, dict],
) -> None:
    for species_index, species_id in enumerate(KINETIC_SPECIES):
        species = species_by_id[species_id]
        for rows, columns in connected_components(classification == species_index):
            if rows.size < REGION_LABEL_MIN_CELLS:
                continue

            ph, e = component_label_point(rows, columns, ph_grid, e_grid)
            ax.text(
                ph,
                e,
                matplotlib_chemical_text(species["label"]),
                color=species["color"],
                fontsize=REGION_LABEL_SIZE,
                fontweight="bold",
                ha="center",
                va="center",
                path_effects=[
                    path_effects.withStroke(
                        linewidth=3.0,
                        foreground="white",
                        alpha=0.85,
                    )
                ],
                zorder=4,
            )


def plot_reference_boundaries(
    ax: plt.Axes,
    boundary_defs: list[dict],
    nernst_factor: float,
    log_c: float,
    ph_values: np.ndarray,
    show_labels: bool,
) -> None:
    species_by_id = {species["id"]: species for species in SPECIES}
    for boundary_id, label, linestyle, color in (
        ("water_o2_h2o", "O2/H2O", "--", WATER_BOUNDARY_COLOR),
        ("water_h2_h2o", "H+/H2", "--", WATER_BOUNDARY_COLOR),
        ("clo3_cl", "ClO3-/Cl-", ":", species_by_id["clo3_minus"]["color"]),
        ("clo4_cl", "ClO4-/Cl-", "-.", species_by_id["clo4_minus"]["color"]),
    ):
        boundary_def = boundary_by_id(boundary_defs, boundary_id)
        ax.plot(
            ph_values,
            boundary_potential(boundary_def, ph_values, log_c, nernst_factor),
            color=color,
            linestyle=linestyle,
            linewidth=2.4,
            label=label if show_labels else "_nolegend_",
            zorder=5,
        )


def write_kinetic_model_json() -> None:
    species_by_id = {species["id"]: species for species in SPECIES}
    metadata = {
        "title": "Kinetically constrained chlorine Eh-pH diagram",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "scripts/chlorine.py --kinetic",
        "temperatureC": DEFAULT_TEMPERATURE_C,
        "logC": STATIC_LOG_C,
        "grid": KINETIC_GRID,
        "kineticSpecies": [
            species_by_id[species_id] for species_id in KINETIC_SPECIES
        ],
        "fastSpecies": list(FAST_SPECIES),
        "slowSpecies": list(SLOW_SPECIES),
        "controls": {
            "logTimeSeconds": KINETIC_LOG_TIME_AXIS,
            "logC": {
                "source": "data/chlorine_pourbaix.json axes.logC",
                "default": STATIC_LOG_C,
            },
            "temperatureC": {
                "source": "data/chlorine_pourbaix.json axes.temperatureC",
                "default": DEFAULT_TEMPERATURE_C,
            },
        },
        "defaultSeconds": 24.0 * 60.0 * 60.0,
        "timeSlices": list(KINETIC_TIMES),
        "initialCondition": (
            "Total chlorine starts in the fast pool Cl-, Cl2(aq), HOCl, and OCl-. "
            "The fast pool is distributed by pH-dependent acid-base/hydrolysis "
            "speciation and a redox accessibility factor tied to the existing "
            "OCl-/Cl- boundary."
        ),
        "fastEquilibria": [
            "Cl2(aq) + H2O <=> HOCl + H+ + Cl-",
            "HOCl <=> H+ + OCl-",
        ],
        "fastEquilibriumParameters": {
            "hoclPka": HOCL_PKA,
            "cl2HydrolysisMidpointPH": CL2_HYDROLYSIS_MIDPOINT_PH,
            "redoxSigmoidWidthV": SIGMOID_WIDTH_V,
        },
        "slowKinetics": [
            {
                "species": species_id,
                **parameters,
            }
            for species_id, parameters in RATE_PARAMETERS.items()
        ],
        "thermodynamicTarget": (
            "The slow oxychlorine capacity is capped by the existing equilibrium "
            "alpha model computed from data/chlorine_half_reactions.json."
        ),
        "warning": KINETIC_WARNING,
    }
    KINETIC_MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    KINETIC_MODEL_OUT.write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )


def write_kinetic_phase_diagram(raw_half_reaction_payload: dict) -> None:
    axes = axes_config([DEFAULT_TEMPERATURE_C])
    normalized_payload = normalize_half_reaction_payload(
        raw_half_reaction_payload,
        DEFAULT_TEMPERATURE_C,
    )
    boundary_defs = normalized_payload["boundaries"]
    nernst_factor = nernst_factor_v(DEFAULT_TEMPERATURE_C)
    ph_edges, e_edges, ph_grid, e_grid = grid_from_axes(axes)
    ph_values = np.linspace(axes["pH"]["min"], axes["pH"]["max"], 400)

    equilibrium_alpha = equilibrium_alpha_by_species(
        boundary_defs,
        nernst_factor,
        STATIC_LOG_C,
        ph_grid,
        e_grid,
    )
    fast_alpha = fast_equilibrium_fractions(
        boundary_defs,
        nernst_factor,
        STATIC_LOG_C,
        ph_grid,
        e_grid,
    )
    k3 = rate_grid(
        boundary_defs,
        nernst_factor,
        STATIC_LOG_C,
        ph_grid,
        e_grid,
        "clo3_minus",
    )
    k4 = rate_grid(
        boundary_defs,
        nernst_factor,
        STATIC_LOG_C,
        ph_grid,
        e_grid,
        "clo4_minus",
    )

    species_by_id = {species["id"]: species for species in SPECIES}
    color_map = ListedColormap(
        [species_by_id[species_id]["color"] for species_id in KINETIC_SPECIES]
    )
    norm = BoundaryNorm(np.arange(len(KINETIC_SPECIES) + 1) - 0.5, color_map.N)

    fig, axes_grid = plt.subplots(2, 2, figsize=(13.5, 8.2), sharex=True, sharey=True)
    for ax, time_def in zip(axes_grid.flat, KINETIC_TIMES):
        fractions = kinetic_fractions_for_time(
            equilibrium_alpha,
            fast_alpha,
            k3,
            k4,
            float(time_def["seconds"]),
        )
        classification = classify_species(fractions)
        ax.pcolormesh(
            ph_edges,
            e_edges,
            classification,
            cmap=color_map,
            norm=norm,
            shading="auto",
            alpha=0.18,
        )
        plot_region_labels(ax, classification, ph_grid, e_grid, species_by_id)
        plot_reference_boundaries(
            ax,
            boundary_defs,
            nernst_factor,
            STATIC_LOG_C,
            ph_values,
            show_labels=ax is axes_grid.flat[0],
        )
        ax.set_title(
            f"t = {time_def['label']}",
            fontsize=PANEL_TITLE_SIZE,
            fontweight="bold",
        )
        ax.set_xlim(axes["pH"]["min"], axes["pH"]["max"])
        ax.set_ylim(axes["E"]["min"], axes["E"]["max"])
        ax.grid(True, color=PLOT_GRID_COLOR, linewidth=1.0, alpha=0.72)
        ax.set_facecolor(PLOT_FACE_COLOR)
        ax.tick_params(
            axis="both",
            colors=PLOT_FRAME_COLOR,
            labelsize=TICK_LABEL_SIZE,
            width=1.4,
        )
        for spine in ax.spines.values():
            spine.set_color(PLOT_FRAME_COLOR)
            spine.set_linewidth(1.3)

    for ax in axes_grid[-1, :]:
        ax.set_xlabel("pH", fontsize=AXIS_LABEL_SIZE)
    for ax in axes_grid[:, 0]:
        ax.set_ylabel("Eh vs SHE (V)", fontsize=AXIS_LABEL_SIZE)

    legend_handles = [
        Patch(
            facecolor=species_by_id[species_id]["color"],
            edgecolor="none",
            label=matplotlib_chemical_text(species_by_id[species_id]["label"]),
        )
        for species_id in KINETIC_SPECIES
    ]
    boundary_handles, boundary_labels = axes_grid.flat[0].get_legend_handles_labels()
    labels = [
        *[handle.get_label() for handle in legend_handles],
        *boundary_labels,
    ]
    fig.legend(
        handles=legend_handles + boundary_handles,
        labels=labels,
        loc="center left",
        bbox_to_anchor=(0.86, 0.5),
        # frameon=False,
        # framealpha=0.94,
        facecolor="white",
        edgecolor=PLOT_EDGE_COLOR,
        fontsize=LEGEND_TEXT_SIZE,
    )
    fig.tight_layout(rect=(0, 0.02, 0.87, 0.98))

    KINETIC_PNG_OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(KINETIC_PNG_OUT, dpi=220, facecolor="white")
    fig.savefig(KINETIC_PDF_OUT, facecolor="white")
    plt.close(fig)
    write_kinetic_model_json()
    print(f"Wrote {KINETIC_PNG_OUT.relative_to(ROOT)}")
    print(f"Wrote {KINETIC_PDF_OUT.relative_to(ROOT)}")
    print(f"Wrote {KINETIC_MODEL_OUT.relative_to(ROOT)}")
