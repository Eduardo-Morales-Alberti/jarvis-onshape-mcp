"""Tests for the design-to-sketch / sketch-to-featurescript skills: every example
design builds, validates, satisfies its constraints and generates FeatureScript;
plus the generator rules learned against Onshape (ANGLE rewrite, MIDPOINT refusal)."""

import importlib.util
import json
import pathlib
import sys

import pytest

SKILLS = pathlib.Path(__file__).resolve().parents[2] / "skills"
sys.path.insert(0, str(SKILLS / "design-to-sketch" / "scripts"))

from sketchgen import Design, Params, Sketch  # noqa: E402
from sketchgen import model  # noqa: E402


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


json_to_fs = _load(SKILLS / "sketch-to-featurescript" / "scripts" / "json_to_fs.py", "json_to_fs")
EXAMPLES = sorted((SKILLS / "design-to-sketch" / "examples").glob("*/design.py"))


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.parent.name)
def test_example_builds_validates_and_generates(path):
    design = _load(path, "design_" + path.parent.name.replace("-", "_")).build()
    assert design.validate() == []
    for sk in design.sketches:
        for c, r in sk.verify():
            assert r < model.TOL, (sk.id, c)
    data = json.loads(json.dumps(design.to_dict()))
    assert data["schema"] == "sketchgen/1" and data["build"]
    ftype, src, params = json_to_fs.generate(data)
    json_to_fs.check(src)
    assert f"export const {ftype} = defineFeature" in src
    assert "ConstraintType.ANGLE" not in src and "ConstraintType.MIDPOINT" not in src
    ids = {p["id"] for p in params}
    assert "validateMass" in ids


def test_examples_cover_the_feature_types():
    srcs = {p.parent.name: json_to_fs.generate(json.loads(json.dumps(
        _load(p, "d_" + p.parent.name.replace("-", "_")).build().to_dict())))[1] for p in EXAMPLES}
    assert "revolve(" in srcs["speedcad-t3-12"]
    assert "opPattern" in srcs["t4scad-05"] and "opPattern" in srcs["t4scad-08"]
    assert "plane(vector(0, 0, -11.660254) * mm" in srcs["t4scad-08"]


def _two_rays(angle_value=60.0):
    P = Params({"side": 10.0, "ang": angle_value})
    sk = Sketch("S1")
    sk.line("a", (0, 0), (0, 10), construction=True)
    sk.line("b", (0, 0), (-8.660254, 5), construction=True)
    sk.constrain("FIX", "a.start", value=(0, 0))
    sk.constrain("COINCIDENT", "b.start", "a.start")
    sk.constrain("LENGTH", "a", value=P["side"])
    sk.constrain("LENGTH", "b", value=P["side"])
    sk.constrain("ANGLE", "a", "b", value=P["ang"])
    return P, sk


def test_angle_is_rewritten_as_law_of_cosines_distance():
    P, sk = _two_rays()
    sk.circle("c", (0, 0), 3)
    sk.constrain("RADIUS", "c", value=3.0)
    sk.region("r", ["c"], extrude={"height": 1.0, "op": "NEW"})
    data = json.loads(json.dumps(Design("p", P, [sk], build=["S1/r"],
                                        origin={"feature": "o", "evidence": ["e"]}).to_dict()))
    _, src, _ = json_to_fs.generate(data)
    line = next(l for l in src.splitlines() if "ANGLE" in l and "rewritten" in l)
    assert "ConstraintType.DISTANCE" in line and "cos(definition.ang)" in line
    assert '"localFirst" : "a.end", "localSecond" : "b.end"' in line


def test_midpoint_is_refused():
    sk = Sketch("S1")
    sk.line("l", (0, 0), (10, 0))
    sk.point("m", (5, 0))
    sk.constrain("MIDPOINT", "m", "l")
    with pytest.raises(ValueError, match="MIDPOINT is not supported"):
        json_to_fs.constraint_fs("s", "c1", sk.constraints[0], {}, {"id": "S1"})


def test_region_crossed_by_another_curve_is_rejected():
    sk = Sketch("S1")
    sk.circle("big", (0, 0), 10)
    sk.circle("cut", (8, 0), 5)
    sk.region("r", ["big"], extrude={"height": 1.0, "op": "NEW"})
    assert any("split by ['cut']" in e for e in sk.validate())


def test_revolve_region_must_not_cross_its_axis():
    sk = Sketch("S1", plane="Front")
    sk.line("ax", (0, -5), (0, 5), construction=True)
    sk.line("l0", (-2, -2), (2, -2))
    sk.line("l1", (2, -2), (2, 2))
    sk.line("l2", (2, 2), (-2, 2))
    sk.line("l3", (-2, 2), (-2, -2))
    sk.region("r", ["l0", "l1", "l2", "l3"], revolve={"axis": "ax", "op": "NEW"})
    assert any("crosses its revolve axis" in e for e in sk.validate())


def test_build_rules():
    sk = Sketch("S1")
    sk.circle("c", (0, 0), 3)
    sk.region("r", ["c"], extrude={"height": 1.0, "op": "ADD"})
    d = Design("p", {}, [sk], build=["S1/r"], origin={"feature": "o", "evidence": ["e"]})
    assert any("first step must be NEW" in e for e in d.validate())
    d = Design("p", {}, [sk], build=[{"circular_pattern": {"steps": ["S1/r"], "axis": "W", "count": 1}}],
               origin={"feature": "o", "evidence": ["e"]})
    errs = " ".join(d.validate())
    assert "axis must be one of X, Y, Z" in errs and "count must be an integer >= 2" in errs


def test_parameter_bounds_never_clash_with_std():
    P = Params({"length": 30.0})
    sk = Sketch("S1")
    sk.circle("c", (0, 0), 3)
    sk.region("r", ["c"], extrude={"height": P["length"], "op": "NEW"})
    data = json.loads(json.dumps(Design("p", P, [sk], build=["S1/r"],
                                        origin={"feature": "o", "evidence": ["e"]}).to_dict()))
    _, src, _ = json_to_fs.generate(data)
    assert "const PB_length" in src and "LENGTH_BOUNDS" not in src
