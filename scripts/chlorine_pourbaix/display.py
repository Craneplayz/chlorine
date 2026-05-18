from __future__ import annotations

import re

from .config import DISPLAY_ARROW


def normalize_reaction_arrow(text: str) -> str:
    return text.replace("->", DISPLAY_ARROW)


MATPLOTLIB_FORMULA_PATTERN = re.compile(
    r"(?<![A-Za-z])(\d*(?:[A-Z][a-z]?\d*)+(?:\([a-z]+\))?[+-]?|\d*e[+-])"
)


def formula_token_to_mathtext(match: re.Match[str]) -> str:
    token = match.group(0)
    coefficient_match = re.match(r"^(\d+)(e[+-]|[A-Z].*)$", token)
    coefficient = ""
    formula = token
    if coefficient_match:
        coefficient = coefficient_match.group(1)
        formula = coefficient_match.group(2)

    if formula.startswith("e") and formula[-1] in "+-":
        return f"${coefficient}\\mathrm{{e}}^{{{formula[-1]}}}$"

    phase = ""
    phase_match = re.search(r"(\([a-z]+\))$", formula)
    if phase_match:
        phase = phase_match.group(1)
        formula = formula[: -len(phase)]

    charge = ""
    if formula.endswith(("+", "-")):
        charge = formula[-1]
        formula = formula[:-1]

    parts = []
    index = 0
    while index < len(formula):
        element_match = re.match(r"[A-Z][a-z]?", formula[index:])
        if not element_match:
            parts.append(re.escape(formula[index]))
            index += 1
            continue

        element = element_match.group(0)
        index += len(element)
        digit_start = index
        while index < len(formula) and formula[index].isdigit():
            index += 1
        digits = formula[digit_start:index]

        parts.append(f"\\mathrm{{{element}}}")
        if digits:
            parts.append(f"_{{{digits}}}")

    if phase:
        parts.append(f"\\mathrm{{{phase}}}")
    if charge:
        parts.append(f"^{{{charge}}}")

    return f"${coefficient}{''.join(parts)}$"

def matplotlib_chemical_text(text: str) -> str:
    return MATPLOTLIB_FORMULA_PATTERN.sub(
        formula_token_to_mathtext,
        normalize_reaction_arrow(text),
    )
