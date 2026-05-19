from __future__ import annotations

import os
import tempfile
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
from matplotlib.patches import Polygon

from .config import (
    ROOT,
    STATIC_LOG_C,
    STATIC_PDF_OUT,
    STATIC_PO2_LOG10_LEVELS,
    STATIC_PNG_OUT,
    STATIC_TEMPERATURE_C,
)
from .display import matplotlib_chemical_text
from .generation import slice_for_log_c


def nernst_factor_for_static_payload(payload: dict, static_temperature_c: float) -> float:
    for temperature_payload in payload.get("temperatureSlices", []):
        if abs(float(temperature_payload["temperatureC"]) - static_temperature_c) < 1e-9:
            return float(temperature_payload["nernstFactorV"])

    return float(payload.get("metadata", {}).get("nernstFactorV", 0.05915935))


def oxygen_water_boundary(current_slice: dict) -> dict | None:
    for boundary in current_slice.get("boundaries", []):
        if boundary.get("id") == "water_o2_h2o":
            return boundary

    for boundary in current_slice.get("boundaries", []):
        if boundary.get("kind") == "water" and "O2" in boundary.get("label", ""):
            return boundary

    return None


def format_log_po2_label(log_po2: float) -> str:
    if abs(log_po2) < 1e-9:
        return r"$pO_2=1$"

    exponent = int(round(log_po2)) if abs(log_po2 - round(log_po2)) < 1e-9 else log_po2
    return rf"$pO_2=10^{{{exponent:g}}}$"


def draw_po2_contours(
    ax,
    current_slice: dict,
    axes: dict,
    nernst_factor: float,
    po2_log10_levels: list[float],
) -> None:
    boundary = oxygen_water_boundary(current_slice)
    if boundary is None:
        return

    e_min = float(axes["E"]["min"])
    e_max = float(axes["E"]["max"])
    ph_min = float(axes["pH"]["min"])
    ph_max = float(axes["pH"]["max"])
    sorted_levels = sorted({float(level) for level in po2_log10_levels})

    for index, log_po2 in enumerate(sorted_levels):
        e_shift = nernst_factor * float(log_po2) / 4.0
        points = [
            {"pH": point["pH"], "E": point["E"] + e_shift}
            for point in boundary.get("points", [])
        ]
        if len(points) < 2:
            continue

        x_values = [point["pH"] for point in points]
        y_values = [point["E"] for point in points]
        ax.plot(
            x_values,
            y_values,
            color="#263238",
            linestyle=(0, (1.2, 2.1)),
            linewidth=1.05,
            alpha=0.72,
            label="pO2 contours" if index == 0 else "_nolegend_",
            zorder=3,
        )

        visible_points = [
            point
            for point in points
            if e_min <= point["E"] <= e_max
        ]
        if not visible_points:
            continue

        label_point = min(
            visible_points,
            key=lambda point: abs(
                float(point["pH"])
                - max(
                    ph_min + 0.5,
                    ph_max - 1.4 - index * 0.8,
                )
            ),
        )
        ax.text(
            label_point["pH"],
            label_point["E"],
            format_log_po2_label(float(log_po2)),
            color="#263238",
            fontsize=7.5,
            ha="left",
            va="center",
            zorder=6,
            bbox={
                "boxstyle": "round,pad=0.14",
                "facecolor": "#fbfaf6",
                "edgecolor": "none",
                "alpha": 0.82,
            },
        )


def write_static_phase_diagram(
    payload: dict,
    show_po2_contours: bool = False,
    po2_log10_levels: list[float] | None = None,
) -> None:
    axes = payload["axes"]
    current_slice = slice_for_log_c(payload["slices"], STATIC_LOG_C)
    species_by_id = {species["id"]: species for species in payload["species"]}
    static_temperature_c = float(
        payload.get("metadata", {}).get("staticTemperatureC", STATIC_TEMPERATURE_C)
    )
    explicit_cl2_gas = bool(
        payload.get("metadata", {}).get("modelOptions", {}).get("explicitCl2Gas")
    )
    po2_log10_levels = po2_log10_levels or STATIC_PO2_LOG10_LEVELS
    nernst_factor = nernst_factor_for_static_payload(payload, static_temperature_c)

    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    ax.set_facecolor("#fbfaf6")

    for region in current_slice.get("regions", payload["regions"]):
        species = species_by_id[region["species"]]
        points = [(point["pH"], point["E"]) for point in region["polygon"]]
        ax.add_patch(
            Polygon(
                points,
                closed=True,
                facecolor=species["color"],
                edgecolor="none",
                alpha=0.18,
                zorder=1,
            )
        )
        ax.text(
            region["label"]["pH"],
            region["label"]["E"],
            matplotlib_chemical_text(species["label"]),
            color=species["color"],
            fontsize=12,
            fontweight="bold",
            ha="center",
            va="center",
            zorder=3,
        )

    if show_po2_contours:
        draw_po2_contours(
            ax,
            current_slice,
            axes,
            nernst_factor,
            po2_log10_levels,
        )

    plot_boundaries = current_slice["boundaries"] + current_slice.get(
        "derivedBoundaries", []
    )
    for boundary in plot_boundaries:
        if boundary.get("plotBoundary") is False:
            continue
        is_water = boundary.get("kind") == "water"
        is_dominance = boundary.get("kind") == "dominance"
        if not is_water and not boundary.get("activeRegionBoundary", True):
            continue

        is_reference = boundary.get("regionReference", False)
        plot_segments = (
            [{"points": boundary["points"]}]
            if is_water
            else boundary.get("activeSegments", [])
        )
        for segment_index, segment in enumerate(plot_segments):
            points = segment.get("points", [])
            if len(points) < 2:
                continue

            x_values = [point["pH"] for point in points]
            y_values = [point["E"] for point in points]
            boundary_label = matplotlib_chemical_text(
                boundary.get("equation") or boundary["label"]
            )
            if is_reference:
                boundary_label = f"{boundary_label} (Henry ref)"
            ax.plot(
                x_values,
                y_values,
                color="#78909c" if is_water else boundary["color"],
                linestyle=(
                    "--"
                    if is_water
                    else ":"
                    if is_dominance
                    else "-."
                    if is_reference
                    else "-"
                ),
                linewidth=2.4 if is_dominance else 1.8 if is_water or is_reference else 2.2,
                label=(
                    boundary_label
                    if segment_index == 0
                    else "_nolegend_"
                ),
                zorder=5 if is_reference else 4,
            )

    ax.set_xlim(axes["pH"]["min"], axes["pH"]["max"])
    ax.set_ylim(axes["E"]["min"], axes["E"]["max"])
    ax.set_xlabel("pH")
    ax.set_ylabel("E (V vs SHE)")
    ax.set_title(
        "Chlorine Pourbaix Diagram\n"
        f"(Total chlorine = {10 ** STATIC_LOG_C:g} M; "
        f"T = {static_temperature_c:g} °C"
        f"{'; explicit Cl2(g) ⇌ Cl2(aq)' if explicit_cl2_gas else ''}"
        f"{'; pO2 contours' if show_po2_contours else ''})"
    )
    ax.set_xticks(range(0, 15, 2))
    ax.grid(True, color="#d8d2c8", linewidth=0.8, alpha=0.65)
    ax.legend(
        loc="upper right",
        # bbox_to_anchor=(1.01, 1.0),
        frameon=True,
        framealpha=0.92,
        facecolor="white",
        edgecolor="#cfd8dc",
        fontsize=8,
    )

    STATIC_PNG_OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(STATIC_PNG_OUT, dpi=220, facecolor="white")
    fig.savefig(STATIC_PDF_OUT, facecolor="white")
    plt.close(fig)
