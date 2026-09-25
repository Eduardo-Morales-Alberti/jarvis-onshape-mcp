"""SpeedCAD T4 exercise 8: triangular prism with a boss on each face (reference.jpg).

Origin: prism axis (world Y) at the centroid of the triangle, on the mid plane
(the 3 face features are a 3x pattern about that axis). Front plane = section.
  S1 Front      : equilateral triangle 30 with a window offset 5 inward, extruded
                  symmetric 30 (square 30x30 faces).
  S2 Top @-11.66: seed on the bottom face: 25x25 frame with a 20x20 hole, 3 thick.
  S3 Top @-14.66: seed: Ø16/Ø12 tube, 6 tall (up to the face).
  pattern x3 about Y, then S4 Front: Ø5 through each wall (3 revolve cuts about
  the face normals), from the tube bore into the window.
"""
import math

from sketchgen import Design, Params, Sketch
from sketchgen import patterns as pt

P = Params({
    "side": 30.0, "length": 30.0, "wall": 5.0,
    "plate": 25.0, "plate_hole": 20.0, "plate_t": 3.0,
    "tube_d": 16.0, "tube_bore": 12.0, "tube_h": 6.0, "hole_d": 5.0,
})
R_IN = P["side"] / (2 * math.sqrt(3))          # inradius: face distance from the axis
R_IN2 = R_IN - P["wall"]                       # window inradius


def origin(sk):
    sk.point("pO", (0, 0), construction=True)
    sk.constrain("FIX", "pO", value=(0, 0), note="origin: prism axis at the centroid")


def tri(r_in):
    """Equilateral triangle, flat side down at -r_in, apex up."""
    return [(-r_in * math.sqrt(3), -r_in), (r_in * math.sqrt(3), -r_in), (0.0, 2 * r_in)]


def square(h):
    return [(-h, -h), (h, -h), (h, h), (-h, h)]


def s1_prism():
    sk = Sketch("S1_prism", plane="Front", notes="Prism section with the window.")
    origin(sk)
    sk.line("vax", (0, -R_IN), (0, 2 * R_IN), construction=True)
    sk.constrain("VERTICAL", "vax")
    sk.constrain("COINCIDENT", "pO", "vax")
    outer = pt.polygon(sk, "t", tri(R_IN), "pO", vline="vax")
    inner = pt.polygon(sk, "w", tri(R_IN2), "pO", vline="vax")
    sk.region("prism", outer, holes=[inner],
              extrude={"height": P["length"], "op": "NEW", "end": "SYMMETRIC"})
    return sk


def s2_frame():
    sk = Sketch("S2_frame", plane="Top", offset=-(R_IN + P["plate_t"]), notes="Seed frame under the bottom face.")
    origin(sk)
    outer = pt.polygon(sk, "f", square(P["plate"] / 2), "pO")
    inner = pt.polygon(sk, "g", square(P["plate_hole"] / 2), "pO")
    sk.region("frame", outer, holes=[inner], extrude={"height": P["plate_t"], "op": "NEW"})
    return sk


def s3_tube():
    sk = Sketch("S3_tube", plane="Top", offset=-(R_IN + P["tube_h"]), notes="Seed tube under the bottom face.")
    origin(sk)
    pt.ring(sk, "tube", (0, 0), "pO", P["tube_d"], P["tube_bore"],
            extrude={"height": P["tube_h"], "op": "NEW"})
    return sk


def s4_holes():
    sk = Sketch("S4_holes", plane="Front", notes="Ø5 through each wall, revolved about the face normal.")
    origin(sk)
    r = P["hole_d"] / 2
    for k in range(3):
        a = math.radians(-90 + 120 * k)
        n, t = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
        at = lambda u, v: (u * n[0] + v * t[0], u * n[1] + v * t[1])
        ax = "ax%d" % k
        sk.line(ax, (0, 0), at(R_IN + 3, 0), construction=True)
        sk.constrain("COINCIDENT", ax + ".start", "pO")
        u0, u1 = R_IN2 - 1, R_IN + 1                   # from the window air into the bore air
        pts = [at(u0, 0), at(u1, 0), at(u1, r), at(u0, r)]
        loop = pt.polygon(sk, "h%d_" % k, pts, "pO", vline=ax if k == 0 else None)
        sk.region("hole%d" % k, loop, revolve={"axis": ax, "op": "REMOVE"})
    sk.constrain("VERTICAL", "ax0")
    return sk


def build():
    return Design(
        part="t4scad-08", parameters=P, sketches=[s1_prism(), s2_frame(), s3_tube(), s4_holes()],
        material={"name": "Steel", "density": 7850}, target_mass_g=101.39628,
        build=["S1_prism/prism",
               {"circular_pattern": {"steps": ["S2_frame/frame", "S3_tube/boss_tube"], "axis": "Y", "count": 3}},
               "S4_holes/hole0", "S4_holes/hole1", "S4_holes/hole2"],
        reference={"image": "reference.jpg", "px_per_mm": 293 / 30.0, "origin_px": (686, 424)},
        origin={"feature": "prism axis at the triangle centroid",
                "evidence": ["three identical face features at 120 deg about it", "30 triangle, 5 wall, 3/6 heights from the faces"]},
        notes=["Frame 25x25 with a 20x20 hole (hidden lines in the section), tube Ø16/Ø12 x6, Ø5 through the wall.",
               "Overlay: only S1/S4 (Front) map onto the section view."],
    )
