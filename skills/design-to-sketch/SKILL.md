---
name: design-to-sketch
description: Turn an engineering drawing image (designs/*.jpg|png) into parametric 2D sketches (lines, arcs, circles, tangencies, Onshape-named constraints) plus a sketches.json hand-off file and SVG/PNG overlays on the reference. Use when the user passes a design/drawing and asks to extract its geometry or sketches. Produces geometry only; it does not talk to Onshape or generate FeatureScript.
argument-hint: <path to drawing image>
---

# design-to-sketch

> **Paths:** `<skills>` is this plugin's `skills/` directory, the parent of this
> skill's base directory (shown when the skill loads). Use the absolute path in
> commands. Part data (`designs/<part>/`, `designs/onshape.json`) lives in the
> user's working project, never in the plugin.

Input: a drawing image. Output, in `designs/<part>/`:

```
reference.<ext>       copy of the input image
analysis.md           dimension table, views, heights, decisions, open questions
design.py             single parameter table + sketch construction (sketchgen)
out/sketches.json     hand-off contract (reference/json-schema.md)
out/S*.svg|png        one overlay per sketch, out/all.* with everything
```

A later skill converts `sketches.json` to FeatureScript. Do not call Onshape,
MCP plugins, or compute mass/volume here: the goal is to prove the geometry is
understood and constrained correctly.

Tools: `scripts/run.py` (stdlib Python 3) and the `scripts/sketchgen` package.
Headless Chrome + ffmpeg rasterize the overlays when available.

## Workflow
Speed rules: run independent tool calls in the same turn (e.g. copy the image while
reading it, build while creating the Part Studio); one `review.png` read per iteration;
`--quiet` output. `run.py` takes well under 2 s including the review image.


### 1. Set up
- Pick a kebab-case part name. Create `designs/<part>/` and copy the image in
  as `reference.<ext>` (copy, never move the user's file).
- If `designs/<part>/` already exists, read its `analysis.md` and `design.py`
  first and iterate on them instead of starting over.

### 2. Read the drawing -> `analysis.md`
Look at the image (Read it) and write down, before any code:
- **Views** present (top/front/right/iso) and how their axes map to the model.
  Aligned orthographic views share coordinates: use that to cross-check.
- **Dimension table**: every callout with its value and `source`
  (`callout`, `derived`, `inferred`). Note repeated callouts (`R45 x3`).
- **Origin (datum)**: find it with the procedure below, before anything else.
- **Topology in words**: which curves bound each profile, where they are
  tangent, where they just intersect, which features are concentric.
- **Heights / depths** from the side views, per region. In a side view the
  dimensions running *across* the view (horizontal in a right view) are the
  heights: read every one of them, including the small ones near the edges.
  Measure each callout against the pixels of the side view: a thin slab that
  runs the full width is the plate, and its small callout (e.g. `5`) is the
  plate thickness. A callout spanning the whole stack (e.g. `15`) is a total
  height from the base face, not a height above the plate.
- **Account for every number on the sheet.** List every callout you can read,
  then assign each one to a feature. A number with no feature means you missed
  a feature: go back to the image, don't drop the number. Simplifying the
  geometry to make a callout go away is not allowed.
- **Open questions**. If a value that changes the geometry is ambiguous, stop
  and ask the user before writing `design.py`.

#### Finding the origin
The origin goes on the **center of the main feature** of the part. That is the
convention the user validated on three drawings, and it holds even when
another point carries more dimensions.
1. List the candidate points: circle/arc centers and hexagon/polygon centers.
2. The **main feature** is the one that:
   - is the largest circle / boss (usually also the tallest in the side view);
   - has the long center lines crossing the whole part;
   - is where dimension chains end or start (e.g. `25 -> 10 -> 10` ending on it).
   Its center is the origin.
3. Confirm it by counting the dimensions that start or pivot on each
   candidate (vertex of an angular dimension, start of linear / aligned /
   polar dimensions, concentric radii and diameters). The count **breaks
   ties** between similar candidates. It does **not** override the main
   feature: a small hole with many chained dimensions is still not the origin.
4. Keep the drawing's orientation: the view's right is +X, up is +Y. Don't
   rotate or mirror. The first skeleton line from the origin gets
   `HORIZONTAL`/`VERTICAL` if the drawing shows it that way, and the rest follow
   by the drawn angles.
5. **Height (Z) datum**: if the side view is symmetric about a mid plane
   (every layer centered on the same line), put the sketches on the mid plane
   and use `end: "SYMMETRIC"` extrude hints with the full thickness as
   `height`. Otherwise sketch on the base face and extrude `BLIND` upward.
6. Record it in `analysis.md` (candidate table with the reason) and in
   `Design(origin={"feature": ..., "evidence": [...]})` (required).

Validated examples:
| design | origin | note |
|---|---|---|
| `speedcad-t3-2` | center of the Ø50 boss | also the vertex of `60°` and the start of both `60` |
| `speedcad-t3-4` | center of the Ø45 boss / hexagon | also the vertex of `145°` and the start of both `50` |
| `speedcad-t3-8` | center of the Ø15 boss | the central Ø10 carries more dimensions (25, 10, 15, 15), but Ø15 is the main boss; Z datum = mid plane |

Common drawing patterns:
| on the drawing | geometry |
|---|---|
| `R` arc blending two circles, curving inward | arc tangent externally to both: `tangent_arc_center(..., external=True, away_from=<centroid of the part>)` |
| `R` arc wrapping around two circles | `external=False`, `away_from=` the side it bulges toward |
| a width callout (e.g. `7`) between an `R` arc and a second parallel curve | band: second arc **concentric** with the first, offset by the width (`DISTANCE arc, arc = w`); it usually just intersects the neighbouring circles instead of being tangent |
| `R` callout on the outline around a hole (`Ø10` + `R15`) | a **lobe**: outline arc concentric with the hole. The hole is never part of the outer loop; it goes in `holes` |
| straight edge running from one round lobe to another | line tangent to both: `tangent_line(c1, r1, c2, r2, side=±1)` (+1 = left of c1->c2), then `TANGENT` to each arc |
| concave `R` fillet between a lobe and a convex arc | center from `circle_circle(c1, r1 + R, c2, r2 + R)`; pick the root explicitly by side, with the cross product against the line c1->c2 (see `fillet_center` in `<skills>/design-to-sketch/examples/speedcad-t3-4/design.py`). `away_from=centroid` only works when the part is symmetric around that line |
| leader line that crosses the part to reach a curve | the callout belongs to the curve at the arrow tip, not the one nearest the text |
| hexagon / polygon with an across-flats callout | `regular_polygon(center, 6, across_flats=s, first_vertex_deg=90)` (90 = pointy top, flats vertical); lines + `EQUAL`, corners `COINCIDENT`, one flat `VERTICAL`, `DISTANCE` flat-flat = s, construction circumcircle concentric with the origin |
| two circles sharing a center mark | `CONCENTRIC`, bore = hole region, extrude REMOVE |
| stepped outline in a side view | one sketch/region per height level |

### 3. Decompose into sketches
- One sketch per extrusion profile (per height level), plus one for holes if
  they are not already in a profile sketch. Order them in build order.
- Every sketch is self-contained: repeat the construction skeleton (the lines
  carrying key centers) as `construction` geometry in each sketch.
- Compute derived points with `sketchgen.geometry`, never by eye:
  - arc of radius R tangent to two circles: `tangent_arc_center(c1, r1, c2, r2, R, external=True|False, away_from=...)`
    (external: |P-Ci| = R + ri, the arc sits outside both; internal: R - ri);
  - tangent point: `tangent_point(ci, ri, P)`;
  - intersections: `circle_circle(...)`, pick the right root explicitly.
- Dimension like the drawing does (see `reference/constraints.md`): `DIAMETER`
  for Ø callouts, `DISTANCE` for widths between concentric arcs, and so on.

### 4. Write `design.py`
Use `sketchgen.patterns` for the recurring pieces, so the file states the drawing
and not the bookkeeping (`<skills>/design-to-sketch/examples/speedcad-t3-2/design.py` is the reference):
`hole`, `ring` (boss + bore + regions), `arc_on` (arc of a known circle),
`blend` / `blend_arc` (R tangent to two circles), `offset_arc` (concentric band,
DISTANCE = width), `profile` (closes a loop with COINCIDENT + TANGENT), `rays`
(skeleton of rays from the origin), `polygon` (half sections of turned parts: every
vertex dimensioned from the axis/base; pair with `revolve={"axis": ..., "op": ...}`
on the region, see `<skills>/design-to-sketch/examples/speedcad-t3-12/design.py`). Repeated features around an
axis (spokes, arms, bolt circles): model ONE instance as a NEW seed body and add a
`circular_pattern` step to `build` (see `<skills>/design-to-sketch/examples/t4scad-05/design.py`).
Keep entity ids stable across edits: FeatureScript updates in place by id.

Shape (see `<skills>/design-to-sketch/examples/speedcad-t3-2/design.py` for a full example):

```python
from sketchgen import Design, Params, Sketch
from sketchgen import geometry as g

P = Params({...})              # the ONLY place numbers from the drawing live;
                               # value=P["x"] keeps the name for FeatureScript inputs

def s1_something():
    sk = Sketch("S1_something", plane="Top", notes="...")
    sk.line(...); sk.circle(...); sk.arc(...)      # arc: ccw start->end
    sk.arc_short(id, center, r, p, q)              # short way between p and q
    sk.constrain("DIAMETER", "A_out", value=P["A_d"])
    sk.join("f_A", "f_RAB", tangent=True)          # COINCIDENT on shared ends (+TANGENT)
    sk.region("footprint", [...loop ids...], holes=[[...]],
              extrude={"height": 10, "op": "NEW"})  # or op REMOVE, end THROUGH_ALL
    return sk

def build():
    return Design(part="<part>", parameters=P, sketches=[...],
                  reference={"image": "reference.jpg",
                             "px_per_mm": ..., "origin_px": (x, y)},
                  origin={"feature": ..., "evidence": [...]},
                  material={"name": "Steel", "density": 7850},  # if known / assumed
                  target_mass_g=...,                            # mass printed on the sheet
                  build=["S2_x/base", "S1_y/boss", "S1_y/bore"],  # feature order: NEW first, cuts last
                  notes=["heights ...", "build order ...", "hypotheses ..."])
```

**Overlay calibration**: `origin_px` is the pixel of the model origin in the
image; `px_per_mm` comes from two points a known distance apart (for example
two hole centers 60 mm apart: pixel distance / 60). Estimate both from the
image, then refine them until the circles sit on the drawing. The largest
clean circle gives the best fit: its pixel bounding box gives both the
center (`origin_px` when it is the datum) and the scale (width / diameter).
Calibration only moves the picture: never change geometry to fix it.

### 5. Run and check
```
python3 <skills>/design-to-sketch/scripts/run.py designs/<part>/design.py --review --quiet
```
It prints every constraint with its residual, validates the structure (refs
exist, loops close, no construction geometry in regions, hints complete, each
region has an interior point and is not crossed by other curves of its sketch),
writes `out/`, and exits non-zero on any failure. Fix every failure.

Residuals only prove internal consistency. **The overlay is the real test**:
- Read **`out/review.png` once**: the full overlay on top, then a zoom tile on every
  junction between profile curves (`~` tangent, `/` plain coincident), computed from
  the model. Every curve must sit on its drawing line in the overlay and in every tile.
- Only if something needs a closer look: `--png` renders every sketch (in parallel),
  `--crop xmin,ymin,xmax,ymax --zoom 4 --tag zoom_<name> --png` a custom zoom (mm).
- **Hard checks on the filled regions** (any failure means the reading is wrong):
  - the outer edge of each profile fill is the outermost drawn contour, with
    no drawing line visible outside it;
  - holes show as white islands *inside* the fill, never as a notch in its edge;
  - the fill never crosses a drawn line.
  Don't report "matches" until you have checked these on `all.png` and on a
  zoom of every junction.
- Look for **drawing lines with no curve on top** (neck outlines, inner
  edges, steps). Each one is a missed feature, not noise.
- If a curve is off, the interpretation is wrong (tangent vs intersecting,
  which root, which radius). Fix `design.py` and write the correction in
  `analysis.md`; never nudge coordinates to make it fit.

### 6. Hand over
Report to the user: the sketches and what each one is for, the key derived
points (arc centers, tangent points), the hypotheses confirmed on the overlay,
and any open questions. Point them at `out/all.svg` (open it in a browser;
hover shows entity ids). The user validates before anything moves to the
FeatureScript phase.

## Rules
- Never edit `out/` by hand; it is regenerated by `run.py`.
- Keep `sketches.json` within the `sketchgen/1` contract
  (`reference/json-schema.md`). Extend the library, not the output, when you
  need a new entity or constraint type, and document it in both reference files.
- Lengths in mm, angles in degrees in the JSON (radians only inside `geometry.py`).
