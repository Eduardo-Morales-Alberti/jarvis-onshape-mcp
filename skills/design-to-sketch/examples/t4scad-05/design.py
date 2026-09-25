"""SpeedCAD T4 exercise 5: hub with 5 arms and eyes at 72 deg (reference.jpg).

Origin: hub axis at mid-height (arms and eyes are centered on the hub's
mid-height, so the Top plane is the arms' mid plane). Three sketches:
  S1 Front: hub half section (Ø35x20, Ø25 counterbore 10 deep from the top,
     Ø15 through), revolved about Z.
  S2 Top  : one arm along -X, 4 wide, from inside the hub to inside the eye,
     extruded symmetric 6 (NEW: seed body of the pattern).
  S3 Front: its eye, Ø20/Ø12 ring centered 50 out, extruded symmetric 8 (ADD).
Arm + eye are patterned x5 about Z (72 deg) and united with the hub.
"""
from sketchgen import Design, Params, Sketch
from sketchgen import patterns as pt

P = Params({
    "hub_d": 35.0, "hub_h": 20.0, "cbore_d": 25.0, "cbore_depth": 10.0, "bore_d": 15.0,
    "arm_w": 4.0, "arm_h": 6.0, "eye_r": 50.0, "eye_d": 20.0, "eye_hole_d": 12.0, "eye_t": 8.0,
})
H = P["hub_h"] / 2


def origin(sk):
    sk.point("pO", (0, 0), construction=True)
    sk.constrain("FIX", "pO", value=(0, 0), note="origin: hub axis at mid-height")


def s1_hub():
    sk = Sketch("S1_hub", plane="Front", notes="Hub half section, revolved about Z.")
    origin(sk)
    sk.line("axis", (0, -H), (0, H), construction=True)
    sk.line("mid", (0, 0), (P["hub_d"] / 2, 0), construction=True)
    sk.constrain("VERTICAL", "axis")
    sk.constrain("COINCIDENT", "pO", "axis")
    sk.constrain("HORIZONTAL", "mid")
    sk.constrain("COINCIDENT", "mid.start", "pO")
    rb, rc, rh = P["bore_d"] / 2, P["cbore_d"] / 2, P["hub_d"] / 2
    zc = H - P["cbore_depth"]
    pts = [(rb, -H), (rh, -H), (rh, H), (rc, H), (rc, zc), (rb, zc)]
    loop = pt.polygon(sk, "h", pts, "pO", hline="mid", vline="axis")
    sk.region("body", loop, revolve={"axis": "axis", "op": "NEW"})
    return sk


def s2_arm():
    sk = Sketch("S2_arm", plane="Top", notes="One arm along -X; patterned x5.")
    origin(sk)
    w = P["arm_w"] / 2
    x0 = P["hub_d"] / 2 - 2.5                       # starts inside the hub wall
    x1 = P["eye_r"] - P["eye_d"] / 2 + 3            # ends inside the eye ring, short of its hole
    pts = [(-x1, -w), (-x0, -w), (-x0, w), (-x1, w)]
    loop = pt.polygon(sk, "a", pts, "pO")
    sk.region("arm", loop, extrude={"height": P["arm_h"], "op": "NEW", "end": "SYMMETRIC"})
    return sk


def s3_eye():
    sk = Sketch("S3_eye", plane="Front", notes="Eye ring at the arm's end; patterned x5.")
    origin(sk)
    c = (-P["eye_r"], 0)
    sk.line("ray", (0, 0), c, construction=True)
    sk.constrain("COINCIDENT", "ray.start", "pO")
    sk.constrain("HORIZONTAL", "ray")
    sk.constrain("LENGTH", "ray", value=P["eye_r"])
    pt.ring(sk, "eye", c, "ray.end", P["eye_d"], P["eye_hole_d"],
            extrude={"height": P["eye_t"], "op": "ADD", "end": "SYMMETRIC"})
    return sk


def build():
    return Design(
        part="t4scad-05", parameters=P, sketches=[s1_hub(), s2_arm(), s3_eye()],
        material={"name": "Steel", "density": 7850}, target_mass_g=183.15368,
        build=["S1_hub/body",
               {"circular_pattern": {"steps": ["S2_arm/arm", "S3_eye/boss_eye"], "axis": "Z", "count": 5}}],
        reference={"image": "reference.jpg", "px_per_mm": 4.4, "origin_px": (945, 270)},
        origin={"feature": "hub axis at mid-height",
                "evidence": ["Ø35/Ø25/Ø15 and the 72 deg pattern on the hub axis",
                             "50 from the hub axis to the eyes; arms and eyes centered on the hub height"]},
        notes=["Arm ends and starts are buried (inside the hub wall and the eye ring): not on the drawing.",
               "Overlay: S2 maps onto the top view; S1/S3 are Front-plane sections."],
    )
