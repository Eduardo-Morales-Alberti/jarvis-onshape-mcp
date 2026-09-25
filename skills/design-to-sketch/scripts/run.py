#!/usr/bin/env python3
"""Build a design: verify constraints, validate structure, write sketches.json
and SVG overlays (optionally rasterized to PNG with headless Chrome).

usage: run.py designs/<part>/design.py [--png] [--crop xmin,ymin,xmax,ymax] [--zoom N]
                                       [--only S1,S2] [--tag name]
"""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sketchgen import model, svg  # noqa: E402

CHROME = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]


def load_design(path):
    spec = importlib.util.spec_from_file_location("design", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build()


def rasterize(svg_path, size):
    exe = next((shutil.which(c) for c in CHROME if shutil.which(c)), None)
    if not exe:
        print("  (no Chrome found, PNG skipped)")
        return None
    png = svg_path[:-4] + ".png"
    w, h = int(size[0]), int(size[1])
    ffmpeg = shutil.which("ffmpeg")
    # headless Chrome's viewport is shorter than --window-size: render taller, crop after
    shot = png + ".raw.png" if ffmpeg else png
    quiet = dict(check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    profile = tempfile.mkdtemp(prefix="sketchgen-chrome-")  # parallel Chromes must not share one
    subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--user-data-dir=" + profile, "--no-first-run",
                    "--allow-file-access-from-files", "--screenshot=" + shot,
                    "--window-size=%d,%d" % (w, h + (200 if ffmpeg else 0)),
                    "file://" + os.path.abspath(svg_path)], **quiet)
    if ffmpeg:
        subprocess.run([ffmpeg, "-y", "-i", shot, "-vf", "crop=%d:%d:0:0" % (w, h), png], **quiet)
        os.remove(shot)
    return png


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("design")
    ap.add_argument("--png", action="store_true", help="also rasterize SVGs with headless Chrome")
    ap.add_argument("--crop", help="xmin,ymin,xmax,ymax in mm: zoomed view of all sketches")
    ap.add_argument("--zoom", type=float, default=3.0)
    ap.add_argument("--only", help="comma-separated sketch ids for the crop view")
    ap.add_argument("--tag", default="crop", help="file name suffix for the crop view")
    ap.add_argument("--review", action="store_true",
                    help="one contact sheet out/review.png: full overlay + a zoom on every junction")
    ap.add_argument("--quiet", action="store_true", help="only print failures and the summary")
    a = ap.parse_args()

    base = os.path.dirname(os.path.abspath(a.design))
    out = os.path.join(base, "out")
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    d = load_design(a.design)

    # 1. structure
    errs = d.validate()
    for e in errs:
        print("SCHEMA ERROR", e)

    # 2. constraints
    worst, bad = 0.0, 0
    for sk in d.sketches:
        if not a.quiet:
            print("\n== %s (%s plane): %d entities, %d constraints, %d regions" % (
                sk.id, sk.plane, len(sk.entities), len(sk.constraints), len(sk.regions)))
        for c, r in sk.verify():
            ok = r < model.TOL
            bad += not ok
            worst = max(worst, r)
            val = "" if "value" not in c else " = %s" % (c["value"],)
            if not (a.quiet and ok):
                print("  %s %-13s %-40s%s  res=%.2e" % ("ok " if ok else "BAD", c["type"],
                                                       ", ".join(c["refs"]), val, r))

    # 3. outputs
    with open(os.path.join(out, "sketches.json"), "w") as f:
        json.dump(d.to_dict(), f, indent=2)
    written = []
    if a.crop:
        sel = [s for s in d.sketches if not a.only or s.id in a.only.split(",")]
        p = os.path.join(out, "%s.svg" % a.tag)
        crop = tuple(float(x) for x in a.crop.split(","))
        written.append((p, svg.render(d, base, sel, p, crop_mm=crop, zoom=a.zoom)))
    else:
        for sk in d.sketches:
            p = os.path.join(out, "%s.svg" % sk.id)
            written.append((p, svg.render(d, base, [sk], p)))
        p = os.path.join(out, "all.svg")
        written.append((p, svg.render(d, base, d.sketches, p)))
    if a.review:
        p = os.path.join(out, "review.svg")
        written.append((p, svg.review(d, base, d.sketches, p)))
    for p, size in written:
        print("wrote", os.path.relpath(p))
    if a.png or a.review:
        todo = written if a.png else [w for w in written if w[0].endswith("review.svg")]
        with ThreadPoolExecutor(max_workers=8) as pool:
            for png in pool.map(lambda w: rasterize(*w), todo):
                if png:
                    print("wrote", os.path.relpath(png))

    print("\nsummary: %d schema errors, %d failing constraints, worst residual %.2e, %.1f s"
          % (len(errs), bad, worst, time.time() - t0))
    sys.exit(1 if errs or bad else 0)


if __name__ == "__main__":
    main()
