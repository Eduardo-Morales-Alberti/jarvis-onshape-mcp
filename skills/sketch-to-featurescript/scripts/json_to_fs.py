#!/usr/bin/env python3
"""sketches.json (schema sketchgen/1) -> one FeatureScript custom feature.

usage: json_to_fs.py designs/<part>/out/sketches.json
                     [--constraints full|geometric|none] [--only S1,S2] [--no-build]

Writes out/<part>.fs and out/fs_params.json (the `parameters` list for the
plugin's write_featurescript_feature). Pure translation: seeds, constraints,
regions and build order all come from the JSON; nothing is recomputed.
API shapes verified by scripts/probe.fs (see reference/fs-mapping.md).
"""
import argparse
import json
import os
import re
import sys

FS_VERSION = "2909"
PLANES = {  # sketch plane -> (normal, x direction)
    "Top": ((0, 0, 1), (1, 0, 0)),
    "Front": ((0, -1, 0), (1, 0, 0)),
    "Right": ((1, 0, 0), (0, 1, 0)),
}
DIMENSIONAL = {"RADIUS", "DIAMETER", "LENGTH", "DISTANCE", "ANGLE"}
LENGTH_KEY = {"RADIUS", "DIAMETER", "LENGTH", "DISTANCE"}
OPS = {"NEW": "NEW", "ADD": "ADD", "REMOVE": "REMOVE", "INTERSECT": "INTERSECT"}


def num(v):
    s = "%.6f" % v
    s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def vec2(p):
    return "vector(%s, %s) * mm" % (num(p[0]), num(p[1]))


def camel(part):
    words = re.split(r"[^A-Za-z0-9]+", part)
    name = words[0].lower() + "".join(w[:1].upper() + w[1:] for w in words[1:])
    return name if name[:1].isalpha() else "p" + name


def ident(s):
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", s):
        raise ValueError("parameter name '%s' is not a valid FeatureScript identifier" % s)
    return s


def param_kinds(design):
    """angle if any ANGLE constraint uses the parameter, else length."""
    kinds = {k: "length" for k in design["parameters"]}
    for sk in design["sketches"]:
        for c in sk["constraints"]:
            if c.get("param") and c["type"] == "ANGLE":
                kinds[c["param"]] = "angle"
    return kinds


def used_params(design, sketches):
    used = set()
    for sk in sketches:
        for c in sk["constraints"]:
            if c.get("param"):
                used.add(c["param"])
        for r in sk["regions"]:
            hp = r.get("extrude_hint", {}).get("height_param")
            if hp:
                used.add(hp)
    return [k for k in design["parameters"] if k in used]


def entity_fs(var, e):
    cons = ', "construction" : true' if e["construction"] else ""
    if e["type"] == "point":
        return 'skPoint(%s, "%s", { "position" : %s });' % (var, e["id"], vec2(e["at"]))
    if e["type"] == "line":
        return 'skLineSegment(%s, "%s", { "start" : %s, "end" : %s%s });' % (
            var, e["id"], vec2(e["start"]), vec2(e["end"]), cons)
    if e["type"] == "circle":
        return 'skCircle(%s, "%s", { "center" : %s, "radius" : %s * mm%s });' % (
            var, e["id"], vec2(e["center"]), num(e["radius"]), cons)
    if e["type"] == "arc":
        return 'skArc(%s, "%s", { "start" : %s, "mid" : %s, "end" : %s%s });' % (
            var, e["id"], vec2(e["start"]), vec2(e["mid"]), vec2(e["end"]), cons)
    raise ValueError("unknown entity type %s" % e["type"])


def value_fs(c, kinds):
    if c.get("param"):
        return "definition.%s" % ident(c["param"])
    return "%s * %s" % (num(c["value"]), "degree" if c["type"] == "ANGLE" else "mm")


UNSUPPORTED = {"MIDPOINT": "ignored by skSolve (probe.fs): use COINCIDENT + EQUAL distances instead"}


def _near(p, q, tol=1e-6):
    return abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol


def angle_as_distance(sk, c, kinds):
    """ANGLE is silently ignored by skSolve (verified with probes). Rewrite it:
    two lines sharing a vertex, both with a LENGTH constraint, get a DISTANCE
    between their free ends from the law of cosines, as a live expression."""
    ents = {e["id"]: e for e in sk["entities"]}
    l1, l2 = (ents[r] for r in c["refs"])
    shared = [(k1, k2) for k1 in ("start", "end") for k2 in ("start", "end")
              if _near(l1[k1], l2[k2])]
    lengths = {x["refs"][0]: x for x in sk["constraints"] if x["type"] == "LENGTH"}
    if len(shared) != 1 or l1["id"] not in lengths or l2["id"] not in lengths:
        raise ValueError("%s: ANGLE %s is only supported between two lines that share a vertex "
                         "and both carry a LENGTH constraint" % (sk["id"], c["refs"]))
    k1, k2 = shared[0]
    free1 = "%s.%s" % (l1["id"], "end" if k1 == "start" else "start")
    free2 = "%s.%s" % (l2["id"], "end" if k2 == "start" else "start")
    a, b, t = value_fs(lengths[l1["id"]], kinds), value_fs(lengths[l2["id"]], kinds), value_fs(c, kinds)
    expr = "sqrt((%s) * (%s) + (%s) * (%s) - 2 * (%s) * (%s) * cos(%s))" % (a, a, b, b, a, b, t)
    return {"type": "DISTANCE", "refs": [free1, free2], "expr": expr}


def constraint_fs(var, cid, c, kinds, sk=None):
    if c["type"] in UNSUPPORTED:
        raise ValueError("%s: %s is not supported: %s" % (sk["id"] if sk else "?", c["type"],
                                                           UNSUPPORTED[c["type"]]))
    if c["type"] == "ANGLE":
        d = angle_as_distance(sk, c, kinds)
        return ('skConstraint(%s, "%s", { "constraintType" : ConstraintType.DISTANCE, '
                '"localFirst" : "%s", "localSecond" : "%s", "length" : %s }); '
                '// ANGLE %s rewritten (skSolve ignores ANGLE)'
                % (var, cid, d["refs"][0], d["refs"][1], d["expr"], value_fs(c, kinds)))
    parts = ['"constraintType" : ConstraintType.%s' % c["type"],
             '"localFirst" : "%s"' % c["refs"][0]]
    if len(c["refs"]) > 1:
        parts.append('"localSecond" : "%s"' % c["refs"][1])
    if c["type"] in LENGTH_KEY:
        parts.append('"length" : %s' % value_fs(c, kinds))
    elif c["type"] == "ANGLE":
        parts.append('"angle" : %s' % value_fs(c, kinds))
    if c.get("direction"):
        parts.append('"direction" : DimensionDirection.%s' % c["direction"].upper())
    return 'skConstraint(%s, "%s", { %s });' % (var, cid, ", ".join(parts))


def region_query(sk, region, select):
    """Face of a sketch region. 'edges' (default) picks the region face whose
    boundary passes through the midpoint of every curve of the region and has
    exactly that many edges; it follows the solved geometry, so it survives
    parameter changes. 'point' uses the static inside_point (debug only)."""
    if select == "point":
        return ('qContainsPoint(qSketchRegion(id + "%s", false), planeToWorld(%s, %s))'
                % (sk["id"], plane_var(sk), vec2(region["inside_point"])))
    own = region["loop"] + [i for h in region["holes"] for i in h]
    return 'regionFace(id + "%s", "%s", [%s])' % (
        sk["id"], region["id"], ", ".join('"%s"' % i for i in own))


# Lambda (not a top-level function: those failed to resolve from the feature
# body). Sketch edges and region-face edges are separate topology in Onshape,
# so the match is geometric: curve midpoints on the face boundary + edge count.
REGION_HELPER = """        const regionFace = function(sketchId, name, bounds)
        {
            var mids = [];
            for (var e in bounds)
                mids = append(mids, evEdgeTangentLine(context, { "edge" : sketchEntityQuery(sketchId, EntityType.EDGE, e), "parameter" : 0.5 }).origin);
            var found = [];
            for (var f in evaluateQuery(context, qSketchRegion(sketchId, false)))
            {
                const edges = qAdjacent(f, AdjacencyType.EDGE, EntityType.EDGE);
                if (size(evaluateQuery(context, edges)) != size(bounds))
                    continue;
                var ok = true;
                for (var p in mids)
                    if (evDistance(context, { "side0" : edges, "side1" : p }).distance > 1e-7 * meter)
                        ok = false;
                if (ok)
                    found = append(found, f);
            }
            if (size(found) != 1)
                throw regenError("region " ~ name ~ " matched " ~ toString(size(found)) ~ " faces (expected 1)");
            return found[0];
        };"""


def extrude_fs(step_no, sk, region, kinds, select="edges"):
    h = region["extrude_hint"]
    fields = ['"entities" : ' + region_query(sk, region, select),
              '"operationType" : NewBodyOperationType.%s' % OPS[h["op"]]]
    if h["end"] == "THROUGH_ALL":
        fields += ['"endBound" : BoundingType.THROUGH_ALL', '"symmetric" : true']
    else:
        depth = ("definition.%s" % ident(h["height_param"]) if h.get("height_param")
                 else "%s * mm" % num(h["height"]))
        fields += ['"endBound" : BoundingType.BLIND', '"depth" : %s' % depth]
        if h["end"] == "SYMMETRIC":
            fields.append('"symmetric" : true')
    if h["op"] != "NEW":
        fields.append('"defaultScope" : true')
    return 'extrude(context, id + "e%02d_%s_%s", { %s });' % (
        step_no, sk["id"], region["id"], ",\n                    ".join(fields))


def revolve_fs(step_no, sk, region, select="edges"):
    """std revolve about a line of the same sketch (construction lines are
    queryable as edges: verified on speedcad-t3-2), so the axis follows the
    solved geometry and the parameters."""
    h = region["revolve_hint"]
    fields = ['"entities" : ' + region_query(sk, region, select),
              '"axis" : sketchEntityQuery(id + "%s", EntityType.EDGE, "%s")' % (sk["id"], h["axis"]),
              '"operationType" : NewBodyOperationType.%s' % OPS[h["op"]]]
    # std revolve defaults to a full turn; the RevolveType enum is not exported by
    # onshape/std/geometry.fs ("Variable RevolveType not found"), so partial
    # angles are refused until verified with a probe.
    if float(h.get("angle", 360)) < 360:
        raise ValueError("%s/%s: partial revolve angles are not supported yet" % (sk["id"], region["id"]))
    if h["op"] != "NEW":
        fields.append('"defaultScope" : true')
    return 'revolve(context, id + "e%02d_%s_%s", { %s });' % (
        step_no, sk["id"], region["id"], ",\n                    ".join(fields))


def plane_var(sk):
    return "pl_" + sk["id"]


def generate(design, mode="full", only=None, build=True, select="edges"):
    sketches = [s for s in design["sketches"] if not only or s["id"] in only]
    kinds = param_kinds(design)
    params = used_params(design, sketches)
    part = design["part"]
    ftype = camel(part)
    out = ["FeatureScript %s;" % FS_VERSION,
           'import(path : "onshape/std/geometry.fs", version : "%s.0");' % FS_VERSION,
           "",
           "// Generated by sketch-to-featurescript/json_to_fs.py from %s (schema %s)."
           % (part, design["schema"]),
           "// Do not edit by hand: fix sketches.json or the generator and regenerate.",
           ""]
    for k in params:
        v = design["parameters"][k]
        if kinds[k] == "angle":
            out.append("const PB_%s = { (degree) : [0, %s, 360] } as AngleBoundSpec;"
                       % (ident(k), num(v)))
        else:
            out.append("const PB_%s = { (millimeter) : [0.01, %s, 10000] } as LengthBoundSpec;"
                       % (ident(k), num(v)))
    out += ["",
            'annotation { "Feature Type Name" : "%s" }' % part,
            "export const %s = defineFeature(function(context is Context, id is Id, definition is map)"
            % ftype,
            "    precondition", "    {"]
    for k in params:
        fn = "isAngle" if kinds[k] == "angle" else "isLength"
        out += ['        annotation { "Name" : "%s" }' % k,
                "        %s(definition.%s, PB_%s);" % (fn, k, k)]  # PB_ prefix: never clashes with std (LENGTH_BOUNDS...)
    check = build and design.get("material") and design.get("target_mass_g")
    if check:
        out += ['        annotation { "Name" : "Validate against drawing mass", "Default" : true }',
                "        definition.validateMass is boolean;"]
    out += ["    }", "    {", "        const mm = millimeter;"]
    for sk in sketches:
        n, x = PLANES[sk["plane"]]
        off = float(sk.get("offset", 0) or 0)
        o = tuple(num(off * c) for c in n)
        out.append("        const %s = plane(vector(%s, %s, %s) * mm, vector(%d, %d, %d), vector(%d, %d, %d));"
                   % ((plane_var(sk),) + o + n + x))
    for sk in sketches:
        var = "s_" + sk["id"]
        out += ["", "        // ---- %s (%s plane)%s" % (sk["id"], sk["plane"],
                                                        ": " + sk["notes"] if sk.get("notes") else ""),
                '        const %s = newSketchOnPlane(context, id + "%s", { "sketchPlane" : %s });'
                % (var, sk["id"], plane_var(sk))]
        out += ["        " + entity_fs(var, e) for e in sk["entities"]]
        n = 0
        for c in sk["constraints"]:
            n += 1
            if mode == "none" or (mode == "geometric" and c["type"] in DIMENSIONAL):
                continue
            out.append("        " + constraint_fs(var, "c%d_%s" % (n, c["type"].lower()), c, kinds, sk))
        out.append("        skSolve(%s);" % var)
    if build:
        regions = {"%s/%s" % (s["id"], r["id"]): (s, r) for s in sketches for r in s["regions"]}
        out.append("")
        out.append("        // ---- build order (from sketches.json 'build')")
        if select == "edges":
            out += REGION_HELPER.split("\n")
        n = 0

        def step_fs(step):
            nonlocal n
            n += 1
            if step not in regions:
                return None, None  # sketch filtered out by --only
            s, r = regions[step]
            fid = "e%02d_%s_%s" % (n, s["id"], r["id"])
            code = (revolve_fs(n, s, r, select) if r.get("revolve_hint")
                    else extrude_fs(n, s, r, kinds, select))
            return fid, code

        for step in design["build"]:
            if isinstance(step, dict):
                cp = step["circular_pattern"]
                seeds = []
                for child in cp["steps"]:
                    fid, code = step_fs(child)
                    if code:
                        out.append("        " + code)
                        seeds.append(fid)
                if seeds:
                    seed_q = "qUnion([%s])" % ", ".join('qCreatedBy(id + "%s", EntityType.BODY)' % f for f in seeds)
                    out += PATTERN.format(n=n, seed=seed_q, count=cp["count"], angle=num(cp.get("angle", 360)),
                                          axis={"X": "1, 0, 0", "Y": "0, 1, 0", "Z": "0, 0, 1"}[cp["axis"]],
                                          full="true" if float(cp.get("angle", 360)) >= 360 else "false"
                                          ).split("\n")
            else:
                fid, code = step_fs(step)
                if code:
                    out.append("        " + code)
        mat = design.get("material")
        if mat:
            out += ['        setProperty(context, { "entities" : qCreatedBy(id, EntityType.BODY),',
                    '                    "propertyType" : PropertyType.MATERIAL,',
                    '                    "value" : material("%s", %s * kilogram / meter ^ 3) });'
                    % (mat["name"], num(mat["density"]))]
        if check:
            out += VALIDATION.format(density=num(mat["density"]),
                                     target=num(design["target_mass_g"])).split("\n")
    out += ["    });", ""]
    src = "\n".join(out)
    fs_params = ([{"id": "validateMass", "type": "boolean", "value": True}] if check else []) + [
                 {"id": k, "type": "quantity",
                  "value": "%s %s" % (num(design["parameters"][k]),
                                      "deg" if kinds[k] == "angle" else "mm")}
                 for k in params]
    return ftype, src, fs_params


# One-call verdict: the upload response carries the mass as an INFO notice,
# or a WARNING when it is off the drawing by more than 0.5 % or bodies != 1.
VALIDATION = """        const solids = qBodyType(qCreatedBy(id, EntityType.BODY), BodyType.SOLID);
        const nBodies = size(evaluateQuery(context, solids));
        const massG = evVolume(context, {{ "entities" : solids }}) * {density} * kilogram / meter ^ 3 / kilogram * 1000;
        const deltaPct = (massG - {target}) / {target} * 100;
        const summary = "mass " ~ toString(roundToPrecision(massG, 3)) ~ " g (target {target} g, delta "
                        ~ toString(roundToPrecision(deltaPct, 3)) ~ " %), bodies " ~ toString(nBodies);
        if (definition.validateMass && (abs(deltaPct) > 0.5 || nBodies != 1))
            reportFeatureWarning(context, id, "VALIDATION FAILED: " ~ summary);
        else
            reportFeatureInfo(context, id, "VALIDATION OK: " ~ summary);"""


VALIDATE_LAMBDA = """function(context is Context, queries)
{{
    // Post-regen check run by write_featurescript_feature (postEvalScriptPath).
    const s = qBodyType(qEverything(EntityType.BODY), BodyType.SOLID);
    const n = size(evaluateQuery(context, s));
    if (n == 0)
        return {{ "ok" : false, "bodies" : 0, "target_g" : {target} }};
    const m = evVolume(context, {{ "entities" : s }}) * {density} * kilogram / meter ^ 3 / kilogram * 1000;
    const d = (m - {target}) / {target} * 100;
    return {{ "ok" : abs(d) <= 0.5 && n == 1, "mass_g" : roundToPrecision(m, 3), "target_g" : {target},
             "delta_pct" : roundToPrecision(d, 3), "bodies" : n }};
}}
"""


# Circular pattern of the seed body (built by the group's first, NEW step and the
# ADDs that merged into it), then everything the feature made is united.
PATTERN = """        {{
            // circular pattern x{count} about the world axis ({axis}) through the origin
            const step = {angle} * degree / ({full} ? {count} : ({count} - 1));
            var transforms = [];
            var names = [];
            for (var k = 1; k < {count}; k += 1)
            {{
                transforms = append(transforms, rotationAround(line(vector(0, 0, 0) * meter, vector({axis})), k * step));
                names = append(names, "i" ~ toString(k));
            }}
            opPattern(context, id + "p{n:02d}", {{ "entities" : qBodyType({seed}, BodyType.SOLID),
                        "transforms" : transforms, "instanceNames" : names }});
            opBoolean(context, id + "u{n:02d}", {{ "tools" : qBodyType(qCreatedBy(id, EntityType.BODY), BodyType.SOLID),
                        "operationType" : BooleanOperationType.UNION }});
        }}"""


def check(src):
    for o, c in ("{}", "()", "[]"):
        if src.count(o) != src.count(c):
            raise ValueError("unbalanced %s%s in generated source" % (o, c))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("--constraints", choices=["full", "geometric", "none"], default="full")
    ap.add_argument("--only", help="comma-separated sketch ids")
    ap.add_argument("--no-build", action="store_true", help="sketches only, no extrudes")
    ap.add_argument("--select", choices=["edges", "point"], default="edges",
                    help="region selection: bounding edges (parametric) or inside_point")
    a = ap.parse_args()
    design = json.load(open(a.json))
    if design.get("schema") != "sketchgen/1":
        sys.exit("unsupported schema %s" % design.get("schema"))
    if not design.get("build"):
        sys.exit("sketches.json has no 'build' list: regenerate it with design-to-sketch")
    only = a.only.split(",") if a.only else None
    ftype, src, params = generate(design, a.constraints, only, not a.no_build, a.select)
    check(src)
    out = os.path.dirname(os.path.abspath(a.json))
    fs_path = os.path.join(out, "%s.fs" % design["part"])
    with open(fs_path, "w") as f:
        f.write(src)
    if design.get("material") and design.get("target_mass_g"):
        with open(os.path.join(out, "validate.fs"), "w") as f:
            f.write(VALIDATE_LAMBDA.format(density=num(design["material"]["density"]),
                                           target=num(design["target_mass_g"])))
    with open(os.path.join(out, "fs_params.json"), "w") as f:
        json.dump({"featureType": ftype, "parameters": params}, f, indent=2)
    print("featureType:", ftype)
    print("wrote", os.path.relpath(fs_path), "(%d lines)" % src.count("\n"))
    print("wrote", os.path.relpath(os.path.join(out, "fs_params.json")), "(%d inputs)" % len(params))


if __name__ == "__main__":
    main()
