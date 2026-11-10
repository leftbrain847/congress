"""Bill view: split by party and party-line crossers."""
from pipeline import queries
from conftest import CONGRESS


def test_party_split(tiny_data):
    con = queries.connect(tiny_data)
    split = {r["party"]: (r["yea"], r["nay"], r["not_voting"]) for r in queries.run(con, "bill_party_split", "Senate", CONGRESS, 4)}
    assert split == {"Party One": (1, 0, 1), "Party Two": (0, 3, 0)}


def test_crossers(tiny_data):
    con = queries.connect(tiny_data)
    # Roll 5: Party Two votes nay 2-1, so D (yea) crossed. Party One is 2-0 nay: no crossers.
    assert [(r["bioname"], r["position"]) for r in queries.run(con, "bill_crossers", "Senate", CONGRESS, 5)] == [("D", 1)]
    # Roll 2: Party One splits 1-1, so it has no majority and nobody is listed; Party Two is unanimous.
    assert queries.run(con, "bill_crossers", "Senate", CONGRESS, 2) == []


def test_points_carry_nominate_and_position(tiny_data):
    con = queries.connect(tiny_data)
    pts = queries.run(con, "bill_points", "Senate", CONGRESS, 6)
    assert len(pts) == 5 and {p["position"] for p in pts} == {1, 0}
    assert all(p["nominate_dim1"] is not None for p in pts)
