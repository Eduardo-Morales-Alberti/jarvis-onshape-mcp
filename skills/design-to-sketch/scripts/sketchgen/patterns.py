"""High-level sketch building blocks, so a design.py states the drawing and
not the bookkeeping. Each helper adds entities + the constraints a designer
would put on them, and returns the geometry the next step needs.

Conventions: `ref` is the point ref a center hangs on ("sk_CA.end", "pO"),
`d`/`r`/`R` are Param values (keep the name for FeatureScript inputs).
"""
from . import geometry as g


def hole(sk, id, center, ref, d):
    """Full circle of diameter d centered on the point `ref`."""
    sk.circle(id, center, d / 2)
    sk.constrain("COINCIDENT", id + ".center", ref)
    sk.constrain("DIAMETER", id, value=d)
    return id


def ring(sk, name, center, ref, d_out, d_in, extrude=None, bore_extrude=None):
    """Boss ring: <name>_out on `ref`, concentric <name>_bore. Optional
    regions: ring (outer minus bore) and bore."""
    out = hole(sk, name + "_out", center, ref, d_out)
    sk.circle(name + "_bore", center, d_in / 2)
    sk.constrain("CONCENTRIC", name + "_bore", out)
    sk.constrain("DIAMETER", name + "_bore", value=d_in)
    if extrude:
        sk.region("boss_" + name, [out], holes=[[name + "_bore"]], extrude=extrude)
    if bore_extrude:
        sk.region("bore_" + name, [name + "_bore"], extrude=bore_extrude,
                  note="apply after all additive features")
    return out, name + "_bore"


def arc_on(sk, id, center, ref, p, q, d=None, r=None, short=False):
    """Arc of a known circle (center on `ref`) from p to q: counter-clockwise,
    or the short way. Dimensioned with DIAMETER d or RADIUS r."""
    radius = d / 2 if d is not None else r
    (sk.arc_short if short else sk.arc)(id, center, radius, p, q)
    sk.constrain("COINCIDENT", id + ".center", ref)
    if d is not None:
        sk.constrain("DIAMETER", id, value=d)
    else:
        sk.constrain("RADIUS", id, value=r)
    return id


def blend(c1, r1, c2, r2, R, away_from, external=True):
    """Arc of radius R tangent to both circles: returns (center, t1, t2), the
    tangent points on circle 1 and circle 2. The root farthest from
    `away_from` is taken (e.g. the part centroid for concave blends)."""
    pc = g.tangent_arc_center(c1, r1, c2, r2, R, external=external, away_from=away_from)
    return pc, g.tangent_point(c1, r1, pc), g.tangent_point(c2, r2, pc)


def blend_arc(sk, id, pc, R, p, q):
    """The short arc of a blend (see blend) with its RADIUS."""
    sk.arc_short(id, pc, R, p, q)
    sk.constrain("RADIUS", id, value=R)
    return id


def offset_arc(sk, id, master, pc, R_master, w, p, q):
    """Arc concentric with `master`, w further out (radius R_master + w),
    dimensioned as the drawing does: DISTANCE master-arc = w."""
    sk.arc_short(id, pc, R_master + w, p, q)
    sk.constrain("CONCENTRIC", id, master)
    sk.constrain("DISTANCE", master, id, value=w)
    return id


def profile(sk, ids, tangent=True, closed=True):
    """COINCIDENT on every shared endpoint of consecutive curves (+ TANGENT)."""
    pairs = list(zip(ids, ids[1:])) + ([(ids[-1], ids[0])] if closed else [])
    for a, b in pairs:
        sk.join(a, b, tangent=tangent)
    return list(ids)


def rays(sk, origin, spec, close=None, note=None):
    """Construction skeleton of rays from a fixed origin, dimensioned like the
    drawing: spec = [(id, end, length, orient), ...] where orient is
    "HORIZONTAL" / "VERTICAL" or ("ANGLE", other_ray_id, angle). close=(id,
    ray_i, ray_j) adds a construction line joining two ray ends. The first
    ray's start is the origin (FIX). Returns the point ref of each ray end."""
    first = spec[0][0]
    for k, (rid, end, length, orient) in enumerate(spec):
        sk.line(rid, origin, end, construction=True)
        if k == 0:
            sk.constrain("FIX", rid + ".start", value=origin, note=note or "origin")
        else:
            sk.constrain("COINCIDENT", rid + ".start", first + ".start")
    if close:
        cid, ri, rj = close
        ends = {r[0]: r[1] for r in spec}
        sk.line(cid, ends[ri], ends[rj], construction=True)
        sk.constrain("COINCIDENT", cid + ".start", ri + ".end")
        sk.constrain("COINCIDENT", cid + ".end", rj + ".end")
    for rid, end, length, orient in spec:
        if isinstance(orient, str):
            sk.constrain(orient, rid)
    for rid, end, length, orient in spec:
        sk.constrain("LENGTH", rid, value=length)
    for rid, end, length, orient in spec:
        if not isinstance(orient, str):
            sk.constrain("ANGLE", orient[1], rid, value=orient[2])
    return {r[0]: r[0] + ".end" for r in spec}


def polygon(sk, prefix, pts, origin_ref, dims=None, construction=False, hline=None, vline=None):
    """Closed polygon of line segments <prefix>0..n-1 (vertex k = pts[k]).
    Every vertex is dimensioned from the fixed point `origin_ref` with a
    horizontal and a vertical DISTANCE, like a turned-part section drawn from
    its axis and base. `dims[k] = (x_value, y_value)` may carry Params (the
    drawing's names); default is the plain coordinates. Axis-aligned edges get
    HORIZONTAL / VERTICAL. A vertex on the origin's horizontal (vertical) gets a
    point-on-line COINCIDENT with the construction line `hline` (`vline`)
    instead of a zero dimension. Returns the line ids in loop order."""
    n = len(pts)
    ids = ["%s%d" % (prefix, k) for k in range(n)]
    for k in range(n):
        sk.line(ids[k], pts[k], pts[(k + 1) % n], construction=construction)
    profile(sk, ids, tangent=False)
    origin = sk.point_of(origin_ref)
    for k in range(n):
        (x0, y0), (x1, y1) = pts[k], pts[(k + 1) % n]
        if abs(y1 - y0) < 1e-9:
            sk.constrain("HORIZONTAL", ids[k])
        elif abs(x1 - x0) < 1e-9:
            sk.constrain("VERTICAL", ids[k])
    for k in range(n):
        dx, dy = (dims[k] if dims else (None, None))
        x, y = pts[k]
        vx = dx if dx is not None else abs(x - origin[0])
        vy = dy if dy is not None else abs(y - origin[1])
        ref = ids[k] + ".start"
        for on_line, line, direction, v in ((abs(x - origin[0]) < 1e-9, vline, "horizontal", vx),
                                            (abs(y - origin[1]) < 1e-9, hline, "vertical", vy)):
            if not on_line:
                sk.constrain("DISTANCE", origin_ref, ref, value=v, direction=direction)
            elif line:
                sk.constrain("COINCIDENT", ref, line)
            else:
                raise ValueError("%s: vertex %s lies on the origin's %s line: pass %s"
                                 % (sk.id, ref, "vertical" if direction == "horizontal" else "horizontal",
                                    "vline" if direction == "horizontal" else "hline"))
    return ids
