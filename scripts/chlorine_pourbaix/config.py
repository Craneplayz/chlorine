from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "chlorine_pourbaix.json"
HALF_REACTIONS_IN = ROOT / "data" / "chlorine_half_reactions.json"
STATIC_PNG_OUT = ROOT / "assets" / "chlorine_pourbaix_static.png"
STATIC_PDF_OUT = ROOT / "assets" / "chlorine_pourbaix_static.pdf"
KINETIC_PNG_OUT = ROOT / "assets" / "chlorine_kinetic_constrained.png"
KINETIC_PDF_OUT = ROOT / "assets" / "chlorine_kinetic_constrained.pdf"
KINETIC_MODEL_OUT = ROOT / "data" / "chlorine_kinetic_model.json"

GAS_CONSTANT = 8.31446261815324
FARADAY_CONSTANT = 96485.33212
KELVIN_OFFSET = 273.15
LOG10_E = 2.302585092994046
DISPLAY_ARROW = "→"

PH_VALUES = [round(i * 0.25, 2) for i in range(57)]
LOG_C_VALUES = [round(-6 + i * 0.5, 2) for i in range(13)]
TEMPERATURE_C_VALUES = [index * 2.5 for index in range(41)]
DEFAULT_TEMPERATURE_C = 25.0
STATIC_TEMPERATURE_C = 25.0
STATIC_LOG_C = -3.0

SPECIES = [
    {"id": "cl_minus", "label": "Cl-", "color": "#2f6fba"},
    {"id": "cl2", "label": "Cl2(aq)", "color": "#7d5fb2"},
    {"id": "cl3_minus", "label": "Cl3-", "color": "#00838f"},
    {"id": "hocl", "label": "HOCl", "color": "#d6a21e"},
    {"id": "hclo2", "label": "HClO2", "color": "#cc7a29"},
    {"id": "clo2_g", "label": "ClO2(g)", "color": "#8b6f47"},
    {"id": "ocl_minus", "label": "OCl-", "color": "#3aa36d"},
    {"id": "clo3_minus", "label": "ClO3-", "color": "#c45646"},
    {"id": "clo4_minus", "label": "ClO4-", "color": "#6a7a89"},
]

REGION_SPECIES_ALIASES = {"cl2_g": "cl2"}
REGION_PH_STEP = 0.05
REGION_E_STEP = 0.01
REGION_AREA_MIN = 0.03
GEOMETRY_EPSILON = 1e-10
ACTIVE_SEGMENT_SAMPLE_MULTIPLIERS = (0.5, 1.5)
ACTIVE_SEGMENT_MAX_BRIDGED_GAP = 1
HPLUS_LOG_ACTIVITY = {"pH": -1}
OH_LOG_ACTIVITY = {"constant": -14, "pH": 1}
WATER_LOG_ACTIVITY: dict = {}
BALANCE_TOLERANCE = 1e-9
NORMALIZATION_CHECK_PH_VALUES = (0.0, 7.0, 14.0)
NORMALIZATION_CHECK_LOG_C_VALUES = (-6.0, -3.0, 0.0)
ALPHA_MODEL_CHECK_TOLERANCE = 1e-9
ALPHA_MASS_BALANCE_ITERATIONS = 90
ALPHA_LAMBDA_INITIAL_BOUND = 200.0
DERIVED_CL2_CL_BOUNDARY_ID = "dominance_cl2_cl_minus"
TERM_SPECIES_ALIASES = {
    "Cl-": "cl_minus",
    "Cl2": "cl2",
    "Cl2(aq)": "cl2",
    "Cl2(g)": "cl2",
    "Cl3-": "cl3_minus",
    "HClO": "hocl",
    "HOCl": "hocl",
    "HClO2": "hclo2",
    "ClO2(g)": "clo2_g",
    "ClO-": "ocl_minus",
    "OCl-": "ocl_minus",
    "ClO3-": "clo3_minus",
    "ClO4-": "clo4_minus",
}
