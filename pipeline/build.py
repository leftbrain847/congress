"""Build partitioned parquet + manifest.json from a raw directory (fetched sources or the committed fixture).

  python -m pipeline.build --raw fixture/raw --out build/data
  python -m pipeline.build --raw build/raw   --out build/data

Output:
  {out}/members.parquet                                     every member-Congress row (House and Senate)
  {out}/votes/chamber={c}/congress={n}/votes.parquet         chamber, congress, rollnumber, icpsr, position
  {out}/rollcalls/chamber={c}/congress={n}/rollcalls.parquet  one row per roll call, with counts and topics
  {out}/coverage.json                                        topic coverage per chamber/Congress, parse report
  {out}/manifest.json                                        the list of files the site may load
position: 1 = yea, -1 = nay, 0 = present / not voting (Voteview cast codes mapped in config/settings.yaml).
"""
import argparse
import datetime as dt
import gzip
import json
import re
import sys
from pathlib import Path

import duckdb

from . import pap, settings as settings_mod, topics

FILE_RE = re.compile(r"^([HS])(\d{3})_votes\.csv(\.gz)?$")
CHAMBER = {"H": "House", "S": "Senate"}

ROLLCALL_FIELDS = [
    ("congress", "SMALLINT"), ("chamber", "VARCHAR"), ("rollnumber", "INTEGER"), ("date", "VARCHAR"),
    ("session", "SMALLINT"), ("bill_number", "VARCHAR"), ("vote_question", "VARCHAR"), ("vote_desc", "VARCHAR"),
    ("dtl_desc", "VARCHAR"), ("vote_result", "VARCHAR"), ("majority_requirement", "VARCHAR"),
    ("yea_count", "INTEGER"), ("nay_count", "INTEGER"),
    ("nominate_mid_1", "DOUBLE"), ("nominate_mid_2", "DOUBLE"),
    ("nominate_spread_1", "DOUBLE"), ("nominate_spread_2", "DOUBLE"),
    ("crs_policy_area", "VARCHAR"), ("crs_policy_area_resolved", "VARCHAR"), ("crs_source", "VARCHAR"),
    ("pap_majortopic", "SMALLINT"), ("pap_subtopic", "SMALLINT"),
    ("yea_n", "INTEGER"), ("nay_n", "INTEGER"), ("not_voting_n", "INTEGER"), ("minority_share", "DOUBLE"),
]


def find(raw: Path, table: str, name: str) -> Path | None:
    for cand in (raw / "voteview" / table / name, raw / "voteview" / table / f"{name}.gz"):
        if cand.exists():
            return cand
    return None


def partitions(raw: Path, cfg: dict) -> list[tuple[str, int]]:
    out = []
    for p in sorted((raw / "voteview" / "votes").glob("*_votes.csv*")):
        m = FILE_RE.match(p.name)
        if m:
            chamber, congress = CHAMBER[m.group(1)], int(m.group(2))
            if chamber in cfg["scope"]["chambers"] and cfg["scope"]["congress_min"] <= congress <= cfg["scope"]["congress_max"]:
                out.append((chamber, congress))
    return sorted(out)


def read_json(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def sql_path(p: Path) -> str:
    return str(p).replace("'", "''")


def cast_case(cfg: dict) -> str:
    cc = cfg["cast_codes"]
    lst = lambda xs: ", ".join(str(int(x)) for x in xs)
    return (f"CASE WHEN cast_code IN ({lst(cc['yea'])}) THEN 1 WHEN cast_code IN ({lst(cc['nay'])}) THEN -1 "
            f"WHEN cast_code IN ({lst(cc['not_voting'])}) THEN 0 END")


def build(raw: Path, out: Path, cfg: dict) -> dict:
    raw, out = Path(raw), Path(out)
    parts = partitions(raw, cfg)
    if not parts:
        raise SystemExit(f"no votes files under {raw}/voteview/votes")
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()

    parties_file = find(raw, "parties", "HSall_parties.csv")
    con.execute(f"""CREATE TABLE parties AS SELECT party_code::INTEGER AS party_code, any_value(party_name) AS party_name
                    FROM read_csv('{sql_path(parties_file)}') GROUP BY 1""")

    known = {int(k) for k in cfg["topics"]["pap_major_topics"]}
    pap_file = raw / "pap" / "rcv.csv"
    pap_file = pap_file if pap_file.exists() else raw / "pap" / "rcv.csv.gz"
    pap_codes, pap_report = pap.read(pap_file, cfg["sources"]["pap_encoding"], known)

    con.execute("""CREATE TABLE members (congress SMALLINT, chamber VARCHAR, icpsr INTEGER, bioname VARCHAR,
        party_code INTEGER, party_name VARCHAR, state_abbrev VARCHAR, district_code INTEGER, bioguide_id VARCHAR,
        born INTEGER, died INTEGER, nominate_dim1 DOUBLE, nominate_dim2 DOUBLE)""")
    rollcalls, missing = [], []
    for chamber, congress in parts:
        prefix = f"{chamber[0]}{congress:03d}"
        mfile, vfile, rfile = (find(raw, "members", f"{prefix}_members.csv"), find(raw, "votes", f"{prefix}_votes.csv"),
                               find(raw, "rollcalls", f"{prefix}_rollcalls.json"))
        if not (mfile and rfile):
            missing.append(prefix)
            continue
        con.execute(f"""INSERT INTO members SELECT congress, chamber, icpsr, bioname, m.party_code, p.party_name,
                state_abbrev, district_code, bioguide_id, born, died, nominate_dim1, nominate_dim2
            FROM read_csv('{sql_path(mfile)}', types={{'born':'INTEGER','died':'INTEGER','district_code':'INTEGER',
                  'nominate_dim1':'DOUBLE','nominate_dim2':'DOUBLE','bioguide_id':'VARCHAR'}}) m
            LEFT JOIN parties p USING (party_code)
            WHERE chamber = '{chamber}'""")
        vdir = out / "votes" / f"chamber={chamber}" / f"congress={congress}"
        vdir.mkdir(parents=True, exist_ok=True)
        # Only members of this chamber: the votes file also carries the President's positions.
        con.execute(f"""CREATE OR REPLACE TABLE v AS
            SELECT '{chamber}' AS chamber, {congress}::SMALLINT AS congress, rollnumber::INTEGER AS rollnumber,
                   icpsr::INTEGER AS icpsr, ({cast_case(cfg)})::TINYINT AS position
            FROM read_csv('{sql_path(vfile)}') r
            WHERE chamber = '{chamber}' AND icpsr IN (SELECT icpsr FROM members WHERE congress = {congress} AND chamber = '{chamber}')
              AND ({cast_case(cfg)}) IS NOT NULL
            ORDER BY rollnumber, icpsr""")
        con.execute(f"COPY v TO '{sql_path(vdir / 'votes.parquet')}' (FORMAT parquet, COMPRESSION zstd)")
        counts = {row[0]: row[1:] for row in con.execute("""SELECT rollnumber, count(*) FILTER (WHERE position = 1),
                    count(*) FILTER (WHERE position = -1), count(*) FILTER (WHERE position = 0) FROM v GROUP BY 1""").fetchall()}
        for r in read_json(rfile):
            if r.get("chamber") != chamber:
                continue
            rec = {k: r.get(k) for k, _ in ROLLCALL_FIELDS if k in r}
            rec["congress"], rec["chamber"] = congress, chamber
            yea, nay, nv = counts.get(r["rollnumber"], (0, 0, 0))
            rec.update(yea_n=yea, nay_n=nay, not_voting_n=nv,
                       minority_share=(min(yea, nay) / (yea + nay)) if yea + nay else None)
            rec["pap_majortopic"], rec["pap_subtopic"] = pap_codes.get((congress, chamber, r["rollnumber"]), (None, None))
            rollcalls.append(rec)

    dupes = con.execute("SELECT count(*) FROM (SELECT 1 FROM members GROUP BY congress, chamber, icpsr HAVING count(*) > 1)").fetchone()[0]
    if dupes:
        raise SystemExit(f"members: {dupes} member(s) listed twice in one chamber and Congress; agreement counts would double")
    rollcalls = topics.resolve_crs(rollcalls, cfg["topics"]["crs_inherit_scope"])
    cols = ", ".join(f"{k} {t}" for k, t in ROLLCALL_FIELDS)
    con.execute(f"CREATE TABLE rollcalls ({cols})")
    con.executemany(f"INSERT INTO rollcalls VALUES ({', '.join('?' for _ in ROLLCALL_FIELDS)})",
                    [[r.get(k) for k, _ in ROLLCALL_FIELDS] for r in rollcalls])

    manifest_parts = []
    for chamber, congress in parts:
        if f"{chamber[0]}{congress:03d}" in missing:
            continue
        rel = f"rollcalls/chamber={chamber}/congress={congress}/rollcalls.parquet"
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        con.execute(f"""COPY (SELECT * FROM rollcalls WHERE chamber = '{chamber}' AND congress = {congress} ORDER BY rollnumber)
                        TO '{sql_path(out / rel)}' (FORMAT parquet, COMPRESSION zstd)""")
        vrel = f"votes/chamber={chamber}/congress={congress}/votes.parquet"
        n_rc, first, last = con.execute(f"SELECT count(*), min(date), max(date) FROM rollcalls WHERE chamber = '{chamber}' AND congress = {congress}").fetchone()
        n_members = con.execute(f"SELECT count(*) FROM members WHERE chamber = '{chamber}' AND congress = {congress}").fetchone()[0]
        manifest_parts.append({"chamber": chamber, "congress": congress, "votes": vrel, "rollcalls": rel,
                               "rollcall_count": n_rc, "member_count": n_members, "first_date": first, "last_date": last,
                               "bytes": (out / vrel).stat().st_size + (out / rel).stat().st_size})
    con.execute(f"COPY (SELECT * FROM members ORDER BY congress, chamber, icpsr) TO '{sql_path(out / 'members.parquet')}' (FORMAT parquet, COMPRESSION zstd)")

    coverage = {"crs_and_pap_by_partition": topics.coverage(rollcalls), "pap_parse": pap_report,
                "missing_partitions": missing}
    (out / "coverage.json").write_text(json.dumps(coverage, indent=1))
    manifest = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "members": "members.parquet", "coverage": "coverage.json", "partitions": manifest_parts,
        "sources": {"voteview": cfg["sources"]["voteview_base"], "pap": cfg["sources"]["pap_rollcalls"]},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def main(argv=None) -> int:
    cfg = settings_mod.load()
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=cfg["output"]["fixture_raw_dir"])
    ap.add_argument("--out", default=cfg["output"]["data_dir"])
    args = ap.parse_args(argv)
    m = build(Path(args.raw), Path(args.out), cfg)
    print(f"build: {len(m['partitions'])} partitions -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
