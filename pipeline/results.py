"""Compute everything upstream: turn the parquet build into the small JSON files the site loads.

  python -m pipeline.results --data build/data --out build/site/results

Every number is computed here with the site's SQL (site/sql) in Python DuckDB. The browser only aggregates the
pair a visitor picks (site/js/compute.js), because precomputing every pair x every topic would be ~40 MB per
House Congress. Files:
  manifest.json, coverage.json
  {chamber}/{congress}/members.json     members (members.sql)
  {chamber}/{congress}/rollcalls.json   {"rows": rollcalls.sql, "split": {roll: [[party, yea, nay, not_voting]]},
                                         "crossers": {roll: [[icpsr, position]]}}
  {chamber}/{congress}/positions.json   {"order": [icpsr...], "by_roll": {roll: "y"/"n"/"p"/"-" per member}}
  members/{icpsr}.json                  every Congress a member served (member.sql)
"""
import argparse
import json
import sys
from pathlib import Path

import duckdb

from . import queries, settings as settings_mod

POS_CHAR = {1: "y", -1: "n", 0: "p"}


def clean(rows):
    return [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in rows]


def partition_files(con, chamber: str, congress: int) -> dict:
    members = clean(queries.run(con, "members", chamber, congress))
    rows = clean(queries.run(con, "rollcalls", chamber, congress))
    split, crossers = {}, {}
    for r in rows:
        roll = r["rollnumber"]
        split[str(roll)] = [[s["party"], s["yea"], s["nay"], s["not_voting"]]
                            for s in queries.run(con, "bill_party_split", chamber, congress, roll)]
        crossers[str(roll)] = [[c["icpsr"], c["position"]] for c in queries.run(con, "bill_crossers", chamber, congress, roll)]
    order = sorted(m["icpsr"] for m in members)
    idx = {icpsr: i for i, icpsr in enumerate(order)}
    by_roll = {}
    for roll, icpsr, pos in con.execute("SELECT rollnumber, icpsr, position FROM votes WHERE chamber = ? AND congress = ?",
                                        [chamber, congress]).fetchall():
        by_roll.setdefault(roll, ["-"] * len(order))[idx[icpsr]] = POS_CHAR[pos]
    base = f"{chamber}/{congress}"
    return {
        f"{base}/members.json": members,
        f"{base}/rollcalls.json": {"rows": rows, "split": split, "crossers": crossers},
        f"{base}/positions.json": {"order": order, "by_roll": {str(r): "".join(v) for r, v in sorted(by_roll.items())}},
    }


def build(data: Path, scope: list[tuple[str, int]] | None = None) -> dict:
    """Return {relative path: JSON-able object} for the partitions in scope (default: every partition)."""
    data = Path(data)
    con = duckdb.connect()
    con.execute(f"CREATE TABLE members AS SELECT * FROM read_parquet('{str(data / 'members.parquet').replace(chr(39), chr(39) * 2)}')")
    manifest = json.loads((data / "manifest.json").read_text())
    parts = manifest["partitions"]
    if scope is not None:
        keep = set(scope)
        parts = [p for p in parts if (p["chamber"], p["congress"]) in keep]
    files = {}
    for p in parts:
        pcon = queries.connect_partition(data, p["chamber"], p["congress"])
        files.update(partition_files(pcon, p["chamber"], p["congress"]))
        pcon.close()
    keep = {(p["chamber"], p["congress"]) for p in parts}
    icpsrs = sorted({i for (i,) in con.execute("SELECT DISTINCT icpsr FROM members").fetchall()} if scope is None else
                    {m["icpsr"] for path, obj in files.items() if path.endswith("/members.json") for m in obj})
    for icpsr in icpsrs:
        files[f"members/{icpsr}.json"] = clean(queries.run(con, "member", icpsr))
    files["manifest.json"] = {
        "generated_at": manifest["generated_at"], "sources": manifest["sources"],
        "partitions": [{k: p[k] for k in ("chamber", "congress", "rollcall_count", "member_count", "first_date", "last_date")}
                       for p in parts],
    }
    cov = json.loads((data / "coverage.json").read_text())
    cov["crs_and_pap_by_partition"] = [r for r in cov["crs_and_pap_by_partition"] if (r["chamber"], r["congress"]) in keep]
    files["coverage.json"] = cov
    return files


def write(files: dict, out: Path):
    out = Path(out)
    for rel, obj in files.items():
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")


def main(argv=None) -> int:
    cfg = settings_mod.load()
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=cfg["output"]["data_dir"])
    ap.add_argument("--out", default="build/site/results")
    args = ap.parse_args(argv)
    files = build(Path(args.data))
    write(files, Path(args.out))
    print(f"results: {len(files)} files -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
