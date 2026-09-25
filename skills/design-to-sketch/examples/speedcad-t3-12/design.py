"""SpeedCAD T3 exercise 12: turned body with a side pin boss (reference.jpg).

Front plane (sketch x = world X, sketch y = world Z), origin on the main axis
at the base (main feature: the revolved body; every height is from the base,
every radius from the axis). Two half-sections, each revolved 360 deg:
  S1 body : Ø70x8 disc, Ø30x4 recess below, frustum Ø40 (=70/2-15) -> Ø20 at 45,
            Ø8 through bore; about the vertical axis.
  S2 boss : Ø12 neck buried in the cone from X=10, Ø20x5 flange at X=20..25,
            Ø6x2 pin hole in the outer face; about the horizontal axis Z=28.
"""
from sketchgen import Design, Params, Sketch
from sketchgen import patterns as pt

P = Params({
    "base_d": 70.0, "base_h": 8.0, "recess_d": 30.0, "recess_h": 4.0,
    "cone_inset": 15.0, "top_d": 20.0, "height": 45.0, "bore_d": 8.0,
    "boss_z": 28.0, "neck_d": 12.0, "flange_d": 20.0, "flange_t": 5.0,
    "pin_d": 6.0, "pin_depth": 2.0, "neck_x0": 10.0,
})
R_BASE, R_CONE0 = P["base_d"] / 2, P["base_d"] / 2 - P["cone_inset"]
X_FL0 = P["base_d"] / 2 - P["cone_inset"]  # flange inner face (same "15" line)
X_FL1 = X_FL0 + P["flange_t"]


def s1_section():
    sk = Sketch("S1_section", plane="Front", notes="Half section of the turned body.")
    sk.line("axis", (0, 0), (0, P["height"]), construction=True)
    sk.line("base", (0, 0), (R_BASE, 0), construction=True)
    sk.constrain("FIX", "axis.start", value=(0, 0), note="origin: main axis at the base")
    sk.constrain("VERTICAL", "axis")
    sk.constrain("HORIZONTAL", "base")
    sk.constrain("COINCIDENT", "base.start", "axis.start")
    b = P["bore_d"] / 2
    pts = [(b, P["recess_h"]), (P["recess_d"] / 2, P["recess_h"]), (P["recess_d"] / 2, 0), (R_BASE, 0),
           (R_BASE, P["base_h"]), (R_CONE0, P["base_h"]), (P["top_d"] / 2, P["height"]), (b, P["height"])]
    dims = [(None, P["recess_h"]), (None, P["recess_h"]), (None, None), (None, None),
            (None, P["base_h"]), (None, P["base_h"]), (None, P["height"]), (None, P["height"])]
    loop = pt.polygon(sk, "b", pts, "axis.start", dims=dims, hline="base", vline="axis")
    sk.region("body", loop, revolve={"axis": "axis", "op": "NEW"})
    return sk


def s2_boss():
    sk = Sketch("S2_boss", plane="Front", notes="Half section of the side pin boss.")
    z = P["boss_z"]
    sk.line("zref", (0, 0), (0, z), construction=True)
    sk.line("axis2", (0, z), (X_FL1 + 5, z), construction=True)
    sk.constrain("FIX", "zref.start", value=(0, 0), note="origin: main axis at the base")
    sk.constrain("VERTICAL", "zref")
    sk.constrain("LENGTH", "zref", value=z)
    sk.constrain("COINCIDENT", "axis2.start", "zref.end")
    sk.constrain("HORIZONTAL", "axis2")
    rn, rf, rp = P["neck_d"] / 2, P["flange_d"] / 2, P["pin_d"] / 2
    xp = X_FL1 - P["pin_depth"]
    pts = [(P["neck_x0"], z), (xp, z), (xp, z + rp), (X_FL1, z + rp),
           (X_FL1, z + rf), (X_FL0, z + rf), (X_FL0, z + rn), (P["neck_x0"], z + rn)]
    dims = [(P["neck_x0"], z), (None, z), (None, None), (None, None),
            (None, None), (None, None), (None, None), (P["neck_x0"], None)]
    loop = pt.polygon(sk, "p", pts, "zref.start", dims=dims)
    sk.region("boss", loop, revolve={"axis": "axis2", "op": "ADD"})
    return sk


def build():
    return Design(
        part="speedcad-t3-12", parameters=P, sketches=[s1_section(), s2_boss()],
        material={"name": "Steel", "density": 7850}, target_mass_g=433.18766,
        build=["S1_section/body", "S2_boss/boss"],
        reference={"image": "reference.jpg", "px_per_mm": 463 / 70.0, "origin_px": (899.5, 574)},
        origin={"feature": "main revolution axis at the base (turned body)",
                "evidence": ["Ø70, Ø30, Ø20, Ø8 all on the vertical axis",
                             "45, 8, 4 and 28 measured from the base face"]},
        notes=["Pin hole Ø6 read as 2 deep from the flange face; cone base Ø40 from the 15 inset.",
               "neck_x0 is not on the drawing: any value buried in the cone gives the same solid."],
    )
