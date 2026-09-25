"""SVG rendering of sketches, optionally overlaid on the reference image."""
import math
import os
import struct

from . import geometry as g

PALETTE = ["#d62728", "#1f77b4", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#e377c2"]


def image_size(path):
    """(width, height) of a PNG or JPEG, stdlib only."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + seg_len
    raise ValueError("unsupported image: %s" % path)


class View:
    """mm -> px transform (y flipped)."""

    def __init__(self, px_per_mm, origin_px, size):
        self.s, self.o, self.size = px_per_mm, origin_px, size

    def __call__(self, p):
        return (self.o[0] + p[0] * self.s, self.o[1] - p[1] * self.s)

    def f(self, p):
        x, y = self(p)
        return "%.2f,%.2f" % (x, y)


def _bbox(sketches):
    xs, ys = [], []
    for s in sketches:
        for e in s.entities.values():
            if e["type"] == "point":
                pts, r = [e["at"]], 0
            elif e["type"] == "line":
                pts, r = [e["start"], e["end"]], 0
            else:
                pts, r = [e["center"]], e["radius"]
            for p in pts:
                xs += [p[0] - r, p[0] + r]
                ys += [p[1] - r, p[1] + r]
    return min(xs), min(ys), max(xs), max(ys)


def make_view(design, base_dir, sketches):
    ref = design.reference
    if ref:
        img = os.path.join(base_dir, ref["image"])
        return View(ref["px_per_mm"], ref["origin_px"], image_size(img)), img
    x0, y0, x1, y1 = _bbox(sketches)
    s, m = 8.0, 40
    size = (int((x1 - x0) * s + 2 * m), int((y1 - y0) * s + 2 * m))
    return View(s, (m - x0 * s, m + y1 * s), size), None


def _arc_cmd(v, e, forward):
    end = e["end"] if forward else e["start"]
    r = e["radius"] * v.s
    large = 1 if e["sweep"] > math.pi else 0
    sweep_flag = 0 if forward else 1  # ccw in math == counter-clockwise on screen (y flipped)
    return "A %.2f %.2f 0 %d %d %s" % (r, r, large, sweep_flag, v.f(end))


def _circle_path(v, c, r):
    x, y = v(c)
    r *= v.s
    return "M %.2f %.2f a %.2f %.2f 0 1 0 %.2f 0 a %.2f %.2f 0 1 0 %.2f 0 Z" % (
        x - r, y, r, r, 2 * r, r, r, -2 * r)


def _loop_path(v, sk, loop):
    ents = [sk.entities[i] for i in loop]
    if len(ents) == 1 and ents[0]["type"] == "circle":
        return _circle_path(v, ents[0]["center"], ents[0]["radius"])
    first, second = ents[0], ents[1]
    ends2 = (second["start"], second["end"])
    fwd = min(g.dist(first["end"], p) for p in ends2) < 1e-6
    cur = first["start"] if fwd else first["end"]
    out = ["M " + v.f(cur)]
    for e in ents:
        forward = g.dist(cur, e["start"]) < 1e-6
        if e["type"] == "line":
            cur = e["end"] if forward else e["start"]
            out.append("L " + v.f(cur))
        else:
            out.append(_arc_cmd(v, e, forward))
            cur = e["end"] if forward else e["start"]
    return " ".join(out) + " Z"


def _entity_svg(v, e, color, sw):
    dash = ' stroke-dasharray="6 4"' if e["construction"] else ""
    col = "#777" if e["construction"] else color
    w = sw * 0.6 if e["construction"] else sw
    t = "<title>%s (%s)</title>" % (e["id"], e["type"])
    if e["type"] == "point":
        x, y = v(e["at"])
        return '<circle cx="%.2f" cy="%.2f" r="2.5" fill="%s">%s</circle>' % (x, y, col, t)
    if e["type"] == "line":
        return '<path d="M %s L %s" stroke="%s" stroke-width="%.2f" vector-effect="non-scaling-stroke" fill="none"%s>%s</path>' % (
            v.f(e["start"]), v.f(e["end"]), col, w, dash, t)
    if e["type"] == "circle":
        return '<path d="%s" stroke="%s" stroke-width="%.2f" vector-effect="non-scaling-stroke" fill="none"%s>%s</path>' % (
            _circle_path(v, e["center"], e["radius"]), col, w, dash, t)
    ends = "".join('<circle cx="%.2f" cy="%.2f" r="2" fill="%s"/>' % (v(p) + (col,))
                   for p in (e["start"], e["end"]))
    return '<path d="M %s %s" stroke="%s" stroke-width="%.2f" vector-effect="non-scaling-stroke" fill="none"%s>%s</path>%s' % (
        v.f(e["start"]), _arc_cmd(v, e, True), col, w, dash, t, ends)


def _labels(v, sk, color):
    """Radius / diameter callouts at each curve's mid point, centers as crosses."""
    out = []
    for c in sk.constraints:
        if c["type"] not in ("RADIUS", "DIAMETER"):
            continue
        e = sk.entities[c["refs"][0]]
        p = e.get("mid") or g.polar(e["center"], e["radius"], math.radians(35))
        x, y = v(p)
        txt = ("R%g" if c["type"] == "RADIUS" else "Ø%g") % c["value"]
        out.append('<text x="%.1f" y="%.1f" font-size="11" fill="%s" font-family="sans-serif">%s</text>'
                   % (x + 3, y - 3, color, txt))
    for e in sk.entities.values():
        if e["type"] in ("arc", "circle") and not e["construction"]:
            x, y = v(e["center"])
            out.append('<path d="M %.1f %.1f h 8 M %.1f %.1f v 8" stroke="%s" stroke-width="0.8"/>'
                       % (x - 4, y, x, y - 4, color))
    return out


def _content(design, base_dir, sketches, v, img, out_path, sw):
    """SVG elements for the reference image + every sketch (no header)."""
    W, H = v.size
    parts = []
    if img:
        href = os.path.relpath(img, os.path.dirname(os.path.abspath(out_path)))
        parts.append('<image href="%s" x="0" y="0" width="%d" height="%d" opacity="0.45"/>' % (href, W, H))
    for k, sk in enumerate(sketches):
        color = PALETTE[k % len(PALETTE)]
        parts.append('<g id="%s">' % sk.id)
        for r in sk.regions:
            d = " ".join(_loop_path(v, sk, l) for l in [r["loop"]] + r["holes"])
            parts.append('<path d="%s" fill="%s" fill-opacity="0.12" fill-rule="evenodd" stroke="none">'
                         '<title>region %s %s</title></path>' % (d, color, r["id"], r.get("extrude_hint", "")))
        parts += [_entity_svg(v, e, color, sw) for e in sk.entities.values()]
        parts += _labels(v, sk, color)
        parts.append("</g>")
    x, y = v((0, 0))
    parts.append('<path d="M %.1f %.1f h 24 M %.1f %.1f v -24" stroke="#000" stroke-width="1.2"/>' % (x, y, x, y))
    return parts


def render(design, base_dir, sketches, out_path, crop_mm=None, zoom=1.0):
    """Write an SVG with the given sketches. crop_mm=(xmin, ymin, xmax, ymax)
    restricts the view to that region (in sketch mm) and scales it by zoom."""
    v, img = make_view(design, base_dir, sketches)
    W, H = v.size
    vb = (0, 0, W, H)
    if crop_mm:
        (ax, ay), (bx, by) = v((crop_mm[0], crop_mm[3])), v((crop_mm[2], crop_mm[1]))
        vb = (ax, ay, bx - ax, by - ay)
    out_w, out_h = vb[2] * zoom, vb[3] * zoom
    sw = 1.6 / max(zoom, 1) ** 0.5
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
             'width="%d" height="%d" viewBox="%.2f %.2f %.2f %.2f">' % ((out_w, out_h) + tuple(vb)),
             '<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="white"/>' % tuple(vb)]
    parts += _content(design, base_dir, sketches, v, img, out_path, sw)
    legend = " | ".join("%s: %s" % (sk.id, PALETTE[k % len(PALETTE)]) for k, sk in enumerate(sketches))
    parts.append('<text x="%.1f" y="%.1f" font-size="%.1f" font-family="sans-serif">%s: %s</text>'
                 % (vb[0] + 6, vb[1] + 14 / zoom, 12 / zoom, design.part, legend))
    parts.append("</svg>")
    with open(out_path, "w") as f:
        f.write("\n".join(parts))
    return out_w, out_h


def junctions(sketches, merge_mm=0.5):
    """Points worth zooming on: every endpoint shared by two non-construction
    curves (COINCIDENT between point refs), labelled with the curves meeting."""
    pts = []
    for sk in sketches:
        for c in sk.constraints:
            if c["type"] != "COINCIDENT" or not all("." in r for r in c["refs"]):
                continue
            ids = [r.split(".")[0] for r in c["refs"]]
            if any(sk.entities[i]["construction"] or sk.entities[i]["type"] == "point" for i in ids):
                continue
            p = sk.point_of(c["refs"][0])
            tangent = any(t["type"] == "TANGENT" and set(t["refs"]) == set(ids) for t in sk.constraints)
            label = "%s %s%s%s" % (sk.id.split("_")[0], ids[0], "~" if tangent else "/", ids[1])
            for q in pts:
                if g.dist(q["p"], p) < merge_mm:
                    break
            else:
                pts.append({"p": p, "label": label})
    return pts


def review(design, base_dir, sketches, out_path, half_mm=6.0, tile=250, width=1280):
    """One contact sheet: the full overlay on top, then a zoom tile on every
    junction (~ tangent, / plain coincident). One image = one review read."""
    v, img = make_view(design, base_dir, sketches)
    W, H = v.size
    scale = width / W
    main_h = H * scale
    pts = junctions(sketches)
    cols = max(1, width // (tile + 6))
    rows = (len(pts) + cols - 1) // cols
    total_h = main_h + rows * (tile + 24) + 10
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
             'width="%d" height="%d">' % (width, total_h),
             '<rect width="100%" height="100%" fill="white"/>',
             "<defs><g id=\"content\">"]
    parts += _content(design, base_dir, sketches, v, img, out_path, 1.6)
    parts.append("</g></defs>")
    parts.append('<svg x="0" y="0" width="%d" height="%.1f" viewBox="0 0 %d %d"><use href="#content"/></svg>'
                 % (width, main_h, W, H))
    for n, j in enumerate(pts):
        cx, cy = v(j["p"])
        h = half_mm * v.s
        x = (n % cols) * (tile + 6) + 3
        y = main_h + 10 + (n // cols) * (tile + 24)
        parts.append('<svg x="%d" y="%.1f" width="%d" height="%d" viewBox="%.2f %.2f %.2f %.2f">'
                     '<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="white"/>'
                     '<use href="#content"/></svg>'
                     % (x, y, tile, tile, cx - h, cy - h, 2 * h, 2 * h, cx - h, cy - h, 2 * h, 2 * h))
        parts.append('<rect x="%d" y="%.1f" width="%d" height="%d" fill="none" stroke="#999"/>' % (x, y, tile, tile))
        parts.append('<text x="%d" y="%.1f" font-size="12" font-family="sans-serif">%d. %s</text>'
                     % (x + 2, y + tile + 15, n + 1, j["label"]))
    parts.append('<text x="6" y="14" font-size="12" font-family="sans-serif">%s: %d junctions '
                 '(~ tangent, / coincident), zoom +/-%g mm</text>' % (design.part, len(pts), half_mm))
    parts.append("</svg>")
    with open(out_path, "w") as f:
        f.write("\n".join(parts))
    return width, total_h
