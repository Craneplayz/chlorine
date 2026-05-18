from __future__ import annotations

import argparse

from .chemistry import load_half_reaction_payload
from .config import ROOT, STATIC_PDF_OUT, STATIC_PNG_OUT, STATIC_TEMPERATURE_C
from .generation import generate_interactive_payload, write_interactive_json
from .kinetics import write_kinetic_phase_diagram
from .plot import write_static_phase_diagram


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
    args = parser.parse_args()

    if not args.interactive_json and not args.static and not args.kinetic:
        args.interactive_json = True
        args.static = True
        args.kinetic = True

    return args

def main() -> None:
    args = parse_args()
    raw_half_reaction_payload = load_half_reaction_payload()
    interactive_payload = None

    if args.interactive_json:
        interactive_payload = generate_interactive_payload(raw_half_reaction_payload)
        write_interactive_json(interactive_payload)

    if args.static:
        static_payload = interactive_payload or generate_interactive_payload(
            raw_half_reaction_payload,
            [STATIC_TEMPERATURE_C],
        )
        write_static_phase_diagram(static_payload)
        print(f"Wrote {STATIC_PNG_OUT.relative_to(ROOT)}")
        print(f"Wrote {STATIC_PDF_OUT.relative_to(ROOT)}")

    if args.kinetic:
        write_kinetic_phase_diagram(raw_half_reaction_payload)
