---
name: sketch-to-featurescript
description: Turn a validated designs/<part>/out/sketches.json (from design-to-sketch) into one parametric Onshape FeatureScript custom feature, upload it with the Onshape plugin into the user's document, and accept it only when the mass matches the drawing. Use when the user asks to reproduce / build / transcribe a design in Onshape after its sketches exist.
argument-hint: <part name, e.g. speedcad-t3-2>
---

# sketch-to-featurescript

> **Paths:** `<skills>` is this plugin's `skills/` directory, the parent of this
> skill's base directory (shown when the skill loads). Use the absolute path in
> commands. Part data (`designs/<part>/`, `designs/onshape.json`) lives in the
> user's working project, never in the plugin.

Input: `designs/<part>/out/sketches.json` (schema `sketchgen/1`, with `build`,
`material`, `target_mass_g`). Output: one custom feature per part in the
Onshape document recorded in `designs/onshape.json`, one Part Studio per part.

The `.fs` is **generated**, never written by hand: when something is wrong,
fix `design.py` / sketches.json (design-to-sketch) or `scripts/json_to_fs.py`,
then regenerate. API shapes and known Onshape quirks are in
`reference/fs-mapping.md`; read it before touching the generator.

## Fast path (target: under 60 s from an existing design.py)
Two turns. Run independent calls in the same turn.

**Turn 1** (Bash):
```
python3 <skills>/sketch-to-featurescript/scripts/build.py designs/<part>
```
It runs design-to-sketch (`--review`) and the generator in about 1.5 s and prints
`{"call": {...}, "needs_part_studio": bool, "review": ".../review.png", "t0": ...}`.
If `needs_part_studio` is true, call `create_part_studio(name=<part>)` **in the same turn**
(it does not depend on the build). If the drawing interpretation changed, Read `review.png`
(one image: overlay + a zoom on every junction).

**Turn 2**: `write_featurescript_feature` with the `call` fields as they come
(`featureScriptPath`, `parametersPath`, `featureName`, `fsElementName`, plus
`elementId` / `fsElementId` / `featureId` when present). Never paste the source.
The response's `post_eval` is the verdict, computed by `out/validate.fs` right after
the regen: `{"ok", "mass_g", "target_g", "delta_pct", "bodies"}` (ok = |delta| <= 0.5 % and
one body). The feature also reports it as an INFO/WARNING notice in Onshape, but the
plugin only returns the enum, so `post_eval` is what to read. Record it (Bash, in the
same turn as the answer):
```
python3 <skills>/sketch-to-featurescript/scripts/build.py record designs/<part> \
  --element <elementId> --fs-element <fs_element_id> --feature <feature_id> \
  --status <status> --post-eval '<post_eval json>' --t0 <t0>
```
It saves the ids in `designs/<part>/onshape.json`, so the next run **updates the same
feature in place** (no new elements, nothing to clean up), and appends `runs.jsonl`
with `wall_clock_s` and the mass.

`describe_part_studio` is only for diagnosing a failure; it is not part of the fast path.

## Details
- Ids: document in `designs/onshape.json` (the user's document: never touch pre-existing
  elements), part in `designs/<part>/onshape.json`. Never delete features, elements or
  documents without asking the user.
- `validateMass` input (default true): untick it when exploring parameters, so the
  mass check does not warn on purpose-made changes.
- **Parametric check** (on first build of a part, not every run): change one driving
  input with `update_feature`, confirm OK, one body, consistent geometry in every sketch
  (solved points via `eval_featurescript` + `sketchEntityQuery`), then restore it.
- The `.fs` is generated, never hand-written: fix design.py or `json_to_fs.py` and rebuild.

## When it fails
| symptom | cause / action |
|---|---|
| compile error, `Function X not found` | helper defined at top level: keep helpers as lambdas in the body |
| `region X matched N faces` | region crossed by another curve, or a loop entity not fully on the region boundary: fix the JSON regions |
| mass off, geometry looks right | heights / material assumption: ask the user, never tweak geometry to hit the mass |
| geometry moves wrongly when a parameter changes | a constraint is ignored by skSolve (ANGLE, MIDPOINT): check fs-mapping, extend the generator's rewrite |
| SKETCH_SOLVE_FAILED | regenerate with `--constraints geometric` (no dimensions), then bisect by constraint id |

Debug flags: `--constraints full|geometric|none`, `--only S1,S2`,
`--no-build` (sketches only), `--select point` (static inside_point).

## Validated
| part | result |
|---|---|
| speedcad-t3-2 | 113 599.2 mm³ → 891.754 g (target 891.754 g); `side` 60 → 65 regenerates consistently (ids in `designs/speedcad-t3-2/onshape.json`) |
