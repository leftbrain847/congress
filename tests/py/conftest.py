"""Shared fixtures: a tiny hand-made Senate (5 members, 6 roll calls) small enough to check every number by hand,
and the real committed fixture (fixture/raw) built once per test session."""
import csv
import gzip
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline import build as build_mod, settings  # noqa: E402

CONGRESS = 50
# icpsr -> (name, party_code)
MEMBERS = {1: ("A", 100), 2: ("B", 100), 3: ("C", 200), 4: ("D", 200), 5: ("E", 200)}
# rollnumber -> cast codes for icpsr 1..5 (1 yea, 6 nay, 7 present, 9 not voting)
CASTS = {
    1: [1, 1, 6, 6, 6],   # yea 2 nay 3 -> minority 0.40
    2: [1, 6, 1, 1, 1],   # yea 4 nay 1 -> 0.20; party 100 split 1-1 (no majority, no crossers)
    3: [1, 1, 1, 1, 1],   # unanimous -> 0.00
    4: [1, 9, 6, 6, 6],   # B not voting; yea 1 nay 3 -> 0.25
    5: [6, 6, 6, 1, 6],   # yea 1 nay 4 -> 0.20; D crosses party 200's nay majority
    6: [1, 1, 1, 7, 1],   # D present; yea 4 nay 0 -> 0.00
}
ROLLCALLS = [
    {"rollnumber": 1, "bill_number": "S10", "crs_policy_area": "Taxation", "vote_question": "On Passage"},
    {"rollnumber": 2, "bill_number": "S10", "crs_policy_area": None, "vote_question": "On the Amendment"},
    {"rollnumber": 3, "bill_number": "PN7", "crs_policy_area": None, "vote_question": "On the Nomination"},
    {"rollnumber": 4, "bill_number": "S11", "crs_policy_area": None, "vote_question": "On the Motion"},
    {"rollnumber": 5, "bill_number": None, "crs_policy_area": None, "vote_question": "On the Motion to Adjourn"},
    {"rollnumber": 6, "bill_number": "S10", "crs_policy_area": None, "vote_question": "On Cloture"},
]
PRESIDENT = 99999


def write_gz(path: Path, text: str, encoding="utf-8"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb") as f:
        f.write(text.encode(encoding))


def csv_text(header, rows):
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def make_tiny_raw(raw: Path):
    vv = raw / "voteview"
    members = [[CONGRESS, "President", PRESIDENT, "", 100, "", "", "", "PRES", "", "", "", "", ""]]
    for icpsr, (name, party) in MEMBERS.items():
        members.append([CONGRESS, "Senate", icpsr, "ST", party, 0, "", "", name, f"X{icpsr:06d}", 1900, "",
                        round(-0.5 + icpsr * 0.2, 2), 0.1])
    write_gz(vv / "members" / f"S{CONGRESS:03d}_members.csv.gz", csv_text(
        ["congress", "chamber", "icpsr", "state_abbrev", "party_code", "district_code", "occupancy", "last_means",
         "bioname", "bioguide_id", "born", "died", "nominate_dim1", "nominate_dim2"], members))
    votes = []
    for roll, casts in CASTS.items():
        for icpsr, cast in zip(MEMBERS, casts):
            votes.append([CONGRESS, "Senate", roll, icpsr, cast, 100.0])
        votes.append([CONGRESS, "Senate", roll, PRESIDENT, 1, 100.0])  # must be excluded (not a senator)
    write_gz(vv / "votes" / f"S{CONGRESS:03d}_votes.csv.gz",
             csv_text(["congress", "chamber", "rollnumber", "icpsr", "cast_code", "prob"], votes))
    rcs = [{"congress": CONGRESS, "chamber": "Senate", "date": f"1888-01-0{r['rollnumber']}", "session": 1,
            "yea_count": 0, "nay_count": 0, "nominate_mid_1": 0.1, "nominate_mid_2": 0.0,
            "nominate_spread_1": 0.5, "nominate_spread_2": 0.2, **r} for r in ROLLCALLS]
    write_gz(vv / "rollcalls" / f"S{CONGRESS:03d}_rollcalls.json.gz", json.dumps(rcs))
    write_gz(vv / "parties" / "HSall_parties.csv.gz", csv_text(
        ["congress", "chamber", "party_code", "party_name"], [[CONGRESS, "Senate", 100, "Party One"],
                                                              [CONGRESS, "Senate", 200, "Party Two"]]))
    header = ["id", "congress", "chamber", "rollnumber", "date", "year", "month", "day", "session", "clerk_rollnumber",
              "yea_count", "nay_count", "nominate_mid_1", "nominate_mid_2", "nominate_spread_1", "nominate_spread_2",
              "nominate_log_likelihood", "bill_number ", "vote_result", "vote_desc", "vote_question", "dtl_desc",
              "pap_description", "pap_majortopic", "pap_subtopic", "majortopic", "subtopic", ""]
    pap_rows = [[1, CONGRESS, "2", 1] + [""] * 19 + ["1", "107", "1", "107", ""],
                [2, CONGRESS, "2", 2] + [""] * 19 + ["NA", "NA", "NA", "NA", ""]]
    write_gz(raw / "pap" / "rcv.csv.gz", csv_text(header, pap_rows), "cp1252")


@pytest.fixture(scope="session")
def cfg():
    return settings.load()


@pytest.fixture(scope="session")
def tiny_data(tmp_path_factory, cfg):
    raw = tmp_path_factory.mktemp("tiny_raw")
    make_tiny_raw(raw)
    out = tmp_path_factory.mktemp("tiny_data")
    build_mod.build(raw, out, cfg)
    return out


@pytest.fixture(scope="session")
def fixture_data(tmp_path_factory, cfg):
    out = tmp_path_factory.mktemp("fixture_data")
    build_mod.build(ROOT / cfg["output"]["fixture_raw_dir"], out, cfg)
    return out
