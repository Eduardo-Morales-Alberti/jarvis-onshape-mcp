"""SpeedCAD T4 exercise 9: claw with a pin (reference.jpg).

Origin: pin axis on the top face (body centered under the pin: 50 wide in X,
30 deep in Y at the top). World: front view = Front plane (X, Z), side view =
Right plane (Y, Z). Z = 0 is the top face, the body goes down.
  S1 Right : side profile = crescent. Top 30, back face 15 down, then R70 (center
             found from its two ends) down to the 6 tip; R80 (center 40 below the
             top, through both outer corners) back up. Extruded symmetric 50.
  S2 Front : V notch 40 deg leaving 6-wide prongs at the bottom, cut through all.
  S3 Front : pin half section (Ø10 x 10 neck, Ø20 x 8 head), revolved about Z.
Height 106 is not dimensioned: read from the drawing scale (50 wide = 228 px).
"""
import math

from sketchgen import Design, Params, Sketch
from sketchgen import geometry as g
from sketchgen import patterns as pt

P = Params({
    "width": 50.0, "top_depth": 30.0, "height": 106.0, "back_flat": 15.0,
    "r_outer": 80.0, "r_outer_down": 40.0, "r_inner": 70.0, "tip": 6.0,
    "notch_deg": 40.0, "neck_d": 10.0, "neck_h": 10.0, "head_d": 20.0, "head_h": 8.0,
})
D2, H = P["top_depth"] / 2, P["height"]


def origin(sk):
    sk.point("pO", (0, 0), construction=True)
    sk.constrain("FIX", "pO", value=(0, 0), note="origin: pin axis on the top face")


def s1_side():
    sk = Sketch("S1_side", plane="Right", notes="Crescent side profile (sketch x = world Y).")
    origin(sk)
    tl, tr = (-D2, 0.0), (D2, 0.0)
    back = (D2, -P["back_flat"])
    tip_in, tip_out = (D2, -H), (D2 - P["tip"], -H)
    c_in = max(g.circle_circle(back, P["r_inner"], tip_in, P["r_inner"]), key=lambda p: p[0])
    c_out = max(g.circle_circle(tl, P["r_outer"], tip_out, P["r_outer"]), key=lambda p: p[0])
    sk.line("top", tl, tr)
    sk.line("back", tr, back)
    pt.blend_arc(sk, "inner", c_in, P["r_inner"], back, tip_in)
    sk.line("tip", tip_in, tip_out)
    pt.blend_arc(sk, "outer", c_out, P["r_outer"], tip_out, tl)
    loop = pt.profile(sk, ["top", "back", "inner", "tip", "outer"], tangent=False)
    sk.constrain("HORIZONTAL", "top")
    sk.constrain("HORIZONTAL", "tip")
    sk.constrain("VERTICAL", "back")
    sk.constrain("COINCIDENT", "pO", "top")
    sk.constrain("DISTANCE", "pO", "top.start", value=D2, direction="horizontal")
    sk.constrain("DISTANCE", "pO", "top.end", value=D2, direction="horizontal")
    sk.constrain("DISTANCE", "pO", "back.end", value=P["back_flat"], direction="vertical")
    sk.constrain("DISTANCE", "pO", "tip.start", value=H, direction="vertical")
    sk.constrain("DISTANCE", "tip.start", "tip.end", value=P["tip"], direction="horizontal")
    sk.region("body", loop, extrude={"height": P["width"], "op": "NEW", "end": "SYMMETRIC"})
    return sk


def s2_notch():
    sk = Sketch("S2_notch", plane="Front", notes="V notch between the prongs.")
    origin(sk)
    sk.line("axis", (0, 0), (0, -H), construction=True)
    sk.constrain("VERTICAL", "axis")
    sk.constrain("COINCIDENT", "axis.start", "pO")
    half = math.radians(P["notch_deg"] / 2)
    hw = P["width"] / 2 - P["tip"]                       # notch half width at the bottom
    apex = -H + hw / math.tan(half)
    zlow = -H - 6
    wl = (apex - zlow) * math.tan(half)
    loop = pt.polygon(sk, "n", [(0, apex), (-wl, zlow), (wl, zlow)], "pO", vline="axis")
    sk.region("notch", loop, extrude={"op": "REMOVE", "end": "THROUGH_ALL"},
              note="extends 6 below the tips so the cut does not share the bottom face")
    return sk


def s3_pin():
    sk = Sketch("S3_pin", plane="Front", notes="Pin half section, revolved about Z.")
    origin(sk)
    zt = P["neck_h"] + P["head_h"]
    sk.line("axis", (0, 0), (0, zt), construction=True)
    sk.line("base", (0, 0), (P["head_d"] / 2, 0), construction=True)
    sk.constrain("VERTICAL", "axis")
    sk.constrain("HORIZONTAL", "base")
    sk.constrain("COINCIDENT", "axis.start", "pO")
    sk.constrain("COINCIDENT", "base.start", "pO")
    rn, rh = P["neck_d"] / 2, P["head_d"] / 2
    pts = [(0, -1.0), (rn, -1.0), (rn, P["neck_h"]), (rh, P["neck_h"]), (rh, zt), (0, zt)]
    loop = pt.polygon(sk, "q", pts, "pO", vline="axis", hline="base")
    sk.region("pin", loop, revolve={"axis": "axis", "op": "ADD"},
              note="starts 1 below the top face so it fuses with the body")
    return sk


def build():
    return Design(
        part="t4scad-09", parameters=P, sketches=[s1_side(), s2_notch(), s3_pin()],
        material={"name": "Steel", "density": 7850}, target_mass_g=886.40732,
        build=["S1_side/body", "S2_notch/notch", "S3_pin/pin"],
        reference={"image": "reference.jpg", "px_per_mm": 228 / 50.0, "origin_px": (636, 158)},
        origin={"feature": "pin axis on the top face", "evidence": ["pin centered on 50 and 30", "18, 15, 40 from the top face"]},
        notes=["Height 106 read from the scale, not dimensioned.",
               "R80 center: 40 below the top, through both outer corners; R70 center from its two ends."],
    )
