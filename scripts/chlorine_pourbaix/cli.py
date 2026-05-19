from __future__ import annotations

import argparse

from .chemistry import load_half_reaction_payload
from .config import (
    ROOT,
    STATIC_PDF_OUT,
    STATIC_PO2_LOG10_LEVELS,
    STATIC_PNG_OUT,
    STATIC_TEMPERATURE_C,
    chlorine_model_context,
)
from .generation import generate_interactive_payload, write_interactive_json
from .kinetics import write_kinetic_phase_diagram
from .plot import write_static_phase_diagram


def parse_static_po2_levels(value: str) -> list[float]:
    levels = []
    for raw_level in value.split(","):
        raw_level = raw_level.strip()
        if not raw_level:
            continue
        try:
            level = float(raw_level)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"invalid log10(pO2/bar) level {raw_level!r}"
            ) from exc
        if level not in levels:
            levels.append(level)

    if not levels:
        raise argparse.ArgumentTypeError(
            "provide at least one comma-separated log10(pO2/bar) level"
        )

    return levels


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the chlorine Pourbaix interactive JSON and/or the fixed "
            "25 C, 1 mM static PNG/PDF exports."
        )
    )
    parser.add_argument(
        "--interactive-json",
        action="store_true",
        help="write data/chlorine_pourbaix.json with concentration and temperature slices",
    )
    parser.add_argument(
        "--static",
        action="store_true",
        help="write only the 25 C, 1 mM static PNG/PDF exports unless combined with --interactive-json",
    )
    parser.add_argument(
        "--kinetic",
        action="store_true",
        help="write the schematic kinetically constrained chlorine Eh-pH PNG/PDF and metadata",
    )
    parser.add_argument(
        "--explicit-cl2-gas",
        action="store_true",
        help=(
            "for interactive/static outputs, convert Cl2(g) half-reactions "
            "through an explicit Henry-law Cl2(g) <=> Cl2(aq) gas-liquid "
            "equilibrium"
        ),
    )
    parser.add_argument(
        "--static-po2-contours",
        action="store_true",
        help=(
            "overlay O2/H2O iso-pO2 contour lines on the static PNG/PDF exports"
        ),
    )
    parser.add_argument(
        "--static-po2-levels",
        type=parse_static_po2_levels,
        default=None,
        metavar="LOG_LEVELS",
        help=(
            "comma-separated log10(pO2/bar) contour levels for static exports; "
            "example: --static-po2-levels=-8,-6,-4,-2,0"
        ),
    )
    args = parser.parse_args()

    if args.static_po2_levels is None:
        args.static_po2_levels = list(STATIC_PO2_LOG10_LEVELS)
    else:
        args.static_po2_contours = True

    if args.static_po2_contours:
        args.static = True

    if not args.interactive_json and not args.static and not args.kinetic:
        args.interactive_json = True
        args.static = True
        args.kinetic = True

    return args

def main() -> None:
    args = parse_args()
    raw_half_reaction_payload = load_half_reaction_payload()
    interactive_payload = None

    with chlorine_model_context(explicit_cl2_gas=args.explicit_cl2_gas):
        if args.interactive_json:
            interactive_payload = generate_interactive_payload(
                raw_half_reaction_payload,
                explicit_cl2_gas=args.explicit_cl2_gas,
            )
            write_interactive_json(interactive_payload)

        if args.static:
            static_payload = interactive_payload or generate_interactive_payload(
                raw_half_reaction_payload,
                [STATIC_TEMPERATURE_C],
                explicit_cl2_gas=args.explicit_cl2_gas,
            )
            write_static_phase_diagram(
                static_payload,
                show_po2_contours=args.static_po2_contours,
                po2_log10_levels=args.static_po2_levels,
            )
            print(f"Wrote {STATIC_PNG_OUT.relative_to(ROOT)}")
            print(f"Wrote {STATIC_PDF_OUT.relative_to(ROOT)}")

    if args.kinetic:
        with chlorine_model_context(explicit_cl2_gas=False):
            write_kinetic_phase_diagram(raw_half_reaction_payload)
