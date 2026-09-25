#!/usr/bin/env python3
"""Fast path: design.py -> validated sketches.json + review.png -> .fs + params,
then print the exact write_featurescript_feature arguments.

usage:
  build.py designs/<part> [--no-review]
      -> one JSON line: {"call": {...MCP args...}, "needs_part_studio": bool, "timings": {...}}
  build.py record designs/<part> --element E --fs-element F --feature X
                  --status OK --message "VALIDATION OK: mass ..." --t0 <epoch> [--note ...]
      -> stores ids in designs/<part>/onshape.json (reuse next time) and appends runs.jsonl

Ids live in designs/<part>/onshape.json; the document in designs/onshape.json.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(HERE, "..", "..", "design-to-sketch", "scripts", "run.py")
GEN = os.path.join(HERE, "json_to_fs.py")


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def build(a):
    part_dir = os.path.abspath(a.part_dir)
    part = os.path.basename(part_dir)
    t = {}
    t0 = time.time()
    cmd = [sys.executable, RUN, os.path.join(part_dir, "design.py"), "--quiet"]
    if not a.no_review:
        cmd.append("--review")
    r = subprocess.run(cmd, capture_output=True, text=True)
    t["sketches_s"] = round(time.time() - t0, 2)
    if r.returncode:
        sys.exit("design-to-sketch failed:\n" + r.stdout[-3000:] + r.stderr[-2000:])
    t1 = time.time()
    js = os.path.join(part_dir, "out", "sketches.json")
    r = subprocess.run([sys.executable, GEN, js], capture_output=True, text=True)
    t["featurescript_s"] = round(time.time() - t1, 2)
    if r.returncode:
        sys.exit("json_to_fs failed:\n" + r.stdout + r.stderr)
    doc = load(os.path.join(part_dir, "..", "onshape.json"), {})
    ids = load(os.path.join(part_dir, "onshape.json"), {})
    call = {"documentId": doc.get("documentId"), "workspaceId": doc.get("workspaceId"),
            "featureName": part, "fsElementName": "FS " + part,
            "featureScriptPath": os.path.join(part_dir, "out", part + ".fs"),
            "parametersPath": os.path.join(part_dir, "out", "fs_params.json")}
    validate = os.path.join(part_dir, "out", "validate.fs")
    if os.path.exists(validate):
        call["postEvalScriptPath"] = validate
    if ids.get("elementId"):
        call["elementId"] = ids["elementId"]
    for k in ("fsElementId", "featureId"):
        if ids.get(k):
            call[k] = ids[k]
    t["local_total_s"] = round(time.time() - t0, 2)
    out = {"call": call, "needs_part_studio": "elementId" not in call,
           "review": None if a.no_review else os.path.join(part_dir, "out", "review.png"),
           "t0": round(t0, 3), "timings": t}
    print(json.dumps(out))


def record(a):
    part_dir = os.path.abspath(a.part_dir)
    ids_path = os.path.join(part_dir, "onshape.json")
    ids = load(ids_path, {})
    ids.update({k: v for k, v in (("elementId", a.element), ("fsElementId", a.fs_element),
                                  ("featureId", a.feature)) if v})
    with open(ids_path, "w") as f:
        json.dump(ids, f, indent=2)
        f.write("\n")
    pe = json.loads(a.post_eval) if a.post_eval else None
    m = None if pe else re.search(r"mass ([\d.]+) g \(target ([\d.]+) g, delta (-?[\d.]+) %\), bodies (\d+)",
                                  a.message or "")
    runs = os.path.join(part_dir, "runs.jsonl")
    n = sum(1 for _ in open(runs)) + 1 if os.path.exists(runs) else 1
    entry = {"run": n, "date": datetime.date.today().isoformat(), "tool": "sketch-to-featurescript/build.py",
             "element": ids.get("elementId"), "status": a.status,
             "outcome": "ok" if a.status in ("OK", "INFO") and (
                 pe.get("ok") if pe else "VALIDATION OK" in (a.message or "")) else "fail",
             "wall_clock_s": round(time.time() - a.t0, 1) if a.t0 else None,
             "mass_g": pe.get("mass_g") if pe else (float(m.group(1)) if m else None),
             "target_mass_g": pe.get("target_g") if pe else (float(m.group(2)) if m else None),
             "mass_error_pct": pe.get("delta_pct") if pe else (float(m.group(3)) if m else None),
             "bodies": pe.get("bodies") if pe else (int(m.group(4)) if m else None),
             "message": a.message, "note": a.note}
    with open(runs, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(json.dumps(entry))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "record":
        ap = argparse.ArgumentParser(prog="build.py record")
        ap.add_argument("cmd")
        ap.add_argument("part_dir")
        ap.add_argument("--element")
        ap.add_argument("--fs-element")
        ap.add_argument("--feature")
        ap.add_argument("--status", required=True)
        ap.add_argument("--message", default="")
        ap.add_argument("--post-eval", help="the post_eval JSON returned by write_featurescript_feature")
        ap.add_argument("--t0", type=float)
        ap.add_argument("--note")
        record(ap.parse_args())
    else:
        ap = argparse.ArgumentParser(prog="build.py")
        ap.add_argument("part_dir")
        ap.add_argument("--no-review", action="store_true")
        build(ap.parse_args())


if __name__ == "__main__":
    main()
