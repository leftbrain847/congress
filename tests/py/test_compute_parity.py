"""The browser's only computation (site/js/compute.js: the picked pair's agreement, overall and by topic, plus the
reshaping for the NOMINATE map and member vote lists) must match the site's SQL. Runs compute.js in node on the
result files pipeline/results.py writes for the fixture, and compares with Python DuckDB."""
import json
import shutil
import subprocess

import pytest

from pipeline import queries, results
from pipeline.results import clean
from conftest import ROOT


def run_node(tmp_path, calls, files):
    (tmp_path / "files.json").write_text(json.dumps(files))
    (tmp_path / "calls.json").write_text(json.dumps(calls))
    script = f"""
      const fs = require('fs');
      require({json.dumps(str(ROOT / 'site/js/compute.js'))});
      const K = globalThis.CG.compute;
      const F = JSON.parse(fs.readFileSync({json.dumps(str(tmp_path / 'files.json'))}, 'utf8'));
      const calls = JSON.parse(fs.readFileSync({json.dumps(str(tmp_path / 'calls.json'))}, 'utf8'));
      const part = (ch, c) => ({{ congress: c, rows: F[`${{ch}}/${{c}}/rollcalls.json`].rows, positions: F[`${{ch}}/${{c}}/positions.json`] }});
      const out = calls.map(([kind, p]) => {{
        if (kind === 'pair') return K.pairAgreement(p.congresses.map((c) => part(p.chamber, c)), p.a, p.b, p.t, p.scheme);
        if (kind === 'points') return K.points(F[`${{p.chamber}}/${{p.congress}}/members.json`], F[`${{p.chamber}}/${{p.congress}}/positions.json`], p.roll);
        if (kind === 'member_votes') return K.memberVotes(p.icpsr, F[`${{p.chamber}}/${{p.congress}}/rollcalls.json`].rows, F[`${{p.chamber}}/${{p.congress}}/positions.json`]);
        if (kind === 'shared') return K.sharedCongresses(F[`members/${{p.a}}.json`], F[`members/${{p.b}}.json`], p.chamber);
      }});
      process.stdout.write(JSON.stringify(out));
    """
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, cwd=tmp_path)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("threshold", [0.10, 0.25])
def test_compute_matches_sql(fixture_data, tmp_path, threshold):
    scope = [("Senate", 118), ("House", 93), ("Senate", 1)]
    files = results.build(fixture_data, scope)
    con = queries.connect(fixture_data)
    calls, want = [], []
    for ch, c in scope:
        ids = [m["icpsr"] for m in files[f"{ch}/{c}/members.json"]]
        for a, b in [(ids[0], ids[1]), (ids[-1], ids[2]), (ids[5], ids[-3])]:
            for scheme in ("pap", "crs"):
                calls.append(["pair", {"chamber": ch, "congresses": [c], "a": a, "b": b, "t": threshold, "scheme": scheme}])
                want.append({"byCongress": [{"congress": c, **{k: r[k] for k in r if k != "congress"}}
                                            for r in queries.run(con, "h2h", a, b, ch, c, c, threshold)],
                             "byTopic": queries.run(con, "h2h_by_topic", a, b, ch, c, c, threshold, scheme)})
            calls.append(["shared", {"a": a, "b": b, "chamber": ch}])
            want.append([r["congress"] for r in queries.run(con, "shared_congresses", a, b, ch)])
        rolls = [r["rollnumber"] for r in files[f"{ch}/{c}/rollcalls.json"]["rows"]]
        for roll in rolls[:: max(1, len(rolls) // 10)]:
            calls.append(["points", {"chamber": ch, "congress": c, "roll": roll}])
            want.append(clean(queries.run(con, "bill_points", ch, c, roll)))
        calls.append(["member_votes", {"icpsr": ids[3], "chamber": ch, "congress": c}])
        want.append(clean(queries.run(con, "member_votes", ids[3], ch, c)))
    got = run_node(tmp_path, calls, files)
    for call, g, w in zip(calls, got, json.loads(json.dumps(want))):
        assert g == w, call


def test_results_carry_precomputed_split_and_crossers(fixture_data):
    files = results.build(fixture_data, [("Senate", 118)])
    rc = files["Senate/118/rollcalls.json"]
    con = queries.connect(fixture_data)
    for roll in (5, 100, 500):
        assert rc["split"][str(roll)] == [[s["party"], s["yea"], s["nay"], s["not_voting"]]
                                          for s in queries.run(con, "bill_party_split", "Senate", 118, roll)]
        assert rc["crossers"][str(roll)] == [[x["icpsr"], x["position"]] for x in queries.run(con, "bill_crossers", "Senate", 118, roll)]
    assert set(files) >= {"manifest.json", "coverage.json", "Senate/118/members.json", "Senate/118/positions.json"}
    assert all(f"members/{m['icpsr']}.json" in files for m in files["Senate/118/members.json"])
