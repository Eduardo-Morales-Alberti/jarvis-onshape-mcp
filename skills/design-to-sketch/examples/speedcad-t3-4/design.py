"""SpeedCAD T3 exercise 4: two-lobe plate with hex boss (reference.jpg).

Origin: center of the Ø45 boss / hexagon (vertex of 145°, start of both 50).
Outline ccw: R15 lobe (Ø10) -> top line -> R35 (O) -> left line -> R15 lobe (Ø15)
-> concave R15 fillet -> R30 (O) -> bottom line. Plate 5, boss top at 15.
"""
import math

from sketchgen import Design, Params, Sketch
from sketchgen import geometry as g
from sketchgen import patterns as pt

P = Params({
    "R_dist": 50.0, "R_hole_d": 10.0, "L_dist": 50.0, "L_hole_d": 15.0, "L_angle_deg": 145.0,
    "lobe_R": 15.0, "top_R": 35.0, "bottom_R": 30.0, "fillet_R": 15.0,
    "boss_d": 45.0, "hex_af": 30.0, "plate_h": 5.0, "total_h": 15.0,
})
O = (0.0, 0.0)
CR = (P["R_dist"], 0.0)
CL = g.polar(O, P["L_dist"], math.radians(-P["L_angle_deg"]))


def skeleton(sk):
    pt.rays(sk, O, [("sk_OR", CR, P["R_dist"], "HORIZONTAL"),
                    ("sk_OL", CL, P["L_dist"], ("ANGLE", "sk_OR", P["L_angle_deg"]))],
            note="origin at boss / hexagon center")


def s1_plate():
    sk = Sketch("S1_plate", notes="Plate outline + both holes, 5 thick.")
    skeleton(sk)
    top35, topR = g.tangent_line(O, P["top_R"], CR, P["lobe_R"], side=1)
    left35, leftL = g.tangent_line(O, P["top_R"], CL, P["lobe_R"], side=-1)
    bot30, botR = g.tangent_line(O, P["bottom_R"], CR, P["lobe_R"], side=-1)
    u = g.sub(CL, O)  # fillet on the lower side of O->L (cross > 0)
    F = max(g.circle_circle(CL, P["lobe_R"] + P["fillet_R"], O, P["bottom_R"] + P["fillet_R"]),
            key=lambda p: u[0] * p[1] - u[1] * p[0])
    fL, f30 = g.tangent_point(CL, P["lobe_R"], F), g.tangent_point(O, P["bottom_R"], F)
    pt.arc_on(sk, "o_lobeR", CR, "sk_OR.end", botR, topR, r=P["lobe_R"])
    sk.line("o_top", topR, top35)
    pt.arc_on(sk, "o_R35", O, "sk_OR.start", top35, left35, r=P["top_R"])
    sk.line("o_left", left35, leftL)
    pt.arc_on(sk, "o_lobeL", CL, "sk_OL.end", leftL, fL, r=P["lobe_R"])
    pt.blend_arc(sk, "o_fillet", F, P["fillet_R"], fL, f30)
    pt.arc_on(sk, "o_R30", O, "sk_OR.start", f30, bot30, r=P["bottom_R"])
    sk.line("o_bottom", bot30, botR)
    loop = pt.profile(sk, ["o_lobeR", "o_top", "o_R35", "o_left", "o_lobeL", "o_fillet", "o_R30", "o_bottom"])
    holes = [[pt.hole(sk, "hole_R", CR, "sk_OR.end", P["R_hole_d"])],
             [pt.hole(sk, "hole_L", CL, "sk_OL.end", P["L_hole_d"])]]
    sk.region("plate", loop, holes=holes, extrude={"height": P["plate_h"], "op": "NEW"})
    return sk


def s2_boss():
    sk = Sketch("S2_boss", notes="Ø45 boss with the hexagonal through-hole.")
    skeleton(sk)
    pt.hole(sk, "boss", O, "sk_OR.start", P["boss_d"])
    verts = g.regular_polygon(O, 6, across_flats=P["hex_af"], first_vertex_deg=90)
    sk.circle("hex_circ", O, g.dist(O, verts[0]), construction=True)
    sk.constrain("COINCIDENT", "hex_circ.center", "sk_OR.start")
    hexl = ["hex%d" % k for k in range(6)]
    for k in range(6):
        sk.line(hexl[k], verts[k], verts[(k + 1) % 6])
        sk.constrain("COINCIDENT", hexl[k] + ".start", "hex_circ")
    pt.profile(sk, hexl, tangent=False)
    for k in range(1, 6):
        sk.constrain("EQUAL", hexl[0], hexl[k])
    sk.constrain("VERTICAL", "hex1")
    sk.constrain("DISTANCE", "hex1", "hex4", value=P["hex_af"], note="across flats")
    sk.region("boss", ["boss"], holes=[hexl], extrude={"height": P["total_h"], "op": "ADD"})
    sk.region("hex_bore", hexl, extrude={"op": "REMOVE", "end": "THROUGH_ALL"})
    return sk


def build():
    return Design(
        part="speedcad-t3-4", parameters=P, sketches=[s1_plate(), s2_boss()],
        material={"name": "Steel", "density": 7850}, target_mass_g=245.50779,
        build=["S1_plate/plate", "S2_boss/boss", "S2_boss/hex_bore"],
        reference={"image": "reference.jpg", "px_per_mm": 3.733, "origin_px": (845.5, 250)},
        origin={"feature": "center of the Ø45 boss / hexagon",
                "evidence": ["vertex of 145 deg", "start of both 50 dimensions",
                             "R35, R30, Ø45 and hexagon concentric"]},
        notes=["Front view: plate 5, boss top at 15 from the base face; holes and hexagon through."],
    )
