"""Agreement math, contested filter and small-n suppression, run through the site's own SQL (site/sql/h2h.sql)."""
from pipeline import queries
from conftest import CONGRESS


def h2h(con, a, b, threshold):
    return queries.run(con, "h2h", a, b, "Senate", CONGRESS, CONGRESS, threshold)


def test_agreement_hand_checked(tiny_data):
    con = queries.connect(tiny_data)
    # A vs B: B did not vote on roll 4, so 5 shared votes; they differ only on roll 2 -> 4/5.
    # Contested at 10%: rolls 1, 2, 5 (rolls 3 and 6 are unanimous among yea/nay) -> agree on 1 and 5 -> 2/3.
    [row] = h2h(con, 1, 2, 0.10)
    assert (row["shared_all"], row["agree_all"]) == (5, 4)
    assert (row["shared_contested"], row["agree_contested"]) == (3, 2)
    # A vs C: differ on rolls 1 and 4 -> 4/6; contested rolls 1, 2, 4, 5 -> 2/4.
    [row] = h2h(con, 1, 3, 0.10)
    assert (row["shared_all"], row["agree_all"], row["shared_contested"], row["agree_contested"]) == (6, 4, 4, 2)


def test_present_is_not_a_shared_vote(tiny_data):
    con = queries.connect(tiny_data)
    # D voted "present" on roll 6 -> D vs E shares 5 votes, not 6.
    [row] = h2h(con, 4, 5, 0.10)
    assert row["shared_all"] == 5


def test_contested_threshold_is_inclusive_and_tunable(tiny_data):
    con = queries.connect(tiny_data)
    # A vs C at 25%: roll 1 (0.40) and roll 4 (exactly 0.25) count; rolls 2 and 5 (0.20) do not.
    [row] = h2h(con, 1, 3, 0.25)
    assert (row["shared_contested"], row["agree_contested"]) == (2, 0)
    [row] = h2h(con, 1, 3, 0.26)
    assert (row["shared_contested"], row["agree_contested"]) == (1, 0)
    # Raw all-votes numbers never depend on the threshold.
    assert (row["shared_all"], row["agree_all"]) == (6, 4)


def test_minority_share_from_member_votes(tiny_data):
    con = queries.connect(tiny_data)
    shares = {r["rollnumber"]: (r["yea_n"], r["nay_n"], r["not_voting_n"], r["minority_share"])
              for r in queries.run(con, "rollcalls", "Senate", CONGRESS)}
    assert shares[1] == (2, 3, 0, 0.4)
    assert shares[4] == (1, 3, 1, 0.25)
    assert shares[6] == (4, 0, 1, 0.0)


def test_president_positions_excluded(tiny_data):
    con = queries.connect(tiny_data)
    assert con.execute("SELECT count(*) FROM votes WHERE icpsr = 99999").fetchone()[0] == 0
    assert con.execute("SELECT count(*) FROM members WHERE chamber = 'President'").fetchone()[0] == 0


def test_small_n_suppression():
    rows = [{"shared_all": 25, "agree_all": 20, "shared_contested": 19, "agree_contested": 10}]
    s = queries.summarize_h2h(rows, min_shared=20)
    assert s["all_shown"] and not s["contested_shown"]
    s = queries.summarize_h2h(rows + [{"shared_all": 1, "agree_all": 1, "shared_contested": 1, "agree_contested": 1}], 20)
    assert s["contested_shown"] and s["shared_contested"] == 20 and s["pct_contested"] == 11 / 20


def test_shared_congresses(tiny_data):
    con = queries.connect(tiny_data)
    assert [r["congress"] for r in queries.run(con, "shared_congresses", 1, 2, "Senate")] == [CONGRESS]
    assert queries.run(con, "shared_congresses", 1, 2, "House") == []
