"""Run the site's SQL (site/sql/*.sql) in Python DuckDB: the exact queries the browser runs in DuckDB-WASM.
Tests use this to check the math the site shows; precompute.py uses it to build the self-contained day snapshot.
"""
from pathlib import Path

import duckdb

from .settings import ROOT

SQL_DIR = ROOT / "site" / "sql"


def sql(name: str) -> str:
    return (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")


def connect(data_dir: Path) -> duckdb.DuckDBPyConnection:
    """Tables members, votes, rollcalls over every partition in data_dir (the browser loads only the ones it needs)."""
    d = str(Path(data_dir)).replace("'", "''")
    con = duckdb.connect()
    con.execute(f"CREATE TABLE members AS SELECT * FROM read_parquet('{d}/members.parquet')")
    con.execute(f"CREATE TABLE votes AS SELECT * FROM read_parquet('{d}/votes/*/*/votes.parquet')")
    con.execute(f"CREATE TABLE rollcalls AS SELECT * FROM read_parquet('{d}/rollcalls/*/*/rollcalls.parquet')")
    return con


def run(con, name: str, *params) -> list[dict]:
    cur = con.execute(sql(name), list(params))
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def summarize_h2h(rows: list[dict], min_shared: int) -> dict:
    """Totals across Congresses, with the same suppression rule the front end applies (js/metrics.js)."""
    tot = {k: sum(r[k] for r in rows) for k in ("shared_all", "agree_all", "shared_contested", "agree_contested")}
    pct = lambda a, n: (a / n) if n else None
    return {
        **tot,
        "pct_all": pct(tot["agree_all"], tot["shared_all"]),
        "pct_contested": pct(tot["agree_contested"], tot["shared_contested"]),
        "contested_shown": tot["shared_contested"] >= min_shared,
        "all_shown": tot["shared_all"] >= min_shared,
    }
