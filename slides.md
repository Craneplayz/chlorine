---
theme: ./theme
title: Chlorine Pourbaix Diagram
info: |
  Conceptual walkthrough of chlorine speciation across pH and redox potential.
layout: cover
background: /cover.jpg
backgroundSize: cover
class: cover-page text-left text-white
transition: fade-out
mdc: true
---

# Chlorine Pourbaix Diagram

**Koh Zhi Xiang**.

*Geobiology*. 
19, May 2026.

---
class: species-ladder
---

# Chlorine

Chlorine ($\mathrm{Cl}$) is a chemical element with atomic number 17. It is the second-lightest of the halogens and the $\mathrm{21}^{\text{st}}$ most abundant element in Earth's crust.

> <span class="text-lg"> **Electron configuration** $\quad [\mathrm{Ne}]\  3\mathrm{s}^2\ 3\mathrm{p}^5$ </span>

In aqueous solution, chlorine could have the following species:

| Name | Species | Oxidation state |
| --- | --- | ---: |
| Chloride | $\mathrm{Cl^-}$ | -1 |
| Chlorine | $\mathrm{Cl_2}$ | 0 |
| Hypochlorous acid | $\mathrm{HOCl}$ | +1 |
| Hypochlorite | $\mathrm{OCl^-}$ | +1 |
| Chlorate | $\mathrm{ClO_3^-}$ | +5 | 
| Perchlorate | $\mathrm{ClO_4^-}$ | +7 |

---

# Pourbaix Diagram

> <span class="text-lg"> **Nernst equation** <small>(1887)</small></span>

> $$E = E^\circ - \frac{RT}{nF}\ln Q=E^\circ - \frac{RT}{nF}\ln \frac{a_\text{Red}}{a_\text{ox}}$$

A **Pourbaix diagram** (also known as $E_\mathrm{H}$-$p\mathrm{H}$ phase diagram) maps the **thermodynamically favoured** species within an reaction system as a function of:

- $\mathrm{pH}$: Acid-base condition (acidic $\rightarrow$ alkaline)
- $E_\mathrm{H}$: Redox potential (reducing $\rightarrow$ oxidising)

In this project, we shall consider an aqueous solution reaction system with $\mathrm{Cl}$ and $\mathrm{H}$, $\mathrm{O}$ from $\mathrm{H_2O}$. Two parameters are given for each diagram

1. **Temperature** $T$ 
2. **Total concentration of chlorine atom** $[\mathrm{Cl}_\text{total}]$ (thereafter expressed in logarithm)

---
class: reaction-table
---
# Reactions

Standard electric potentials for half-reactions were retrieved from Lange (1999).

| No. | Half-reaction | $E^\circ$ / V |
|---: | --- | ---: |
| 1 | $\mathrm{ClO_4^- + 2H^+ + 2e^- \rightarrow ClO_3^- + H_2O}$ | 1.201 |
| 2 | $\mathrm{2ClO_4^- + 16H^+ + 14e^- \rightarrow Cl_2 + 8H_2O}$ | 1.392 |
| 3 | $\mathrm{ClO_4^- + 8H^+ + 8e^- \rightarrow Cl^- + 4H_2O}$ | 1.388 |
| 4 | $\mathrm{ClO_3^- + 2H^+ + e^- \rightarrow ClO_2(g) + H_2O}$ | 1.175 |
| 5 | $\mathrm{ClO_3^- + 3H^+ + 2e^- \rightarrow HClO_2 + H_2O}$ | 1.181 |
| 6 | $\mathrm{2ClO_3^- + 12H^+ + 10e^- \rightarrow Cl_2 + 6H_2O}$ | 1.468 |
| 7 | $\mathrm{ClO_3^- + 6H^+ + 6e^- \rightarrow Cl^- + 3H_2O}$ | 1.450 |
| 8 | $\mathrm{ClO_2(g) + H^+ + e^- \rightarrow HClO_2}$ | 1.188 |
| 9 | $\mathrm{HClO_2 + 2H^+ + 2e^- \rightarrow HClO + H_2O}$ | 1.640 |

---
class: reaction-table
---

# Reactions

| No. | Half-reaction | $E^\circ$ / V |
|---: | --- | ---: |
| 10 | $\mathrm{HClO_2 + 3H^+ + 4e^- \rightarrow Cl^- + 2H_2O}$ | 1.584 |
| 11 | $\mathrm{2HClO_2 + 6H^+ + 6e^- \rightarrow Cl_2(g) + 4H_2O}$ | 1.659 |
| \*12 | $\mathrm{2ClO^- + 2H_2O + 2e^- \rightarrow Cl_2(g) + 4OH^-}$ | 0.421 |
| \*13 | $\mathrm{ClO^- + H_2O + 2e^- \rightarrow Cl^- + 2OH^-}$ | 0.890 |
| 14 | $\mathrm{Cl_3^- + 2e^- \rightarrow 3Cl^-}$ | 1.415 |
| 15 | $\mathrm{Cl_2(aq) + 2e^- \rightarrow 2Cl^-}$ | 1.396 |

\* These two half-reactions were expressed in alkaline condition under $1\text{ mol NaOH}$.

---
---
# Drawing the Pourbaix diagram

The Pourbaix diagram was precalculated using `Python`.

1. Standard potentials of half reactions were read.
2. Express half reactions in alkaline conditions using $\mathrm{H}^+$ and $\mathrm{H}_2\mathrm{O}$. Shift their $E^\circ$ using $K_w$ to respect this change. 
3. Precompute across temperature $T$ and total chlorine $[\mathrm{Cl}_{\text{total}}]$.
4. Rasterise the diagram with grids. Then, solve the equation system defined by the reactions for each grid to obtain concentration of all species $\boldsymbol{\alpha}=(\alpha_1,\alpha_2, ...)$.
5. Mark the regions in the diagram with species of highest concentration $i = \arg\max_i \alpha_i$.
6. Determine the boundary by marching squares.
7. Export the interactive dataset; export static images only at $25 \degree \text{C}$ and $1 \text{ mM}$.

Utilise `Slidev` with `Vue.js` for interactive diagram. Results verified with the diagram in Takeno (2005).


---
---

# Main Diagram Walkthrough

<PourbaixDiagram />

---

# From Thermodynamics to Kinetics

A normal Pourbaix diagram asks which species is thermodynamically favoured at fixed pH and Eh.

A kinetically constrained diagram asks a different question:

$$
\text{dominant species}=\arg\max_i c_i(t;\mathrm{pH},E_h)
$$

Here, $\mathrm{Cl_2}$, $\mathrm{HOCl}$, and $\mathrm{OCl^-}$ are treated as fast-equilibrium species, while $\mathrm{ClO_3^-}$ and $\mathrm{ClO_4^-}$ accumulate through slow schematic kinetic steps.

---
class: kinetic-diagram-slide
---

# Kinetically Constrained Chlorine Eh-pH Diagram

<img class="rounded-xl h-115 dark:invert-100" src="/src/chlorine_kinetic_constrained.png" alt="Kinetically constrained chlorine Eh-pH diagram with one second, one hour, one day, and one year panels" />

<!-- Time-dependent kinetic phase map with -->
<!-- 
---

# Environmental Implications -->

---

# References

1. Lange, N. A. (1999). Lange’s Handbook of Chemistry (J. A. Dean, Ed.; 15th ed.). McGraw-Hill.
2. Takeno, N. (2005). Atlas of Eh-pH Diagrams: Intercomparison of Thermodynamic Databases (No. 419; pp. 1–285). Geological Survey of Japan.
3. Bard, A. J., Parsons, R., & Jordan, J. (1985). Standard Potentials in Aqueous Solution (1st ed). CRC Press.

