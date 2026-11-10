"""Build the day's self-contained page (one HTML file, no outside loads) for scripts/snapshot.mjs.

  python -m pipeline.snapshot_page --data build/data --out build/day.html

The page runs the same front end (site/js/app.js) on a precomputed engine (site/js/engine_static.js). Every stored
answer is produced here by running the site's SQL (site/sql) in Python DuckDB over the built data, for the
chamber/Congress partitions in snapshot_scope (default: the 118th Congress, both chambers).
"""
import argparse
import json
import sys
from pathlib import Path

from . import queries, settings as settings_mod
from .build_site import front_settings
from .settings import ROOT

POS_CHAR = {1: "y", -1: "n", 0: "p"}


def ordinal(n: int) -> str:
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def clean(rows):
    """JSON-safe rows (dates already strings in the data; floats rounded for size)."""
    out = []
    for r in rows:
        o = {}
        for k, v in r.items():
            o[k] = round(v, 4) if isinstance(v, float) else v
        out.append(o)
    return out


def precompute(data: Path, cfg: dict, scope: list[tuple[str, int]]) -> dict:
    con = queries.connect(data)
    t = cfg["analysis"]["contested_threshold"]
    manifest = json.loads((data / "manifest.json").read_text())
    D = {"members": {}, "member": {}, "rollcalls": {}, "rollcall": {}, "split": {}, "crossers": {}, "positions": {},
         "h2h": {"threshold": t, "by_partition": {}}}
    for chamber, congress in scope:
        k = f"{chamber}|{congress}"
        members = clean(queries.run(con, "members", chamber, congress))
        D["members"][k] = members
        for m in members:
            D["member"].setdefault(str(m["icpsr"]), clean(queries.run(con, "member", m["icpsr"])))
        rcs = clean(queries.run(con, "rollcalls", chamber, congress))
        D["rollcalls"][k] = rcs
        D["rollcall"][k], D["split"][k], D["crossers"][k] = {}, {}, {}
        for r in rcs:
            roll = r["rollnumber"]
            [full] = clean(queries.run(con, "rollcall", chamber, congress, roll))
            # Store only what the list row lacks; the engine merges them back.
            D["rollcall"][k][str(roll)] = {f: v for f, v in full.items() if f not in r or r[f] != v}
            D["split"][k][str(roll)] = clean(queries.run(con, "bill_party_split", chamber, congress, roll))
            # Crossers as [icpsr, position]; names come from the members list (party_majority is -position).
            D["crossers"][k][str(roll)] = [[c["icpsr"], c["position"]] for c in queries.run(con, "bill_crossers", chamber, congress, roll)]
        order = [m["icpsr"] for m in sorted(members, key=lambda m: m["icpsr"])]
        idx = {icpsr: i for i, icpsr in enumerate(order)}
        by_roll = {}
        for roll, icpsr, pos in con.execute("SELECT rollnumber, icpsr, position FROM votes WHERE chamber = ? AND congress = ?",
                                            [chamber, congress]).fetchall():
            by_roll.setdefault(roll, ["-"] * len(order))[idx[icpsr]] = POS_CHAR[pos]
        D["positions"][k] = {"order": order, "by_roll": {str(r): "".join(v) for r, v in sorted(by_roll.items())}}
        # Every pair at once, with the h2h.sql definitions (both voted yea or nay; contested = minority_share >= t).
        pairs = con.execute("""
            SELECT a.icpsr, b.icpsr, count(*), count(*) FILTER (WHERE a.position = b.position),
                   count(*) FILTER (WHERE r.minority_share >= $t),
                   count(*) FILTER (WHERE r.minority_share >= $t AND a.position = b.position)
            FROM votes a JOIN votes b ON b.chamber = a.chamber AND b.congress = a.congress AND b.rollnumber = a.rollnumber AND a.icpsr < b.icpsr
            JOIN rollcalls r ON r.chamber = a.chamber AND r.congress = a.congress AND r.rollnumber = a.rollnumber
            WHERE a.chamber = $ch AND a.congress = $c AND a.position <> 0 AND b.position <> 0
            GROUP BY 1, 2""", {"t": t, "ch": chamber, "c": congress}).fetchall()
        # Packed: indices into order (a < b by icpsr), then shared_all, agree_all, shared_contested, agree_contested.
        flat = []
        for a, b, n, ag, nc, ac in sorted(pairs):
            flat += [idx[a], idx[b], n, ag, nc, ac]
        D["h2h"]["by_partition"][k] = {"order": order, "rows": flat}
    keep = {(c, n) for c, n in scope}
    D["manifest"] = {**manifest, "partitions": [p for p in manifest["partitions"] if (p["chamber"], p["congress"]) in keep]}
    cov = json.loads((data / "coverage.json").read_text())
    cov["crs_and_pap_by_partition"] = [r for r in cov["crs_and_pap_by_partition"] if (r["chamber"], r["congress"]) in keep]
    D["coverage"] = cov
    congresses = sorted({n for _, n in scope})
    D["scope_label"] = " and ".join(f"{ordinal(n)} Congress" for n in congresses) + " (" + ", ".join(sorted({c for c, _ in scope})) + ")"
    return D


def page(D: dict, cfg: dict, title: str) -> str:
    read = lambda rel: (ROOT / "site" / rel).read_text(encoding="utf-8")
    sett = front_settings(cfg)
    sett["scope"] = {**sett["scope"], "default_chamber": "Senate",
                     "default_congress": max(p["congress"] for p in D["manifest"]["partitions"])}
    data_json = json.dumps(D, separators=(",", ":")).replace("</", "<\\/")
    sett_json = json.dumps(sett, separators=(",", ":")).replace("</", "<\\/")
    html = read("index.html")
    head_end = html.index("</head>")
    head = html[:head_end]
    head = head.replace("<title>Congress Roll Calls</title>", f"<title>{title}</title>")
    head = head.replace('<link rel="stylesheet" href="css/app.css">', f"<style>\n{read('css/app.css')}\n</style>")
    body = html[head_end:]
    body = body.split("<script")[0]
    body = body.replace('<p class="loading">Starting the in-browser database…</p>', '<p class="loading">Loading…</p>')
    body += (f'<script type="application/json" id="snapshot-data">{data_json}</script>\n'
             f'<script>\n{read("js/metrics.js")}\n</script>\n<script>\n{read("js/app.js")}\n</script>\n'
             f'<script>\n{read("js/engine_static.js")}\n</script>\n'
             '<script>\n(function () {\n'
             '  const D = JSON.parse(document.getElementById("snapshot-data").textContent);\n'
             f'  const settings = {sett_json};\n'
             '  CG.app.start(CG.createStaticEngine(D), settings);\n'
             '})();\n</script>\n</body>\n</html>\n')
    # One self-contained file: inline scripts and styles only, no network at all.
    head = head.replace(
        head[head.index('<!-- Content-Security-Policy'):head.index('<style>')],
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'; '
        'style-src \'unsafe-inline\'; img-src data:; base-uri \'none\'">\n')
    banner = ('<div class="notice snapshot-note">Day snapshot: the ' + D["scope_label"] +
              ', precomputed with the site\'s own queries. The live site computes every Congress in your browser.</div>')
    body = body.replace('<main id="app"', banner + '\n<main id="app"', 1)
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
    D = precompute(Path(args.data), cfg, scope)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(D, cfg, args.title), encoding="utf-8")
    print(f"snapshot page: {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
