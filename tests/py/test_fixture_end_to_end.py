"""The committed fixture (real Voteview + PAP slices: Congresses 1, 93, 118, both chambers) builds end to end, and
the site's SQL agrees with an independent pure-Python count straight from the raw votes file."""
import csv
import gzip
import json
from collections import defaultdict

from pipeline import queries
from conftest import ROOT


def test_manifest_lists_every_partition(fixture_data, cfg):
    m = json.loads((fixture_data / "manifest.json").read_text())
    got = {(p["chamber"], p["congress"]) for p in m["partitions"]}
    assert got == {(c, n) for c in ("House", "Senate") for n in cfg["output"]["fixture_congresses"]}
    for p in m["partitions"]:
        assert (fixture_data / p["votes"]).exists() and (fixture_data / p["rollcalls"]).exists()
        assert p["rollcall_count"] > 0 and p["member_count"] > 0


def test_coverage_report(fixture_data):
    cov = json.loads((fixture_data / "coverage.json").read_text())
    rows = {(r["chamber"], r["congress"]): r for r in cov["crs_and_pap_by_partition"]}
    assert rows[("House", 1)]["crs_untagged_share"] == 1.0          # CRS policy areas start in the 93rd
    assert rows[("House", 118)]["crs_inherited"] > 0                 # amendments/procedural votes inherit
    assert rows[("House", 93)]["pap_tagged"] == rows[("House", 93)]["rollcalls"]
    assert cov["pap_parse"]["layout_B"] > 0                           # the shifted 118th rows were read


def independent_h2h(raw_votes_gz, a, b, minority, threshold):
    pos = defaultdict(dict)
    with gzip.open(raw_votes_gz, "rt") as f:
        for r in csv.DictReader(f):
            c = int(r["cast_code"])
            p = 1 if c in (1, 2, 3) else -1 if c in (4, 5, 6) else 0
            pos[int(r["rollnumber"])][int(r["icpsr"])] = p
    n = agree = nc = ac = 0
    for roll, by in pos.items():
        pa, pb = by.get(a, 0), by.get(b, 0)
        if pa and pb:
            n += 1
            agree += pa == pb
            if minority[roll] is not None and minority[roll] >= threshold:
                nc += 1
                ac += pa == pb
    return n, agree, nc, ac


def test_sql_matches_independent_count(fixture_data, cfg):
    con = queries.connect(fixture_data)
    senators = queries.run(con, "members", "Senate", 118)
    a, b = senators[0]["icpsr"], senators[-1]["icpsr"]
    minority = {r["rollnumber"]: r["minority_share"] for r in queries.run(con, "rollcalls", "Senate", 118)}
    t = cfg["analysis"]["contested_threshold"]
    [row] = queries.run(con, "h2h", a, b, "Senate", 118, 118, t)
    expect = independent_h2h(ROOT / "fixture/raw/voteview/votes/S118_votes.csv.gz", a, b, minority, t)
    assert (row["shared_all"], row["agree_all"], row["shared_contested"], row["agree_contested"]) == expect
    assert row["shared_contested"] < row["shared_all"]
