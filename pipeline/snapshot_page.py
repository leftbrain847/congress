"""Build the day's self-contained page (one HTML file, no outside loads) for scripts/snapshot.mjs.

  python -m pipeline.snapshot_page --data build/data --out build/day.html --title "YYYY-MM-DD - Congress"

The same front end as the live site, with the same result files (pipeline/results.py) embedded instead of fetched,
for the chamber/Congress partitions given (default: the 118th Congress, both chambers).
"""
import argparse
import json
import sys
from pathlib import Path

from . import results, settings as settings_mod
from .build_site import front_settings
from .settings import ROOT

SCRIPTS = ["js/metrics.js", "js/compute.js", "js/data.js", "js/app.js"]


def ordinal(n: int) -> str:
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def page(files: dict, cfg: dict, title: str) -> str:
    read = lambda rel: (ROOT / "site" / rel).read_text(encoding="utf-8")
    parts = files["manifest.json"]["partitions"]
    sett = front_settings(cfg)
    sett["scope"] = {**sett["scope"], "default_chamber": "Senate", "default_congress": max(p["congress"] for p in parts)}
    label = " and ".join(f"{ordinal(n)} Congress" for n in sorted({p["congress"] for p in parts})) + \
        " (" + ", ".join(sorted({p["chamber"] for p in parts})) + ")"
    data_json = json.dumps(files, separators=(",", ":")).replace("</", "<\\/")
    sett_json = json.dumps(sett, separators=(",", ":")).replace("</", "<\\/")
    html = read("index.html")
    head_end = html.index("</head>")
    head = html[:head_end].replace("<title>Congress Roll Calls</title>", f"<title>{title}</title>")
    head = head.replace('<link rel="stylesheet" href="css/app.css">', f"<style>\n{read('css/app.css')}\n</style>")
    # One self-contained file: inline scripts and styles only, no network at all.
    head = head.replace(head[head.index("<!-- Content-Security-Policy"):head.index("<style>")],
                        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'; '
                        'style-src \'unsafe-inline\'; img-src data:; base-uri \'none\'">\n')
    body = html[head_end:].split("<script")[0]
    banner = (f'<div class="notice snapshot-note">Day snapshot: the {label}, with the same precomputed results as the live site, '
              'embedded in this page.</div>')
    body = body.replace('<main id="app"', banner + '\n<main id="app"', 1)
    body += f'<script type="application/json" id="snapshot-data">{data_json}</script>\n'
    body += "".join(f"<script>\n{read(s)}\n</script>\n" for s in SCRIPTS)
    body += ('<script>\n(function () {\n'
             '  const files = JSON.parse(document.getElementById("snapshot-data").textContent);\n'
             f'  CG.app.start(CG.createData(files), {sett_json});\n'
             '})();\n</script>\n</body>\n</html>\n')
    return head + body


def main(argv=None) -> int:
    cfg = settings_mod.load()
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=cfg["output"]["data_dir"])
    ap.add_argument("--out", default="build/day.html")
    ap.add_argument("--title", default="Congress Roll Calls")
    ap.add_argument("--congress", type=int, nargs="*", default=[118])
    args = ap.parse_args(argv)
    scope = [(ch, c) for ch in cfg["scope"]["chambers"] for c in args.congress]
    files = results.build(Path(args.data), scope)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(files, cfg, args.title), encoding="utf-8")
    print(f"snapshot page: {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
