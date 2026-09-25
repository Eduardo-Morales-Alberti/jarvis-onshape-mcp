---
name: drawing-to-onshape
description: End-to-end, timed - drawing image in designs/ -> sketches -> parametric FeatureScript feature in Onshape -> mass validated against the drawing, in the minimum number of turns. Use when the user asks to build / reproduce / time a design from its drawing. Orchestrates design-to-sketch and sketch-to-featurescript.
argument-hint: <drawing image, e.g. designs/SPEEDCADT3_4.jpg>
---

# drawing-to-onshape

> **Paths:** `<skills>` is this plugin's `skills/` directory, the parent of this
> skill's base directory (shown when the skill loads). Use the absolute path in
> commands. Part data (`designs/<part>/`, `designs/onshape.json`) lives in the
> user's working project, never in the plugin.

Wall-clock is dominated by model turns, not compute: the local build runs in
under 2 s and the Onshape calls take ~10 s. Every extra turn costs 5-15 s, and the
biggest single cost is writing `design.py`. So: few turns, everything
independent in the same turn, short design.py, never paste generated files.

The geometry rules live in `design-to-sketch/SKILL.md` (origin, patterns,
review) and the Onshape rules in `sketch-to-featurescript/SKILL.md`. This file
is only the turn plan.

## Turn plan (target: 5 turns)
1. **One turn, in parallel:**
   - Bash: `date +%s.%N > <scratchpad>/t0; mkdir -p designs/<part>; cp <image> designs/<part>/reference.<ext>`
   - Read the drawing image.
   - ToolSearch `select:` **all** the Onshape tools at once: `write_featurescript_feature`,
     `create_part_studio`, `eval_featurescript`, `describe_part_studio`, `update_feature`.
2. **Write `designs/<part>/design.py`** with `sketchgen.patterns` (`rays`, `ring`,
   `hole`, `arc_on`, `blend`/`blend_arc`, `offset_arc`, `profile`). Short docstrings,
   no analysis prose in the file. Put the reasoning in `analysis.md` only if the
   user asks for it or the drawing is ambiguous.
3. **One turn, in parallel:**
   - Bash: `python3 <skills>/sketch-to-featurescript/scripts/build.py designs/<part>`
   - `create_part_studio(<part>)` when `designs/<part>/onshape.json` has no `elementId`.
4. **Read `out/review.png`** only when the geometry is a new interpretation, in the
   same turn as the upload if the review is not needed first. The upload is
   `write_featurescript_feature` with the `call` fields from build.py
   (`featureScriptPath`, `parametersPath`, `postEvalScriptPath`, ids). Pass
   `featureScript: ""` if the tool schema still marks it as required. The response's
   `post_eval` is the verdict: `{"ok", "mass_g", "target_g", "delta_pct", "bodies"}`.
5. **Record and answer in the same turn:** `build.py record designs/<part> ...
   --post-eval '<post_eval json>' --t0 $(cat <scratchpad>/t0)`, then report the time
   and the mass.

If `post_eval.ok` is false or the status is ERROR, leave the fast path: follow the
"When it fails" table in `sketch-to-featurescript/SKILL.md`.

## Batch
Several drawings: do step 1 for all of them in one turn, write all the design.py
files in one turn (parallel Writes), then build all of them in one Bash, create the
missing Part Studios in parallel, and upload in parallel (each part has its own
Part Studio).

## Benchmarks (runs.jsonl `wall_clock_s`)
| date | part | turns | wall clock | note |
|---|---|---|---|---|
| 2026-09-25 | speedcad-t3-2 | 9 | 127 s | before this protocol; included an extra eval turn and one-off debugging |
| 2026-09-25 | speedcad-t3-4 | 5 | 53.9 s | this protocol, first try, post_eval ok (245.508 g); geometry already known in the session |
| 2026-09-25 | speedcad-t3-12 | 10 | 170.9 s | new feature type: included implementing revolve support + 1 failed upload (RevolveType enum), exact mass 433.187 g |
| 2026-09-25 | speedcad-t3-20 | 4 | 35.6 s | two sketches (Front + Right), first try, exact mass 195.436 g |
| 2026-09-25 | t4scad-05 | 6 | 87.4 s | new feature type: included implementing circular_pattern; first upload ok, exact mass 183.154 g |
| 2026-09-25 | t4scad-09 | 5 | 226 s | first try, +0.062 % (height 106 not dimensioned, read from the scale) |
| 2026-09-25 | t4scad-08 | +6 | 09+08 together, see runs.jsonl | offset planes + multi-seed pattern implemented; 1 compile error (LENGTH_BOUNDS clash); exact 101.396 g |
| 2026-09-25 | t4scad-19 | 5 | 126.6 s | first try, 7 sketches on 3 planes, no skill changes, exact 245.695 g |
