"""Assemble the static site (GitHub Pages): front end, mirrored settings, and the upstream results.

  python -m pipeline.build_site --data build/data --out build/site

- settings.json  front-end mirror of config/settings.yaml (analysis, scope, topic labels)
- results/       every number the page shows, computed by pipeline/results.py with the site's SQL
Nothing is loaded from another origin at runtime and there is no in-browser database: the browser only adds up
the pair a visitor picks (site/js/compute.js).
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

from . import results, settings as settings_mod
from .settings import ROOT

STATIC = ["index.html", "css/app.css", "js/metrics.js", "js/compute.js", "js/data.js", "js/app.js", "js/boot.js"]


def front_settings(cfg: dict) -> dict:
    return {
        "analysis": cfg["analysis"],
        "scope": cfg["scope"],
        "topics": {"pap_major_topics": {str(k): v for k, v in cfg["topics"]["pap_major_topics"].items()},
                   "crs_inherit_scope": cfg["topics"]["crs_inherit_scope"]},
    }


def build_site(data: Path, out: Path, cfg: dict):
    if out.exists():
        shutil.rmtree(out)
    for rel in STATIC:
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "site" / rel, out / rel)
    (out / "settings.json").write_text(json.dumps(front_settings(cfg), indent=1))
    (out / ".nojekyll").write_text("")
    results.write(results.build(data), out / "results")


def main(argv=None) -> int:
    cfg = settings_mod.load()
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=cfg["output"]["data_dir"])
    ap.add_argument("--out", default="build/site")
    args = ap.parse_args(argv)
    build_site(Path(args.data), Path(args.out), cfg)
    print(f"site: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
