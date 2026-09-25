"""Pure-math 2D helpers. Points are (x, y) tuples in mm, angles in radians."""
import math

EPS = 1e-9


def dist(p, q):
    return math.hypot(q[0] - p[0], q[1] - p[1])


def add(p, v):
    return (p[0] + v[0], p[1] + v[1])


def sub(p, q):
    return (p[0] - q[0], p[1] - q[1])


def scale(v, k):
    return (v[0] * k, v[1] * k)


def unit(v):
    n = math.hypot(*v)
    if n < EPS:
        raise ValueError("zero-length vector")
    return (v[0] / n, v[1] / n)


def polar(center, r, angle):
    return (center[0] + r * math.cos(angle), center[1] + r * math.sin(angle))


def angle_of(center, p):
    """Angle of p seen from center, normalized to [0, 2pi)."""
    return math.atan2(p[1] - center[1], p[0] - center[0]) % (2 * math.pi)


def ccw_sweep(a0, a1):
    """Counter-clockwise sweep from angle a0 to a1, in (0, 2pi]."""
    s = (a1 - a0) % (2 * math.pi)
    return s if s > EPS else 2 * math.pi


def circle_circle(c1, r1, c2, r2):
    """Intersection points of two circles (0, 1 or 2 points)."""
    d = dist(c1, c2)
    if d < EPS or d > r1 + r2 + EPS or d < abs(r1 - r2) - EPS:
        return []
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h = math.sqrt(max(r1 * r1 - a * a, 0.0))
    u = unit(sub(c2, c1))
    m = add(c1, scale(u, a))
    if h < EPS:
        return [m]
    n = (-u[1], u[0])
    return [add(m, scale(n, h)), add(m, scale(n, -h))]


def tangent_arc_center(c1, r1, c2, r2, R, external=True, away_from=None):
    """Center of a radius-R arc tangent to circles (c1, r1) and (c2, r2).

    external=True: the arc sits outside both circles (|P-Ci| = R + ri).
    external=False: the arc wraps around both circles (|P-Ci| = R - ri).
    Of the two solutions, returns the one farthest from `away_from` (or the
    first one if not given).
    """
    d1 = R + r1 if external else R - r1
    d2 = R + r2 if external else R - r2
    sols = circle_circle(c1, d1, c2, d2)
    if not sols:
        raise ValueError("no tangent arc of radius %s exists" % R)
    if away_from is None:
        return sols[0]
    return max(sols, key=lambda p: dist(p, away_from))


def tangent_point(c_from, r_from, toward):
    """Point on circle (c_from, r_from) along the ray toward another center."""
    return add(c_from, scale(unit(sub(toward, c_from)), r_from))


def tangent_line(c1, r1, c2, r2, side=1, crossed=False):
    """Tangent points (t1, t2) of a line tangent to both circles.

    side=+1 puts the line on the left of the direction c1 -> c2, -1 on the right.
    crossed=False: external tangent (both circles on the same side of the line,
    the usual "belt" edge). crossed=True: internal tangent (line passes between).
    """
    d = dist(c1, c2)
    rr = r1 + r2 if crossed else r1 - r2
    if d < abs(rr):
        raise ValueError("no such tangent line")
    u = unit(sub(c2, c1))
    cos_t = rr / d
    sin_t = side * math.sqrt(max(1 - cos_t * cos_t, 0.0))
    n = (u[0] * cos_t - u[1] * sin_t, u[1] * cos_t + u[0] * sin_t)
    t1 = add(c1, scale(n, r1))
    t2 = add(c2, scale(n, -r2 if crossed else r2))
    return t1, t2


def regular_polygon(center, n, across_flats=None, circumradius=None, first_vertex_deg=90.0):
    """Vertices of a regular n-gon, counter-clockwise from first_vertex_deg."""
    R = circumradius or (across_flats / 2) / math.cos(math.pi / n)
    a0 = math.radians(first_vertex_deg)
    return [polar(center, R, a0 + 2 * math.pi * k / n) for k in range(n)]


def point_line_distance(p, a, b):
    """Unsigned distance from p to the infinite line through a, b."""
    ab = sub(b, a)
    return abs(ab[0] * (p[1] - a[1]) - ab[1] * (p[0] - a[0])) / math.hypot(*ab)


def line_angle_deg(a, b, c, d):
    """Unsigned angle in [0, 180] between direction a->b and c->d."""
    u, v = unit(sub(b, a)), unit(sub(d, c))
    cosang = max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1]))
    return math.degrees(math.acos(cosang))
