# Chlorine Pourbaix Slidev Deck

Slidev presentation using the Seriph theme.

## Commands

```bash
npm install
npm run precompute
python3 scripts/chlorine.py --interactive-json
python3 scripts/chlorine.py --static
python3 scripts/chlorine.py --static --static-po2-contours
python3 scripts/chlorine.py --static --static-po2-levels=-8,-6,-4,-2,0
python3 scripts/chlorine.py --kinetic
python3 scripts/chlorine.py --interactive-json --static --explicit-cl2-gas
npm run dev -- --port 3030
```

The deck uses a hybrid workflow:

- Python reads half-reaction constants from `data/chlorine_half_reactions.json` and precomputes teaching-scale Pourbaix boundary data into `data/chlorine_pourbaix.json`.
- The interactive JSON covers total chlorine from `log10 C = -6..0` and temperature from `0..100 C` in `2.5 C` steps. The static PNG/PDF exports remain fixed at `25 C` and `1 mM`.
- Add `--explicit-cl2-gas` to interactive/static generation to convert `Cl2(g)` half-reactions through the explicit Henry-law equilibrium `Cl2(g) ⇌ Cl2(aq)`.
- Add `--static-po2-contours` to overlay O2/H2O iso-pO2 lines on the static PNG/PDF; customize the log10(pO2/bar) levels with `--static-po2-levels=-8,-6,-4,-2,0`.
- The kinetic export writes `assets/chlorine_kinetic_constrained.png`, `assets/chlorine_kinetic_constrained.pdf`, and `data/chlorine_kinetic_model.json`. This is a schematic kinetically constrained Eh-pH diagram, not a true equilibrium Pourbaix diagram.
- Vue components handle sliders, toggles, hover states, and display interpolation.

The thermodynamic values in the half-reaction JSON are schematic defaults for presentation design. The kinetic rate parameters are also schematic teaching values. Replace both with database-derived constants or calibrated rate laws before using the diagrams as quantitative geochemical evidence.
