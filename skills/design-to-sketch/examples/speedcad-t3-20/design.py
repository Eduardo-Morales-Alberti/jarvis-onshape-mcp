"""SpeedCAD T3 exercise 20: two-lobe key with a forked shank (reference.jpg).

Origin: bottom end of the shank on the symmetry axis (70, 40 and 32 measured
from there; symmetric part). Two sketches on two planes:
  S1 Front: lobes R13 around Ø15 (40 apart, Z=70), concave R20 on top (tangent
     to both), concave R20 each side (tangent to the lobe, through the 15-wide
     shoulder corner at Z=40), step to the 8-wide shank. Extruded symmetric 15.
  S2 Right: fork slot 7.5 wide from below the base up to Z=32 (8 under the
     shoulder), cut through all.
"""
from sketchgen import Design, Params, Sketch
from sketchgen import geometry as g
from sketchgen import patterns as pt

P = Params({
    "hole_d": 15.0, "lobe_R": 13.0, "hole_dx": 40.0, "hole_z": 70.0,
    "top_R": 20.0, "side_R": 20.0, "shoulder_w": 15.0, "shoulder_z": 40.0,
    "shank_w": 8.0, "thick": 15.0, "slot_w": 7.5, "slot_gap": 8.0,
})
CL, CR = (-P["hole_dx"] / 2, P["hole_z"]), (P["hole_dx"] / 2, P["hole_z"])
XS, XK, ZS = P["shoulder_w"] / 2, P["shank_w"] / 2, P["shoulder_z"]


def side_arc_center(c, corner, outward):
    """R20 tangent (externally) to the lobe and through the shoulder corner."""
    sols = g.circle_circle(corner, P["side_R"], c, P["side_R"] + P["lobe_R"])
    return max(sols, key=lambda p: outward * p[0])


def s1_profile():
    sk = Sketch("S1_profile", plane="Front", notes="Key outline + Ø15 holes, 15 thick symmetric.")
    sk.point("pO", (0, 0), construction=True)
    sk.constrain("FIX", "pO", value=(0, 0), note="origin: shank end on the axis")
    for pid, c in (("pL", CL), ("pR", CR)):
        sk.point(pid, c, construction=True)
        sk.constrain("DISTANCE", "pO", pid, value=abs(c[0]), direction="horizontal")
        sk.constrain("DISTANCE", "pO", pid, value=P["hole_z"], direction="vertical")
    T, tL, tR = pt.blend(CL, P["lobe_R"], CR, P["lobe_R"], P["top_R"], away_from=(0, 0))
    FR = side_arc_center(CR, (XS, ZS), +1)
    FL = side_arc_center(CL, (-XS, ZS), -1)
    sR, sL = g.tangent_point(CR, P["lobe_R"], FR), g.tangent_point(CL, P["lobe_R"], FL)
    sk.line("bottom", (-XK, 0), (XK, 0))
    sk.line("shankR", (XK, 0), (XK, ZS))
    sk.line("stepR", (XK, ZS), (XS, ZS))
    pt.blend_arc(sk, "arcR", FR, P["side_R"], (XS, ZS), sR)
    pt.arc_on(sk, "lobeR", CR, "pR", sR, tR, r=P["lobe_R"])
    pt.blend_arc(sk, "top", T, P["top_R"], tR, tL)
    pt.arc_on(sk, "lobeL", CL, "pL", tL, sL, r=P["lobe_R"])
    pt.blend_arc(sk, "arcL", FL, P["side_R"], sL, (-XS, ZS))
    sk.line("stepL", (-XS, ZS), (-XK, ZS))
    sk.line("shankL", (-XK, ZS), (-XK, 0))
    loop = ["bottom", "shankR", "stepR", "arcR", "lobeR", "top", "lobeL", "arcL", "stepL", "shankL"]
    smooth = {("arcR", "lobeR"), ("lobeR", "top"), ("top", "lobeL"), ("lobeL", "arcL")}
    for a, b in zip(loop, loop[1:] + loop[:1]):
        sk.join(a, b, tangent=(a, b) in smooth)
    sk.constrain("COINCIDENT", "pO", "bottom")
    for lid in ("bottom", "stepR", "stepL"):
        sk.constrain("HORIZONTAL", lid)
    for lid in ("shankR", "shankL"):
        sk.constrain("VERTICAL", lid)
    for ref, x in (("shankR.start", XK), ("shankL.end", XK), ("stepR.end", XS), ("stepL.start", XS)):
        sk.constrain("DISTANCE", "pO", ref, value=x, direction="horizontal")
    sk.constrain("DISTANCE", "pO", "stepR.start", value=ZS, direction="vertical")
    sk.constrain("DISTANCE", "pO", "stepL.end", value=ZS, direction="vertical")
    holes = [[pt.hole(sk, "holeL", CL, "pL", P["hole_d"])], [pt.hole(sk, "holeR", CR, "pR", P["hole_d"])]]
    sk.region("plate", loop, holes=holes, extrude={"height": P["thick"], "op": "NEW", "end": "SYMMETRIC"})
    return sk


def s2_slot():
    sk = Sketch("S2_slot", plane="Right", notes="Fork slot through the shank (sketch x = world Y).")
    sk.point("pO", (0, 0), construction=True)
    sk.constrain("FIX", "pO", value=(0, 0), note="origin: shank end on the axis")
    w, top = P["slot_w"] / 2, P["shoulder_z"] - P["slot_gap"]
    pts = [(-w, -5.0), (w, -5.0), (w, top), (-w, top)]
    loop = pt.polygon(sk, "s", pts, "pO")
    sk.region("slot", loop, extrude={"op": "REMOVE", "end": "THROUGH_ALL"},
              note="starts 5 below the base so the cut does not share the bottom face")
    return sk


def build():
    return Design(
        part="speedcad-t3-20", parameters=P, sketches=[s1_profile(), s2_slot()],
        material={"name": "Steel", "density": 7850}, target_mass_g=195.43601,
        build=["S1_profile/plate", "S2_slot/slot"],
        reference={"image": "reference.jpg", "px_per_mm": 415 / 70.0, "origin_px": (992, 645)},
        origin={"feature": "shank end on the symmetry axis",
                "evidence": ["70 (holes), 40 (shoulder) and 8 (slot) measured from the shank end",
                             "outline symmetric about the vertical axis"]},
        notes=["Lower R20 read as tangent to the lobe and through the shoulder corner (15 wide at Z=40).",
               "Overlay: only S1 maps onto the front view; S2 belongs to the left view."],
    )
