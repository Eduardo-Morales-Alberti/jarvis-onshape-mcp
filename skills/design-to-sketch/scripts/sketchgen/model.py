"""Sketch model: entities + Onshape-named constraints + regions, with numeric
verification and JSON export (schema "sketchgen/1")."""
import math

from . import geometry as g

SCHEMA = "sketchgen/1"
TOL = 1e-6
MIN_CLEARANCE = 0.2  # mm from any edge, for qContainsPoint region picking
PLANES = {"Top", "Front", "Right"}

# type -> (arity, needs value)
CONSTRAINTS = {
    "COINCIDENT": (2, False),
    "CONCENTRIC": (2, False),
    "TANGENT": (2, False),
    "PARALLEL": (2, False),
    "PERPENDICULAR": (2, False),
    "EQUAL": (2, False),
    "MIDPOINT": (2, False),
    "HORIZONTAL": ((1, 2), False),   # a line, or two points
    "VERTICAL": ((1, 2), False),
    "FIX": (1, True),
    "RADIUS": (1, True),
    "DIAMETER": (1, True),
    "LENGTH": (1, True),
    "DISTANCE": (2, True),
    "ANGLE": (2, True),
}
EXTRUDE_OPS = {"NEW", "ADD", "REMOVE", "INTERSECT"}
END_TYPES = {"BLIND", "THROUGH_ALL", "SYMMETRIC", "UP_TO_NEXT"}


class Param(float):
    """A drawing dimension that remembers its name, so constraints and extrude
    hints built from it can point back at the parameter (for FeatureScript
    inputs). Arithmetic returns a plain float: derived values stay literal."""

    def __new__(cls, name, value):
        obj = float.__new__(cls, value)
        obj.name = name
        return obj


def Params(values):
    """Parameter table: {name: number} -> {name: Param}."""
    return {k: Param(k, v) for k, v in values.items()}


def _r(v):
    return round(v, 6)


def _pt(p):
    return [_r(p[0]), _r(p[1])]


class Sketch:
    def __init__(self, id, plane="Top", name=None, notes=None, offset=0.0):
        """offset: the sketch plane is the default plane moved along its
        normal by this many mm (Top +Z, Front -Y, Right +X)."""
        self.id = id
        self.plane = plane
        self.offset = offset
        self.name = name or id
        self.notes = notes
        self.entities = {}
        self.constraints = []
        self.regions = []

    # ---- entities -------------------------------------------------------
    def _add(self, e):
        if e["id"] in self.entities:
            raise ValueError("duplicate entity id %s in %s" % (e["id"], self.id))
        self.entities[e["id"]] = e
        return e["id"]

    def point(self, id, at, construction=False):
        return self._add({"id": id, "type": "point", "construction": construction, "at": tuple(at)})

    def line(self, id, start, end, construction=False):
        return self._add({"id": id, "type": "line", "construction": construction,
                          "start": tuple(start), "end": tuple(end)})

    def circle(self, id, center, radius, construction=False):
        return self._add({"id": id, "type": "circle", "construction": construction,
                          "center": tuple(center), "radius": radius})

    def arc(self, id, center, radius, start, end, construction=False):
        """Arc running counter-clockwise from `start` to `end` around `center`.
        start/end are snapped onto the circle."""
        a0, a1 = g.angle_of(center, start), g.angle_of(center, end)
        return self._arc(id, center, radius, a0, a1, construction)

    def arc_short(self, id, center, radius, p, q, construction=False):
        """Arc between p and q taking the shorter way round (order chosen so
        the stored direction is still counter-clockwise)."""
        a, b = g.angle_of(center, p), g.angle_of(center, q)
        if g.ccw_sweep(a, b) > math.pi:
            a, b = b, a
        return self._arc(id, center, radius, a, b, construction)

    def _arc(self, id, center, radius, a0, a1, construction):
        sweep = g.ccw_sweep(a0, a1)
        return self._add({"id": id, "type": "arc", "construction": construction,
                          "center": tuple(center), "radius": radius,
                          "start": g.polar(center, radius, a0),
                          "mid": g.polar(center, radius, a0 + sweep / 2),
                          "end": g.polar(center, radius, a0 + sweep),
                          "start_angle": a0, "sweep": sweep})

    # ---- constraints / regions -----------------------------------------
    def constrain(self, type, *refs, value=None, note=None, direction=None):
        """direction (DISTANCE only): "horizontal" or "vertical" measures just
        dx or dy between two points, like a horizontal/vertical dimension."""
        c = {"type": type, "refs": list(refs)}
        if value is not None:
            c["value"] = value
        if direction:
            c["direction"] = direction
        if note:
            c["note"] = note
        self.constraints.append(c)

    def join(self, a, b, tangent=False):
        """COINCIDENT on every endpoint shared by curves a and b (plus TANGENT
        if asked). Raises if they share none, so a bad chain fails loudly."""
        ea, eb = self.entities[a], self.entities[b]
        shared = [(ka, kb) for ka in ("start", "end") for kb in ("start", "end")
                  if g.dist(ea[ka], eb[kb]) < TOL]
        if not shared:
            raise ValueError("%s: %s and %s share no endpoint" % (self.id, a, b))
        for ka, kb in shared:
            self.constrain("COINCIDENT", "%s.%s" % (a, ka), "%s.%s" % (b, kb))
        if tangent:
            self.constrain("TANGENT", a, b)

    def region(self, id, loop, holes=None, extrude=None, revolve=None, note=None):
        """extrude: dict(height=..., op=NEW|ADD|REMOVE, end=BLIND|THROUGH_ALL).
        revolve: dict(axis=<line id in this sketch>, op=..., angle=360)."""
        if extrude and revolve:
            raise ValueError("region %s: extrude or revolve, not both" % id)
        r = {"id": id, "loop": list(loop), "holes": [list(h) for h in (holes or [])]}
        if extrude:
            r["extrude_hint"] = dict({"end": "BLIND"}, **extrude)
        if revolve:
            r["revolve_hint"] = dict({"angle": 360.0}, **revolve)
        if note:
            r["note"] = note
        self.regions.append(r)

    # ---- ref resolution -------------------------------------------------
    def _split(self, ref):
        eid, _, part = ref.partition(".")
        if eid not in self.entities:
            raise KeyError("%s: unknown entity '%s'" % (self.id, eid))
        return self.entities[eid], part

    def is_point_ref(self, ref):
        e, part = self._split(ref)
        return bool(part) or e["type"] == "point"

    def point_of(self, ref):
        e, part = self._split(ref)
        if e["type"] == "point" and not part:
            return e["at"]
        key = part or "center"
        if key not in e or key in ("radius",):
            raise KeyError("%s: '%s' has no point '%s'" % (self.id, ref, key))
        return e[key]

    def curve(self, ref):
        e, part = self._split(ref)
        if part:
            raise KeyError("%s: expected a curve, got point ref '%s'" % (self.id, ref))
        return e

    # ---- verification ---------------------------------------------------
    def _dist_to_curve(self, p, e):
        if e["type"] == "line":
            return g.point_line_distance(p, e["start"], e["end"])
        if e["type"] in ("circle", "arc"):
            return abs(g.dist(p, e["center"]) - e["radius"])
        return g.dist(p, e["at"])

    def _length(self, e):
        if e["type"] == "line":
            return g.dist(e["start"], e["end"])
        return e["radius"]

    def residual(self, c):
        t, refs, v = c["type"], c["refs"], c.get("value")
        if t == "COINCIDENT":
            a, b = refs
            pa, pb = self.is_point_ref(a), self.is_point_ref(b)
            if pa and pb:
                return g.dist(self.point_of(a), self.point_of(b))
            if pa:
                return self._dist_to_curve(self.point_of(a), self.curve(b))
            if pb:
                return self._dist_to_curve(self.point_of(b), self.curve(a))
            raise ValueError("COINCIDENT between two curves is not supported")
        if t == "CONCENTRIC":
            return g.dist(self.point_of(refs[0]), self.point_of(refs[1]))
        if t == "TANGENT":
            e1, e2 = self.curve(refs[0]), self.curve(refs[1])
            if e1["type"] == "line":
                e1, e2 = e2, e1
            if e2["type"] == "line":
                return abs(g.point_line_distance(e1["center"], e2["start"], e2["end"]) - e1["radius"])
            d = g.dist(e1["center"], e2["center"])
            r1, r2 = e1["radius"], e2["radius"]
            return min(abs(d - (r1 + r2)), abs(d - abs(r1 - r2)))
        if t in ("PARALLEL", "PERPENDICULAR"):
            l1, l2 = self.curve(refs[0]), self.curve(refs[1])
            ang = g.line_angle_deg(l1["start"], l1["end"], l2["start"], l2["end"])
            target = 90.0 if t == "PERPENDICULAR" else 0.0
            return min(abs(ang - target), abs(180.0 - ang - target))
        if t == "EQUAL":
            return abs(self._length(self.curve(refs[0])) - self._length(self.curve(refs[1])))
        if t == "MIDPOINT":
            p, l = self.point_of(refs[0]), self.curve(refs[1])
            m = ((l["start"][0] + l["end"][0]) / 2, (l["start"][1] + l["end"][1]) / 2)
            return g.dist(p, m)
        if t in ("HORIZONTAL", "VERTICAL"):
            if len(refs) == 2:
                d = g.sub(self.point_of(refs[1]), self.point_of(refs[0]))
            else:
                l = self.curve(refs[0])
                d = g.sub(l["end"], l["start"])
            return abs(d[1] if t == "HORIZONTAL" else d[0])
        if t == "FIX":
            return g.dist(self.point_of(refs[0]), v)
        if t == "RADIUS":
            return abs(self.curve(refs[0])["radius"] - v)
        if t == "DIAMETER":
            return abs(2 * self.curve(refs[0])["radius"] - v)
        if t == "LENGTH":
            return abs(self._length(self.curve(refs[0])) - v)
        if t == "DISTANCE":
            a, b = refs
            if c.get("direction"):
                d = g.sub(self.point_of(b), self.point_of(a))
                return abs(abs(d[0] if c["direction"] == "horizontal" else d[1]) - v)
            if self.is_point_ref(a) and self.is_point_ref(b):
                return abs(g.dist(self.point_of(a), self.point_of(b)) - v)
            if self.is_point_ref(a):
                a, b = b, a
            # curve a, point b: distance point->line, or gap between concentric arcs
            ea = self.curve(a)
            if self.is_point_ref(b):
                return abs(self._dist_to_curve(self.point_of(b), ea) - v)
            eb = self.curve(b)
            if ea["type"] == "line" and eb["type"] == "line":  # parallel lines
                return abs(g.point_line_distance(eb["start"], ea["start"], ea["end"]) - v)
            return abs(abs(ea["radius"] - eb["radius"]) - v)
        if t == "ANGLE":
            l1, l2 = self.curve(refs[0]), self.curve(refs[1])
            ang = g.line_angle_deg(l1["start"], l1["end"], l2["start"], l2["end"])
            return min(abs(ang - v), abs(180.0 - ang - v))
        raise ValueError("unknown constraint type %s" % t)

    def verify(self):
        """[(constraint, residual)] for every constraint."""
        return [(c, self.residual(c)) for c in self.constraints]

    # ---- structural validation -----------------------------------------
    def _endpoints(self, eid):
        e = self.entities[eid]
        if e["type"] == "circle":
            return None
        if e["type"] == "point":
            raise ValueError("point '%s' cannot be part of a loop" % eid)
        return e["start"], e["end"]

    def loop_error(self, loop):
        """None if the entity chain closes, else a message."""
        if len(loop) == 1:
            return None if self._endpoints(loop[0]) is None else "single open curve"
        ends = [self._endpoints(i) for i in loop]
        if any(e is None for e in ends):
            return "a full circle cannot be chained with other curves"
        # walk the chain, flipping curves as needed
        cur = None
        for k, (s, e) in enumerate(ends):
            if cur is None:
                nxt_s, nxt_e = ends[1]
                if min(g.dist(e, nxt_s), g.dist(e, nxt_e)) < TOL:
                    cur, first = e, s
                elif min(g.dist(s, nxt_s), g.dist(s, nxt_e)) < TOL:
                    cur, first = s, e
                else:
                    return "gap after %s" % loop[0]
                continue
            if g.dist(cur, s) < TOL:
                cur = e
            elif g.dist(cur, e) < TOL:
                cur = s
            else:
                return "gap before %s" % loop[k]
        return None if g.dist(cur, first) < TOL else "loop does not close"

    # ---- region interior point -----------------------------------------
    def loop_polyline(self, loop, step_deg=3.0):
        """Loop sampled as a closed polygon (arcs split every step_deg)."""
        ents = [self.entities[i] for i in loop]
        if len(ents) == 1 and ents[0]["type"] == "circle":
            e = ents[0]
            n = int(360 / step_deg)
            return [g.polar(e["center"], e["radius"], 2 * math.pi * k / n) for k in range(n)]
        ends = (ents[1]["start"], ents[1]["end"])
        fwd = min(g.dist(ents[0]["end"], p) for p in ends) < TOL
        cur = ents[0]["start"] if fwd else ents[0]["end"]
        pts = []
        for e in ents:
            forward = g.dist(cur, e["start"]) < TOL
            if e["type"] == "arc":
                n = max(2, int(math.degrees(e["sweep"]) / step_deg))
                angs = [e["start_angle"] + e["sweep"] * k / n for k in range(n)]
                if not forward:
                    angs = [e["start_angle"] + e["sweep"] * (1 - k / n) for k in range(n)]
                pts += [g.polar(e["center"], e["radius"], a) for a in angs]
            else:
                pts.append(e["start"] if forward else e["end"])
            cur = e["end"] if forward else e["start"]
        return pts

    @staticmethod
    def _in_poly(p, poly):
        x, y, inside = p[0], p[1], False
        for i in range(len(poly)):
            (x1, y1), (x2, y2) = poly[i - 1], poly[i]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
        return inside

    @staticmethod
    def _dist_to_poly(p, poly):
        best = float("inf")
        for i in range(len(poly)):
            a, b = poly[i - 1], poly[i]
            ab = g.sub(b, a)
            L2 = ab[0] ** 2 + ab[1] ** 2
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / L2))
            best = min(best, g.dist(p, (a[0] + t * ab[0], a[1] + t * ab[1])))
        return best

    def inside_point(self, region, grid=16, refine=3):
        """Point strictly inside the region (outer loop minus holes), as far
        from every edge as a coarse grid + local refinement finds. Cached per
        region. Returns (point, clearance)."""
        key = id(region)
        cache = self.__dict__.setdefault("_inside_cache", {})
        if key in cache:
            return cache[key]
        outer = self.loop_polyline(region["loop"])
        holes = [self.loop_polyline(h) for h in region["holes"]]
        polys = [outer] + holes

        def score(p):
            if not self._in_poly(p, outer) or any(self._in_poly(p, h) for h in holes):
                return -1.0
            return min(self._dist_to_poly(p, pl) for pl in polys)

        xs, ys = [p[0] for p in outer], [p[1] for p in outer]
        x0, y0, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
        cands = [(x0 + w * (i + 0.5) / grid, y0 + h * (j + 0.5) / grid)
                 for i in range(grid) for j in range(grid)]
        best, best_d = None, -1.0
        for p in cands:
            d = score(p)
            if d > best_d:
                best, best_d = p, d
        step_x, step_y = w / grid, h / grid
        for _ in range(refine):
            if best is None:
                break
            for p in [(best[0] + dx * step_x / 2, best[1] + dy * step_y / 2)
                      for dx in (-1, 0, 1) for dy in (-1, 0, 1)]:
                d = score(p)
                if d > best_d:
                    best, best_d = p, d
            step_x, step_y = step_x / 2, step_y / 2
        cache[key] = (best, best_d)
        return cache[key]

    def curves_crossing(self, region, eps=0.01):
        """Non-construction curves (outside the region's own loops) that pass
        through its interior. Onshape splits a sketch face along every curve,
        so a region must not be crossed for one inside point to select it whole."""
        own = set(region["loop"]) | {i for h in region["holes"] for i in h}
        outer = self.loop_polyline(region["loop"])
        holes = [self.loop_polyline(h) for h in region["holes"]]
        polys = [outer] + holes
        hits = []
        for e in self.entities.values():
            if e["id"] in own or e["construction"] or e["type"] == "point":
                continue
            if e["type"] == "line":
                pts = [(e["start"][0] + (e["end"][0] - e["start"][0]) * k / 40,
                        e["start"][1] + (e["end"][1] - e["start"][1]) * k / 40) for k in range(41)]
            elif e["type"] == "circle":
                pts = [g.polar(e["center"], e["radius"], 2 * math.pi * k / 120) for k in range(120)]
            else:
                pts = [g.polar(e["center"], e["radius"], e["start_angle"] + e["sweep"] * k / 60)
                       for k in range(61)]
            for q in pts:
                if (self._in_poly(q, outer) and not any(self._in_poly(q, h) for h in holes)
                        and min(self._dist_to_poly(q, pl) for pl in polys) > eps):
                    hits.append(e["id"])
                    break
        return hits

    def validate(self):
        errs = []
        if self.plane not in PLANES:
            errs.append("unknown plane %s" % self.plane)
        for e in self.entities.values():
            if e["type"] == "arc":
                for k in ("start", "mid", "end"):
                    if abs(g.dist(e["center"], e[k]) - e["radius"]) > TOL:
                        errs.append("arc %s: %s not on circle" % (e["id"], k))
        for c in self.constraints:
            spec = CONSTRAINTS.get(c["type"])
            if not spec:
                errs.append("unknown constraint %s" % c["type"])
                continue
            arity = spec[0] if isinstance(spec[0], tuple) else (spec[0],)
            if len(c["refs"]) not in arity:
                errs.append("%s expects %s refs, got %s" % (c["type"], arity, c["refs"]))
            if c.get("direction") and (c["type"] != "DISTANCE"
                                       or c["direction"] not in ("horizontal", "vertical")):
                errs.append("bad direction %s on %s" % (c["direction"], c["type"]))
            if spec[1] and "value" not in c:
                errs.append("%s %s needs a value" % (c["type"], c["refs"]))
            for ref in c["refs"]:
                try:
                    self._split(ref)
                except KeyError as ex:
                    errs.append(str(ex))
        for r in self.regions:
            for loop in [r["loop"]] + r["holes"]:
                missing = [i for i in loop if i not in self.entities]
                if missing:
                    errs.append("region %s: unknown %s" % (r["id"], missing))
                    r["_broken"] = True
                    continue
                if any(self.entities[i]["construction"] for i in loop):
                    errs.append("region %s uses construction geometry" % r["id"])
                msg = self.loop_error(loop)
                if msg:
                    errs.append("region %s: %s" % (r["id"], msg))
                    r["_broken"] = True
            if not r.pop("_broken", False):
                p, clear = self.inside_point(r)
                if p is None or clear < MIN_CLEARANCE:
                    errs.append("region %s: no interior point with %.2f mm clearance"
                                % (r["id"], MIN_CLEARANCE))
                cut = self.curves_crossing(r)
                if cut:
                    errs.append("region %s is split by %s: Onshape would make several faces"
                                % (r["id"], cut))
            h = r.get("extrude_hint")
            if h:
                if h.get("op") not in EXTRUDE_OPS:
                    errs.append("region %s: bad op %s" % (r["id"], h.get("op")))
                if h.get("end") not in END_TYPES:
                    errs.append("region %s: bad end %s" % (r["id"], h.get("end")))
                if h["end"] != "THROUGH_ALL" and "height" not in h:
                    errs.append("region %s: missing height" % r["id"])
            rv = r.get("revolve_hint")
            if rv:
                errs += self._revolve_errors(r, rv)
        return ["%s: %s" % (self.id, m) for m in errs]

    def _revolve_errors(self, r, rv):
        """The axis must be a line of this sketch and the region must lie on
        one side of it (touching is fine): otherwise the revolve self-intersects."""
        errs = []
        if rv.get("op") not in EXTRUDE_OPS:
            errs.append("region %s: bad op %s" % (r["id"], rv.get("op")))
        ax = self.entities.get(rv.get("axis"))
        if not ax or ax["type"] != "line":
            return errs + ["region %s: revolve axis '%s' is not a line of this sketch" % (r["id"], rv.get("axis"))]
        if not 0 < float(rv.get("angle", 360)) <= 360:
            errs.append("region %s: revolve angle must be in (0, 360]" % r["id"])
        a, b = ax["start"], ax["end"]
        side = set()
        for loop in [r["loop"]] + r["holes"]:
            for p in self.loop_polyline(loop):
                cr = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
                if abs(cr) > 1e-6:
                    side.add(cr > 0)
        if len(side) > 1:
            errs.append("region %s crosses its revolve axis %s" % (r["id"], ax["id"]))
        return errs

    # ---- export ---------------------------------------------------------
    def to_dict(self):
        ents = []
        for e in self.entities.values():
            o = {"id": e["id"], "type": e["type"], "construction": e["construction"]}
            if e["type"] == "point":
                o["at"] = _pt(e["at"])
            elif e["type"] == "line":
                o.update(start=_pt(e["start"]), end=_pt(e["end"]))
            elif e["type"] == "circle":
                o.update(center=_pt(e["center"]), radius=_r(e["radius"]))
            else:
                o.update(center=_pt(e["center"]), radius=_r(e["radius"]),
                         start=_pt(e["start"]), mid=_pt(e["mid"]), end=_pt(e["end"]),
                         direction="ccw")
            ents.append(o)
        cons = []
        for c in self.constraints:
            o = dict(c)
            if isinstance(o.get("value"), Param):
                o["param"] = o["value"].name
            if isinstance(o.get("value"), (tuple, list)):
                o["value"] = _pt(o["value"])
            elif isinstance(o.get("value"), float):
                o["value"] = _r(o["value"])
            cons.append(o)
        regions = []
        for r in self.regions:
            p, _ = self.inside_point(r)
            o = dict(r, inside_point=_pt(p))
            h = r.get("extrude_hint")
            if h and isinstance(h.get("height"), Param):
                o["extrude_hint"] = dict(h, height=float(h["height"]), height_param=h["height"].name)
            regions.append(o)
        d = {"id": self.id, "name": self.name, "plane": self.plane, "offset": _r(float(self.offset)),
             "entities": ents, "constraints": cons, "regions": regions}
        if self.notes:
            d["notes"] = self.notes
        return d


class Design:
    def __init__(self, part, parameters, sketches, reference=None, notes=None, origin=None,
                 material=None, target_mass_g=None, build=None):
        """reference: dict(image=<path relative to design.py>, px_per_mm=float,
        origin_px=(x, y)) used only for the SVG overlay.
        origin: dict(feature=<what sits at (0, 0)>, evidence=[<dimensions that
        start there>]) recording why the origin was chosen.
        material: dict(name=..., density=<kg/m3>); target_mass_g: mass printed
        on the drawing. Both optional, used by the FeatureScript validation.
        build: ordered list of "<sketch id>/<region id>" steps, the feature
        order in CAD. Every region with an extrude_hint appears exactly once;
        the first step is NEW and no ADD/REMOVE comes before it."""
        if not origin or not origin.get("feature") or not origin.get("evidence"):
            raise ValueError("Design needs origin={'feature': ..., 'evidence': [...]}")
        self.origin = origin
        self.part = part
        self.parameters = parameters
        self.sketches = sketches
        self.reference = reference
        self.notes = notes or []
        self.material = material
        self.target_mass_g = target_mass_g
        self.build = build or []

    def validate(self):
        errs = []
        names = set(self.parameters)
        for s in self.sketches:
            used = [c["value"].name for c in s.constraints if isinstance(c.get("value"), Param)]
            used += [r["extrude_hint"]["height"].name for r in s.regions
                     if isinstance(r.get("extrude_hint", {}).get("height"), Param)]
            for n in used:
                if n not in names:
                    errs.append("%s: param '%s' not in the parameter table" % (s.id, n))
        errs += self._validate_build()
        if self.material and not (self.material.get("name") and self.material.get("density")):
            errs.append("material needs name and density (kg/m3)")
        ids = [s.id for s in self.sketches]
        if len(ids) != len(set(ids)):
            errs.append("duplicate sketch ids")
        for s in self.sketches:
            errs += s.validate()
        return errs

    AXES = {"X", "Y", "Z"}

    def flat_build(self):
        """Build steps in execution order, pattern groups expanded."""
        out = []
        for step in self.build:
            if isinstance(step, dict):
                out += list(step.get("circular_pattern", {}).get("steps", []))
            else:
                out.append(step)
        return out

    def _validate_build(self):
        hinted = {"%s/%s" % (s.id, r["id"]): r.get("extrude_hint") or r.get("revolve_hint")
                  for s in self.sketches for r in s.regions
                  if r.get("extrude_hint") or r.get("revolve_hint")}
        if not self.build:
            return ["build: missing (ordered list of 'sketch/region' steps)"]
        errs = []
        for step in self.build:
            if not isinstance(step, dict):
                continue
            cp = step.get("circular_pattern")
            if not cp or set(step) != {"circular_pattern"}:
                errs.append("build: unknown step %r" % step)
                continue
            if cp.get("axis") not in self.AXES:
                errs.append("build: circular_pattern axis must be one of X, Y, Z (world, through the origin)")
            if not isinstance(cp.get("count"), int) or cp["count"] < 2:
                errs.append("build: circular_pattern count must be an integer >= 2")
            if not 0 < float(cp.get("angle", 360)) <= 360:
                errs.append("build: circular_pattern angle must be in (0, 360]")
            first = (cp.get("steps") or [None])[0]
            if first not in hinted or hinted[first]["op"] != "NEW":
                errs.append("build: a circular_pattern group must start with a NEW step "
                            "(it builds the seed body that gets patterned and then united)")
        flat = self.flat_build()
        for step in flat:
            if step not in hinted:
                errs.append("build: '%s' is not a region with an extrude/revolve hint" % step)
        dup = {x for x in flat if flat.count(x) > 1}
        if dup:
            errs.append("build: repeated steps %s" % sorted(dup))
        missing = [k for k in hinted if k not in flat]
        if missing:
            errs.append("build: regions with hints not built %s" % missing)
        ops = [hinted[x]["op"] for x in flat if x in hinted]
        if ops and ops[0] != "NEW":
            errs.append("build: first step must be NEW, got %s" % ops[0])
        return errs

    def to_dict(self):
        d = {"schema": SCHEMA, "part": self.part, "units": "mm",
             "origin": self.origin, "notes": self.notes,
             "parameters": {k: float(v) for k, v in self.parameters.items()},
             "sketches": [s.to_dict() for s in self.sketches],
             "build": self.build}
        if self.reference:
            d["reference"] = {"image": self.reference["image"]}
        if self.material:
            d["material"] = self.material
        if self.target_mass_g is not None:
            d["target_mass_g"] = self.target_mass_g
        return d
