# Example designs

`design.py` files of parts reproduced end to end with this pipeline (exact mass in
Onshape). They are references for `sketchgen` usage: skeletons, `patterns`, revolves,
circular patterns, offset planes, multi-plane sketches.

The drawings they come from (SpeedCAD exercises) are not included: they belong to their
authors. Without `reference.jpg` next to them, `run.py` cannot draw the overlay, but the
model builds, validates and generates FeatureScript (see `tests/skills/`).

| example | shows |
|---|---|
| speedcad-t3-2 | tangent blends between circles, concentric offset band, ANGLE rewrite |
| speedcad-t3-4 | tangent lines, concave fillet root by side, hexagon |
| speedcad-t3-12 | half sections revolved about two different axes |
| speedcad-t3-20 | two planes (Front + Right), arc through a point tangent to a circle |
| t4scad-05 | circular pattern of a seed body |
| t4scad-08 | offset sketch planes, multi-seed pattern, revolve cuts on rotated axes |
| t4scad-09 | crescent side profile from arcs defined by points, V notch, pin revolve |
| t4scad-19 | seven sketches on three planes, through cuts |
