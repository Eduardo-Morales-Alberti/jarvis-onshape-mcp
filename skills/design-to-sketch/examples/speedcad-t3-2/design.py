"""SpeedCAD T3 exercise 2: tri-lobe bracket (reference.jpg).

Top plane, origin at the center of boss C (main feature: largest boss, vertex
of 60 deg, start of both 60 dimensions). Built with sketchgen.patterns.
"""
import math

from sketchgen import Design, Params, Sketch
from sketchgen import geometry as g
from sketchgen import patterns as pt

P = Params({
    "side": 60.0, "angle_deg": 60.0,            # boss centers: equilateral triangle, CA vertical
    "A_d": 30.0, "A_bore": 15.0, "A_h": 30.0,   # top boss
    "B_d": 35.0, "B_bore": 20.0, "B_h": 35.0,   # left boss
    "C_d": 50.0, "C_bore": 30.0, "C_h": 40.0,   # bottom boss (origin)
    "arm_R": 45.0, "arm_w": 7.0, "arm_h": 20.0,  # concave arm arc, arm width, arm height
    "plate_h": 10.0,                            # whole footprint
})

C, A = (0.0, 0.0), (0.0, P["side"])
_t = math.radians(90 + P["angle_deg"])
B = (P["side"] * math.cos(_t), P["side"] * math.sin(_t))
BOSS = {"A": (A, P["A_d"], "sk_CA.end"), "B": (B, P["B_d"], "sk_CB.end"), "C": (C, P["C_d"], "sk_CA.start")}
CENTROID = ((A[0] + B[0] + C[0]) / 3, (A[1] + B[1] + C[1]) / 3)
ARMS = [("A", "B"), ("B", "C"), ("C", "A")]  # counter-clockwise


def arm(i, j):
    """R45 blend tangent to bosses i, j (outside the triangle) + where the
    concentric inner arc (R45 + 7) cuts each boss, on the side facing the other."""
    (ci, di, _), (cj, dj, _) = BOSS[i], BOSS[j]
    pc, ti, tj = pt.blend(ci, di / 2, cj, dj / 2, P["arm_R"], away_from=CENTROID)
    R2 = P["arm_R"] + P["arm_w"]
    ii = min(g.circle_circle(pc, R2, ci, di / 2), key=lambda p: g.dist(p, cj))
    ij = min(g.circle_circle(pc, R2, cj, dj / 2), key=lambda p: g.dist(p, ci))
    return pc, ti, tj, ii, ij


def skeleton(sk):
    pt.rays(sk, C, [("sk_CA", A, P["side"], "VERTICAL"),
                    ("sk_CB", B, P["side"], ("ANGLE", "sk_CA", P["angle_deg"]))],
            close=("sk_AB", "sk_CA", "sk_CB"), note="origin at center of boss C")


def s1_bosses():
    sk = Sketch("S1_bosses", notes="Boss rings and through bores, extruded from the Top plane.")
    skeleton(sk)
    for n in "ABC":
        c, _, ref = BOSS[n]
        pt.ring(sk, n, c, ref, P[n + "_d"], P[n + "_bore"],
                extrude={"height": P[n + "_h"], "op": "ADD"},
                bore_extrude={"op": "REMOVE", "end": "THROUGH_ALL"})
    return sk


def s2_footprint():
    sk = Sketch("S2_footprint", notes="3 convex boss arcs + 3 concave R45 arcs, tangent at every junction.")
    skeleton(sk)
    geo = {ij: arm(*ij) for ij in ARMS}
    loop = []
    for k, (i, j) in enumerate(ARMS):
        c, d, ref = BOSS[i]
        pt.arc_on(sk, "f_" + i, c, ref, geo[ARMS[k - 1]][2], geo[(i, j)][1], d=d)
        pc, ti, tj, _, _ = geo[(i, j)]
        loop += ["f_" + i, pt.blend_arc(sk, "f_R%s%s" % (i, j), pc, P["arm_R"], ti, tj)]
    sk.region("footprint", pt.profile(sk, loop), extrude={"height": P["plate_h"], "op": "NEW"})
    return sk


def s3_arms():
    sk = Sketch("S3_arms", notes="Arm bands: R45 arc, concentric arc 7 further in, short boss arcs.")
    skeleton(sk)
    for i, j in ARMS:
        pc, ti, tj, ii, ij = arm(i, j)
        o, n = "a_R%s%s" % (i, j), "a_in%s%s" % (i, j)
        bi, bj = "a_%s%s_%s" % (i, j, i), "a_%s%s_%s" % (i, j, j)
        pt.blend_arc(sk, o, pc, P["arm_R"], ti, tj)
        pt.offset_arc(sk, n, o, pc, P["arm_R"], P["arm_w"], ii, ij)
        for b, name, t, x in ((bi, i, ti, ii), (bj, j, tj, ij)):
            c, d, ref = BOSS[name]
            pt.arc_on(sk, b, c, ref, t, x, d=d, short=True)
        sk.join(o, bi, tangent=True)
        sk.join(o, bj, tangent=True)
        sk.join(bi, n)
        sk.join(bj, n)
        sk.region("arm_%s%s" % (i, j), [o, bj, n, bi], extrude={"height": P["arm_h"], "op": "ADD"})
    return sk


def build():
    return Design(
        part="speedcad-t3-2",
        parameters=P,
        sketches=[s1_bosses(), s2_footprint(), s3_arms()],
        material={"name": "Steel", "density": 7850},
        target_mass_g=891.75399,
        build=["S2_footprint/footprint", "S3_arms/arm_AB", "S3_arms/arm_BC", "S3_arms/arm_CA",
               "S1_bosses/boss_A", "S1_bosses/boss_B", "S1_bosses/boss_C",
               "S1_bosses/bore_A", "S1_bosses/bore_B", "S1_bosses/bore_C"],
        reference={"image": "reference.jpg", "px_per_mm": 271 / 60.0, "origin_px": (776, 512)},
        origin={"feature": "center of boss C (Ø50, main feature)",
                "evidence": ["vertex of the 60 deg angular dimension",
                             "start of the vertical 60 to boss A",
                             "start of the aligned 60 to boss B"]},
        notes=["Heights (right view): A 30, B 35, C 40, arms 20, plate 10.",
               "Each R45 arc is tangent to both bosses it joins; inner arc concentric, 7 further in."],
    )
