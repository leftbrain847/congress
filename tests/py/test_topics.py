"""CRS inheritance for amendment/procedural votes, PAP parsing, and coverage reporting."""
import pytest

from pipeline import pap, queries, topics
from conftest import CONGRESS


def rc(roll, bill, area, chamber="House", congress=118):
    return {"congress": congress, "chamber": chamber, "rollnumber": roll, "bill_number": bill, "crs_policy_area": area}


def test_amendment_inherits_parent_bill():
    out = topics.resolve_crs([rc(1, "HR23", "Taxation"), rc(2, "HR23", None), rc(3, "HR99", None), rc(4, None, None)])
    got = [(r["crs_policy_area_resolved"], r["crs_source"]) for r in out]
    assert got == [("Taxation", "tagged"), ("Taxation", "inherited"), (None, None), (None, None)]


def test_most_common_tag_wins_then_alphabetical():
    out = topics.resolve_crs([rc(1, "HR1", "Health"), rc(2, "HR1", "Health"), rc(3, "HR1", "Taxation"), rc(4, "HR1", None),
                              rc(5, "HR2", "Taxation"), rc(6, "HR2", "Energy"), rc(7, "HR2", None)])
    assert out[3]["crs_policy_area_resolved"] == "Health"
    assert out[6]["crs_policy_area_resolved"] == "Energy"


def test_own_tag_is_never_overwritten():
    out = topics.resolve_crs([rc(1, "HR1", "Health"), rc(2, "HR1", "Health"), rc(3, "HR1", "Taxation")])
    assert out[2]["crs_policy_area_resolved"] == "Taxation" and out[2]["crs_source"] == "tagged"


def test_scope_congress_vs_chamber():
    rows = [rc(1, "HR5", "Energy", "House"), rc(2, "HR5", None, "Senate")]
    assert topics.resolve_crs(rows, "congress")[1]["crs_policy_area_resolved"] == "Energy"
    assert topics.resolve_crs(rows, "chamber")[1]["crs_policy_area_resolved"] is None
    # Same bill number in another Congress is a different bill.
    assert topics.resolve_crs([rc(1, "HR5", "Energy", congress=117), rc(2, "HR5", None)])[1]["crs_source"] is None
    with pytest.raises(ValueError):
        topics.resolve_crs(rows, "everything")


def test_coverage_reports_untagged_share():
    out = topics.resolve_crs([rc(1, "HR23", "Taxation"), rc(2, "HR23", None), rc(3, "PN1", None), rc(4, None, None)])
    [row] = topics.coverage(out)
    assert (row["crs_tagged"], row["crs_inherited"], row["crs_untagged"], row["crs_untagged_share"]) == (1, 1, 2, 0.5)


def test_inheritance_end_to_end(tiny_data):
    con = queries.connect(tiny_data)
    rows = {r["rollnumber"]: (r["crs_policy_area_resolved"], r["crs_source"]) for r in queries.run(con, "rollcalls", "Senate", CONGRESS)}
    assert rows[1] == ("Taxation", "tagged")
    assert rows[2] == ("Taxation", "inherited") and rows[6] == ("Taxation", "inherited")
    assert rows[3] == (None, None) and rows[4] == (None, None) and rows[5] == (None, None)


KNOWN = set(range(1, 11)) | {12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 23}
HEADER = ("id,congress,chamber,rollnumber,date,year,month,day,session,clerk_rollnumber,yea_count,nay_count,"
          "nominate_mid_1,nominate_mid_2,nominate_spread_1,nominate_spread_2,nominate_log_likelihood,bill_number ,"
          "vote_result,vote_desc,vote_question,dtl_desc,pap_description,pap_majortopic,pap_subtopic,majortopic,subtopic,\r\n")


def line(fields):
    return ",".join(fields) + "\r\n"


def test_pap_layouts_and_chamber_codes():
    a = ["1", "100", "2", "3"] + [""] * 19 + ["7", "703", "7", "703", ""]                       # layout A, Senate
    b = ["2", "118", "House", "30"] + [""] * 14 + ["HR22", "Passed", "T", "On Passage", "", "desc", "8", "803", "8", "803"]  # B
    na = ["3", "110", "1", "473"] + [""] * 19 + ["NA", "NA", "NA", "NA", ""]
    bad = ["4", "90", "1", "5"] + [""] * 19 + ["0", "", "0", "", ""]                             # code 0 is not in the codebook
    mismatch = ["5", "90", "1", "6"] + [""] * 19 + ["3", "1201", "3", "1201", ""]               # subtopic of another major
    codes, report = pap.parse(HEADER + "".join(line(r) for r in (a, b, na, bad, mismatch)), KNOWN)
    assert codes[(100, "Senate", 3)] == (7, 703)
    assert codes[(118, "House", 30)] == (8, 803)
    assert codes[(110, "House", 473)] == (None, None)
    assert codes[(90, "House", 5)] == (None, None) and codes[(90, "House", 6)] == (None, None)
    assert report["layout_A"] == 3 and report["layout_B"] == 1 and report["code_outside_codebook"] == 2


def test_pap_conflicting_duplicates_left_untagged():
    r1 = ["1", "100", "1", "3"] + [""] * 19 + ["7", "703", "7", "703", ""]
    r2 = ["2", "100", "House", "3"] + [""] * 19 + ["8", "803", "8", "803", ""]
    codes, report = pap.parse(HEADER + line(r1) + line(r2), KNOWN)
    assert codes[(100, "House", 3)] == (None, None) and report["duplicate_conflict"] == 1


def test_pap_rejects_unexpected_header():
    with pytest.raises(ValueError):
        pap.parse("a,b,c\r\n1,2,3\r\n", KNOWN)
