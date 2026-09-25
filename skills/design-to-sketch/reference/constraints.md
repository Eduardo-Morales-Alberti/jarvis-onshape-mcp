# Constraint catalog

Names match Onshape sketch constraints so the FeatureScript converter can map
them 1:1. `p` = point ref (`id.start|end|center`, or a `point` entity),
`c` = curve ref (line, arc or circle id). Residuals are in mm (degrees for
angles); `run.py` fails any residual >= 1e-6.

| type | refs | value | checked as |
|---|---|---|---|
| `COINCIDENT` | p, p | | distance between the points |
| `COINCIDENT` | p, c | | distance from the point to the curve (point on curve) |
| `CONCENTRIC` | c/p, c/p | | distance between centers |
| `TANGENT` | c, c | | line-circle: \|dist(center, line) - r\|; circle-circle: min(\|d - (r1+r2)\|, \|d - \|r1-r2\|\|) |
| `PARALLEL` | line, line | | angle between them (0 or 180) |
| `PERPENDICULAR` | line, line | | angle between them minus 90 |
| `EQUAL` | c, c | | line lengths or radii |
| `MIDPOINT` | p, line | | distance from p to the line's midpoint |
| `HORIZONTAL` / `VERTICAL` | line, or p, p | | dy / dx of the line or between the points |
| `FIX` | p | `[x, y]` | distance to the fixed position |
| `RADIUS` | arc/circle | r | radius |
| `DIAMETER` | arc/circle | d | 2 x radius |
| `LENGTH` | line | l | line length |
| `DISTANCE` | p, p | d | point-point distance |
| `DISTANCE` + `"direction": "horizontal"\|"vertical"` | p, p | d | \|dx\| or \|dy\| only: horizontal / vertical dimensions, dimension chains |
| `DISTANCE` | c, p | d | point to line / curve distance |
| `DISTANCE` | arc, arc (concentric) | d | radial gap between them |
| `DISTANCE` | line, line (parallel) | d | gap between them (e.g. hexagon across flats) |
| `ANGLE` | line, line | deg | unsigned angle, supplement accepted |

## Conventions

- **FeatureScript limits** (see `sketch-to-featurescript/reference/fs-mapping.md`):
  Onshape's `skSolve` ignores `ANGLE` and `MIDPOINT`. Use `ANGLE` only between
  two lines that share a vertex and both carry `LENGTH` (the converter rewrites
  it); express midpoints with `COINCIDENT` + `EQUAL` instead of `MIDPOINT`.

- **Center on a known point**: `COINCIDENT <arc>.center <point>`, the way
  Onshape does it. Use `CONCENTRIC` only between two curves.
- **Dimension as the drawing does**: if the drawing says `Ø30`, use
  `DIAMETER 30`, not `RADIUS 15`; if it gives a width `7` between concentric
  arcs, use `DISTANCE arc, arc = 7` instead of deriving `RADIUS 52`. The
  converter should reproduce the designer's intent, not our arithmetic.
- **Every junction** between two profile curves gets `COINCIDENT` on the shared
  endpoints (`Sketch.join`), plus `TANGENT` when the drawing shows a smooth
  blend.
- **Anchor**: every sketch has exactly one `FIX` (normally the origin), and
  all other geometry hangs off it through constraints.
- The checker verifies that the constraints hold for the stored coordinates.
  It does **not** count degrees of freedom; judge "fully defined" by reading
  the constraint list (the Onshape solver will report it in phase 2).
