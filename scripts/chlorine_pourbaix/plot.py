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

from .config import ROOT, STATIC_LOG_C, STATIC_PDF_OUT, STATIC_PNG_OUT, STATIC_TEMPERATURE_C
from .display import matplotlib_chemical_text
from .generation import slice_for_log_c


def write_static_phase_diagram(payload: dict) -> None:
    axes = payload["axes"]
    current_slice = slice_for_log_c(payload["slices"], STATIC_LOG_C)
    species_by_id = {species["id"]: species for species in payload["species"]}
    static_temperature_c = float(
        payload.get("metadata", {}).get("staticTemperatureC", STATIC_TEMPERATURE_C)
    )

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
        f"T = {static_temperature_c:g} °C)"
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
