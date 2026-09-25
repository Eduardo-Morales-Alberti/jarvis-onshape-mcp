"""SpeedCAD T4 exercise 19: split clamp with a fork lug and a rib (reference.jpg).

Origin: ring axis (world Y), centered in its 35 length. Front plane = X/Z view.
  S1 Front: ring R20/R15, 35 long (symmetric).
  S2 Front: tab block to 35 from the axis, 15 tall (split later), 35 long.
  S3 Right: lug 25 wide with a R12.5 top around the Ø10 axis (Z = 50 - 12.5), 15 thick.
  S4 Front: rib 5 thick from the lug face at Z=30 to the tab end at Z=7.5.
  S5 Front: 5 gap through ring + tabs, and the 5 lug slot down to Z=25 (through).
  S6 Right: Ø10 through the lug cheeks.     S7 Top: 2 x Ø6 through the tabs.
"""
from sketchgen import Design, Params, Sketch
from sketchgen import patterns as pt

P = Params({
    "ring_R": 20.0, "bore_R": 15.0, "length": 35.0,
    "tab_x": 35.0, "tab_h": 15.0, "gap": 5.0, "tab_hole_d": 6.0, "tab_hole_from_end": 8.0, "tab_hole_dy": 20.0,
    "lug_w": 25.0, "lug_t": 15.0, "lug_top": 50.0, "slot_w": 5.0, "slot_bottom": 25.0, "lug_hole_d": 10.0,
    "rib_t": 5.0, "rib_top": 30.0,
})
ZH = P["lug_top"] - P["lug_w"] / 2          # lug hole axis height (R12.5 top)
X_TAB0 = 17.0                               # tab block starts inside the ring wall (15..20)
Z_LUG0 = 17.0                               # lug starts inside the ring wall


def origin(sk):
    sk.point("pO", (0, 0), construction=True)
    sk.constrain("FIX", "pO", value=(0, 0), note="origin: ring axis, mid length")


def s1_ring():
    sk = Sketch("S1_ring", plane="Front", notes="Ring R20/R15.")
    origin(sk)
    sk.circle("outer", (0, 0), P["ring_R"])
    sk.circle("bore", (0, 0), P["bore_R"])
    for c, v in (("outer", P["ring_R"]), ("bore", P["bore_R"])):
        sk.constrain("COINCIDENT", c + ".center", "pO")
        sk.constrain("RADIUS", c, value=v)
    sk.region("ring", ["outer"], holes=[["bore"]],
              extrude={"height": P["length"], "op": "NEW", "end": "SYMMETRIC"})
    return sk


def s2_tabs():
    sk = Sketch("S2_tabs", plane="Front", notes="Tab block (split by the gap cut).")
    origin(sk)
    h = P["tab_h"] / 2
    loop = pt.polygon(sk, "t", [(X_TAB0, -h), (P["tab_x"], -h), (P["tab_x"], h), (X_TAB0, h)], "pO")
    sk.region("tabs", loop, extrude={"height": P["length"], "op": "ADD", "end": "SYMMETRIC"})
    return sk


def s3_lug():
    sk = Sketch("S3_lug", plane="Right", notes="Lug outline (sketch x = world Y).")
    origin(sk)
    w = P["lug_w"] / 2
    sk.line("vax", (0, 0), (0, P["lug_top"]), construction=True)
    sk.constrain("VERTICAL", "vax")
    sk.constrain("COINCIDENT", "vax.start", "pO")
    sk.point("pH", (0, ZH), construction=True)
    sk.constrain("COINCIDENT", "pH", "vax")
    sk.constrain("DISTANCE", "pO", "pH", value=ZH, direction="vertical")
    sk.line("bot", (-w, Z_LUG0), (w, Z_LUG0))
    sk.line("right", (w, Z_LUG0), (w, ZH))
    sk.arc("top", (0, ZH), w, (w, ZH), (-w, ZH))
    sk.line("left", (-w, ZH), (-w, Z_LUG0))
    loop = ["bot", "right", "top", "left"]
    for a, b in zip(loop, loop[1:] + loop[:1]):
        sk.join(a, b, tangent=(a, b) in {("right", "top"), ("top", "left")})
    sk.constrain("COINCIDENT", "top.center", "pH")
    sk.constrain("RADIUS", "top", value=w)
    sk.constrain("HORIZONTAL", "bot")
    sk.constrain("VERTICAL", "right")
    sk.constrain("VERTICAL", "left")
    sk.constrain("DISTANCE", "pO", "bot.start", value=Z_LUG0, direction="vertical")
    sk.region("lug", loop, extrude={"height": P["lug_t"], "op": "ADD", "end": "SYMMETRIC"})
    return sk


def s4_rib():
    sk = Sketch("S4_rib", plane="Front", notes="Rib; its short edge stays inside the ring wall.")
    origin(sk)
    xl, zt = P["lug_t"] / 2, P["tab_h"] / 2
    pts = [(xl, P["rib_top"]), (P["tab_x"], zt), (X_TAB0, zt), (xl, Z_LUG0)]
    loop = pt.polygon(sk, "r", pts, "pO")
    sk.region("rib", loop, extrude={"height": P["rib_t"], "op": "ADD", "end": "SYMMETRIC"})
    return sk


def s5_cuts():
    sk = Sketch("S5_cuts", plane="Front", notes="Clamp gap and lug slot.")
    origin(sk)
    g, s = P["gap"] / 2, P["slot_w"] / 2
    gap = pt.polygon(sk, "g", [(10.0, -g), (P["tab_x"] + 5, -g), (P["tab_x"] + 5, g), (10.0, g)], "pO")
    slot = pt.polygon(sk, "s", [(-s, P["slot_bottom"]), (s, P["slot_bottom"]),
                                (s, P["lug_top"] + 5), (-s, P["lug_top"] + 5)], "pO")
    sk.region("gap", gap, extrude={"op": "REMOVE", "end": "THROUGH_ALL"})
    sk.region("slot", slot, extrude={"op": "REMOVE", "end": "THROUGH_ALL"})
    return sk


def s6_lug_hole():
    sk = Sketch("S6_lug_hole", plane="Right", notes="Ø10 through the cheeks.")
    origin(sk)
    sk.line("vax", (0, 0), (0, ZH), construction=True)
    sk.constrain("VERTICAL", "vax")
    sk.constrain("COINCIDENT", "vax.start", "pO")
    sk.constrain("LENGTH", "vax", value=ZH)
    sk.region("h10", [pt.hole(sk, "h10", (0, ZH), "vax.end", P["lug_hole_d"])],
              extrude={"op": "REMOVE", "end": "THROUGH_ALL"})
    return sk


def s7_tab_holes():
    sk = Sketch("S7_tab_holes", plane="Top", notes="2 x Ø6 through both tabs.")
    origin(sk)
    x = P["tab_x"] - P["tab_hole_from_end"]
    for k, y in (("a", -P["tab_hole_dy"] / 2), ("b", P["tab_hole_dy"] / 2)):
        sk.point("p" + k, (x, y), construction=True)
        sk.constrain("DISTANCE", "pO", "p" + k, value=x, direction="horizontal")
        sk.constrain("DISTANCE", "pO", "p" + k, value=abs(y), direction="vertical")
        sk.region("h6" + k, [pt.hole(sk, "h6" + k, (x, y), "p" + k, P["tab_hole_d"])],
                  extrude={"op": "REMOVE", "end": "THROUGH_ALL"})
    return sk


def build():
    return Design(
        part="t4scad-19", parameters=P,
        sketches=[s1_ring(), s2_tabs(), s3_lug(), s4_rib(), s5_cuts(), s6_lug_hole(), s7_tab_holes()],
        material={"name": "Steel", "density": 7850}, target_mass_g=245.69464,
        build=["S1_ring/ring", "S2_tabs/tabs", "S3_lug/lug", "S4_rib/rib", "S5_cuts/gap", "S5_cuts/slot",
               "S6_lug_hole/h10", "S7_tab_holes/h6a", "S7_tab_holes/h6b"],
        reference={"image": "reference.jpg", "px_per_mm": 215 / 35.0, "origin_px": (663, 475)},
        origin={"feature": "ring axis, mid length",
                "evidence": ["R20/R15 on it", "50, 25, 30, 35 measured from it", "35 length centered"]},
        notes=["Tab block and lug start inside the ring wall; rib short edge inside the ring wall."],
    )
