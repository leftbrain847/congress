# Congress

A public, neutral site for U.S. House and Senate roll-call voting, 1789 to the present. It answers one question: who votes with whom, on what, and how did each vote split? It's a static site on GitHub Pages: every query runs in the visitor's browser (DuckDB-WASM over partitioned parquet). There's no backend, no API key, and no outside loads at runtime.

**Built so far:** head-to-head agreement (feature 1) and the bill view (feature 4) for both chambers, plus member pages and chamber/Congress pickers.
**Next:** agreement by topic (feature 2) and blocs (feature 3); see `next` in `project.yml`.

## Run
From a clean clone, against the committed fixture (real Voteview and Policy Agendas slices for the 1st, 93rd and 118th Congresses, both chambers):
```
pip install -r requirements.txt && npm ci
python -m pipeline.build --raw fixture/raw --out build/data          # sources -> partitioned parquet
python -m pipeline.build_site --data build/data --out build/site     # site + self-hosted DuckDB-WASM
cd build/site && python -m http.server 8000                          # open http://localhost:8000
```
For the full history, run the **pipeline-and-pages** workflow in GitHub Actions. It fetches every Congress (`python -m pipeline.fetch --raw build/raw`), builds, tests and deploys. To refresh the fixture: `python -m pipeline.fetch --raw build/raw --congress 1 93 118 && python -m pipeline.make_fixture --raw build/raw`.

## Test
```
npm test && pytest -q
```
CI runs both, then the fixture build end to end. The tests cover:
- agreement math on hand-checked cases;
- the contested filter, including its inclusive threshold;
- small-n suppression;
- CRS topic inheritance for amendments;
- the Policy Agendas file's quirks;
- the site's SQL against an independent count on real data;
- day-snapshot parity with the SQL;
- the NOMINATE cutting line.

## How it works
- **Settings:** every tunable lives in `config/settings.yaml`: contested threshold, minimum shared votes, rolling window, topic scheme, clustering resolution, chambers, Congress range and the NOMINATE dimension-2 weight. `build_site` mirrors it into `settings.json` for the page.
- **One set of queries:** `site/sql/*.sql` is what the browser runs, and the same files run in Python DuckDB for the tests and the day page. The math lives in one place.
- **Sources:** checked against the real files on 2026-11-09, not assumed.
  - **Voteview per-Congress files:**
    - `votes` and `members` CSVs;
    - the `rollcalls` JSON, which carries `crs_policy_area` (the CSV doesn't);
    - `HSall_parties.csv`.
  - **Policy Agendas `rcv_voteview_v3_4.csv`:**
    - covers the 79th–118th Congresses, and the 118th is partial;
    - encoded in cp1252;
    - chamber is coded `1`/`2`, which mean House/Senate;
    - 569 rows of the 118th have their topic columns shifted one place right. `pipeline/pap.py` documents and handles each quirk.
  - **Join check:** every 93rd- and 118th-Congress roll call that Policy Agendas covers joins to Voteview with identical yea/nay counts.
- **CRS inheritance:** a roll call with no CRS policy area takes the area of its bill: the same bill number in the same Congress, with the most common tag winning and ties broken alphabetically. `coverage.json` and the About page show the share still untagged per chamber and Congress.
- **Zero outside loads:** DuckDB-WASM's wasm, workers and parquet extension are served from `vendor/`, each pinned by sha256 in `config/vendor.lock.json`. The build refuses a file that doesn't match. Fonts are system fonts. The page's CSP allows only its own origin.

## Definitions (shown on the site next to every number)
- **Shared vote:** both members voted yea or nay. Present and not voting are left out.
- **Contested:** the smaller side had at least `contested_threshold` (default 10%) of the yea and nay votes.
- **Agreement:** shared votes on which both voted the same way, divided by shared votes. It's always shown with its n, and next to the all-votes number. Results with fewer than `min_shared_votes` (default 20) shared votes are hidden.
- **Voted against party majority:** a yea or nay that differs from the majority of the member's own party's yeas and nays on that roll call.
- **Cutting line:** drawn as Voteview draws it, using `nominate_dim2_weight`.

## Deployed
- Live: GitHub Pages once Pages is enabled and the pipeline workflow has run.
- Day snapshot: `snapshots/2026-11-09 - Congress.html` (frozen; never edited)

## Ship a sprint day
Build the day page, then freeze it:
```
python -m pipeline.snapshot_page --data build/data --out build/day.html --title "YYYY-MM-DD - Congress"
node scripts/snapshot.mjs build/day.html --public
```
Commit `snapshots/` to `main` (via PR). The index's nightly refresh logs the day automatically. Public pages still have to pass its UAT and secret scan.

## Data credits
- Voteview: Lewis, Poole, Rosenthal, Boche, Rudkin and Sonnet, *Voteview: Congressional Roll-Call Votes Database*.
- Policy Agendas Project: roll-call topic codes from comparativeagendas.net.
