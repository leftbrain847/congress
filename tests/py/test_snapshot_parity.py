"""The day-snapshot engine (site/js/engine_static.js) must give the same answers as the site's SQL. It stores
packed results and reshapes them; this runs it in node and compares with Python DuckDB on the fixture."""
import json
import shutil
import subprocess

import pytest

from pipeline import queries, snapshot_page
from pipeline.snapshot_page import clean
from conftest import ROOT

SCOPE = [("Senate", 118), ("House", 1)]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_static_engine_matches_sql(fixture_data, cfg, tmp_path):
    D = snapshot_page.precompute(fixture_data, cfg, SCOPE)
    con = queries.connect(fixture_data)
    t = cfg["analysis"]["contested_threshold"]
    calls = []
    for ch, c in SCOPE:
        members = queries.run(con, "members", ch, c)
        ids = [m["icpsr"] for m in members]
        rolls = [r["rollnumber"] for r in queries.run(con, "rollcalls", ch, c)]
        calls += [("members", [ch, c]), ("rollcalls", [ch, c])]
        for roll in rolls[:: max(1, len(rolls) // 25)]:
            calls += [(q, [ch, c, roll]) for q in ("rollcall", "bill_party_split", "bill_crossers", "bill_points")]
        for a, b in [(ids[0], ids[1]), (ids[-1], ids[2]), (ids[5], ids[-3])]:
            calls += [("h2h", [a, b, ch, c, c, t]), ("shared_congresses", [a, b, ch])]
        for m in ids[:3]:
            calls += [("member", [m]), ("member_votes", [m, ch, c])]
    (tmp_path / "data.json").write_text(json.dumps(D))
    (tmp_path / "calls.json").write_text(json.dumps(calls))
    script = f"""
      const fs = require('fs');
      require({json.dumps(str(ROOT / 'site/js/engine_static.js'))});
      const e = globalThis.CG.createStaticEngine(JSON.parse(fs.readFileSync({json.dumps(str(tmp_path / 'data.json'))}, 'utf8')));
      const calls = JSON.parse(fs.readFileSync({json.dumps(str(tmp_path / 'calls.json'))}, 'utf8'));
      process.stdout.write(JSON.stringify(calls.map(([n, p]) => e._sync(n, p))));
    """
    got = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True, cwd=tmp_path).stdout)
    assert len(got) == len(calls)
    for (name, params), js in zip(calls, got):
        want = clean(queries.run(con, name, *params))
        if name == "rollcall":
            js = [{k: v for k, v in js[0].items() if k in want[0]}]
        assert js == json.loads(json.dumps(want)), f"{name}{params}"
