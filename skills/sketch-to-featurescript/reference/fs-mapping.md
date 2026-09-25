# sketches.json → FeatureScript mapping (verified)

Verified in Onshape (FS 2909 prelude, library 3083) with `scripts/probe.fs`,
the angle probes and the speedcad-t3-2 build (2026-09-25). "Verified" means
the solved geometry was measured (volumes, `eval_featurescript` positions),
not just that the feature regenerated.

## Entities
| JSON | FeatureScript |
|---|---|
| point | `skPoint(s, id, { "position" : vector(x, y) * mm })` |
| line | `skLineSegment(s, id, { "start", "end", "construction" })` |
| circle | `skCircle(s, id, { "center", "radius", "construction" })` |
| arc | `skArc(s, id, { "start", "mid", "end", "construction" })` |

Refs are the same strings as in the JSON: `id`, `id.start`, `id.end`, `id.center`.

## Constraints
`skConstraint(s, cid, { "constraintType" : ConstraintType.X, "localFirst" : r1, "localSecond" : r2, ... })`

| type | extra keys | status |
|---|---|---|
| COINCIDENT (point-point, point-curve) | | verified |
| CONCENTRIC | | verified |
| TANGENT (line-arc, arc-arc) | | verified |
| PARALLEL, HORIZONTAL, VERTICAL (lines) | | verified |
| EQUAL (radii) | | verified |
| FIX (point) | none: freezes the seed position | verified |
| RADIUS, DIAMETER, LENGTH | `"length"` | verified |
| DISTANCE point-point | `"length"`, optional `"direction" : DimensionDirection.HORIZONTAL/VERTICAL` | verified |
| DISTANCE between concentric arcs | `"length"` | verified (t3-2 arm width) |
| PERPENDICULAR | | accepted, not measured |
| **ANGLE** | `"angle"` | **ignored by skSolve** (every key variant tried). The generator rewrites it as a DISTANCE between the free ends of two lines that share a vertex and both have LENGTH: √(a² + b² − 2ab·cos θ) as a live expression. Other ANGLE uses are rejected. |
| **MIDPOINT** | | **ignored by skSolve**. The generator rejects it. |
| HORIZONTAL/VERTICAL between two points | | not verified yet (first use: speedcad-t3-8) |
| DISTANCE between parallel lines | `"length"` | verified (t3-4 hexagon across flats, exact mass) |

Parametric values: a constraint with `param` uses `definition.<param>`; the
feature exposes one input per parameter with bounds whose default is the
drawing value.

## Regions → faces
Sketch edges (wire body) and region-face edges are **separate topology**:
`qAdjacent` from a sketch edge to a region face returns nothing. The
generator's `regionFace` lambda picks, among `qSketchRegion(sketchId, false)`,
the single face whose boundary passes through the midpoint of every curve of
the region (`evEdgeTangentLine(..., 0.5)`, `evDistance` < 1e-7 m) and has
exactly that many edges. It follows the solved geometry, so it survives
parameter changes (a static `inside_point` did not). It must be a lambda
inside the feature body: a top-level helper function failed to resolve.

## Extrudes
std `extrude(context, id + "...", {...})` from inside the custom feature:
- `"operationType" : NewBodyOperationType.NEW | ADD | REMOVE`, and `"defaultScope" : true` for ADD/REMOVE;
- `"endBound" : BoundingType.BLIND`, `"depth"`; `"symmetric" : true` for SYMMETRIC (full thickness);
- REMOVE THROUGH_ALL: `"endBound" : BoundingType.THROUGH_ALL, "symmetric" : true` (cuts both ways).

## Sketch planes
Top, Front (normal -Y, sketch x = X, y = Z) and Right (normal +X, sketch x = Y, y = Z)
are all verified: Front on t3-12 and t3-20, Right on t3-20 (fork slot, exact mass).

Sketch `offset` moves the plane along its normal: `plane(normal * offset, normal, x)`.
Verified on t4scad-08 (frame and tube sketched under the prism face).

Parameter bounds are named `PB_<param>`: a parameter called `length` produced
`LENGTH_BOUNDS`, which clashes with the std library and fails to compile silently
(empty feature spec).

## Revolves
std `revolve(context, id + "...", { "entities" : face, "axis" : sketchEntityQuery(id + sketch, EntityType.EDGE, axisLine), "operationType" : ..., "defaultScope" : true })`.
- Construction lines ARE queryable as edges (verified), so the axis is a line of the
  same sketch and follows the parameters.
- Default is a full turn. `RevolveType` is **not exported** by `onshape/std/geometry.fs`
  ("Variable RevolveType not found"): the generator omits it and refuses partial angles.
- Verified on speedcad-t3-12 (two revolves, NEW + ADD, exact mass 433.187 g).

## Circular pattern
`opPattern(context, id + "pNN", { "entities" : seedSolids, "transforms" : [rotationAround(line(origin, axis), k * step) ...], "instanceNames" : [...] })`
then `opBoolean(... BooleanOperationType.UNION)` over all solids created by the feature.
The seeds are all bodies created by the group's steps (qUnion of their qCreatedBy); an ADD
step merges through `defaultScope` into whatever it touches, so pieces that would touch the
main body instead of the seed must be NEW. Verified on t4scad-05 (5 arms + eyes, exact mass).

## Material
`setProperty(context, { "entities" : qCreatedBy(id, EntityType.BODY), "propertyType" : PropertyType.MATERIAL, "value" : material("Steel", 7850 * kilogram / meter ^ 3) })`: the mass shows up in mass properties.

## Self-validation (end of every generated feature)
`evVolume` of `qBodyType(qCreatedBy(id, EntityType.BODY), BodyType.SOLID)` × density
→ grams, compared with `target_mass_g`; body count. `reportFeatureInfo` ("VALIDATION OK: ...")
or `reportFeatureWarning` ("VALIDATION FAILED: ...", |delta| > 0.5 % or bodies != 1),
so the upload response itself carries the verdict. Gated by the `validateMass` input.
The upload verdict comes from `postEvalScriptPath` (out/validate.fs): verified live on speedcad-t3-4 (245.508 g).

## Upload without pasting the source (plugin, branch fb/oauth)
`write_featurescript_feature` accepts `featureScriptPath` + `parametersPath`
(files read by the MCP server), `fsElementId` (reuse the Feature Studio) and
`featureId` (update the instance in place). Needs the MCP server restarted after
the plugin change.
