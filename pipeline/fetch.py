"""Download the raw sources into a local raw directory (run in GitHub Actions; the sandbox may not reach the hosts).

Layout written (the same layout the committed fixture uses, which stores files gzipped):
  {raw}/voteview/{table}/{H|S}{ccc}_{table}.{ext}
  {raw}/voteview/parties/HSall_parties.csv
  {raw}/pap/rcv.csv

  python -m pipeline.fetch --raw build/raw            # every Congress in settings scope
  python -m pipeline.fetch --raw build/raw --congress 117 118
"""
import argparse
import concurrent.futures
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import settings as settings_mod

CHAMBER_PREFIX = {"House": "H", "Senate": "S"}


def voteview_name(chamber: str, congress: int, table: str, ext: str) -> str:
    return f"{CHAMBER_PREFIX[chamber]}{congress:03d}_{table}.{ext}"


def _get(url: str, dest: Path, cfg: dict) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": cfg["sources"]["user_agent"]})
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(req, timeout=cfg["sources"]["request_timeout_s"]) as resp, open(tmp, "wb") as out:
            while chunk := resp.read(1 << 20):
                out.write(chunk)
    except urllib.error.HTTPError as e:
        tmp.unlink(missing_ok=True)
        return f"{e.code}"
    tmp.replace(dest)
    time.sleep(cfg["sources"]["request_pause_s"])
    return "ok"


def plan(cfg: dict, raw: Path, congresses: list[int]) -> list[tuple[str, Path]]:
    base = cfg["sources"]["voteview_base"]
    jobs = []
    for chamber in cfg["scope"]["chambers"]:
        for c in congresses:
            for table, ext in cfg["sources"]["voteview_tables"].items():
                name = voteview_name(chamber, c, table, ext)
                jobs.append((f"{base}/{table}/{name}", raw / "voteview" / table / name))
    jobs.append((f"{base}/{cfg['sources']['voteview_parties']}", raw / "voteview" / "parties" / "HSall_parties.csv"))
    jobs.append((cfg["sources"]["pap_rollcalls"], raw / "pap" / "rcv.csv"))
    return jobs


def main(argv=None) -> int:
    cfg = settings_mod.load()
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="build/raw")
    ap.add_argument("--congress", type=int, nargs="*")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)
    raw = Path(args.raw)
    congresses = args.congress or list(range(cfg["scope"]["congress_min"], cfg["scope"]["congress_max"] + 1))
    jobs = plan(cfg, raw, congresses)
    for _, dest in jobs:
        dest.parent.mkdir(parents=True, exist_ok=True)
    failed = []
    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        for (url, dest), status in zip(jobs, pool.map(lambda j: _get(j[0], j[1], cfg), jobs)):
            if status != "ok":
                failed.append(f"{status} {url}")
    print(f"fetch: {len(jobs) - len(failed)}/{len(jobs)} files")
    for f in failed:
        print(f"fetch: missing {f}")
    # A Congress Voteview has not published yet 404s; that is reported, not fatal. Missing PAP or parties is fatal.
    fatal = [f for f in failed if "parties" in f or cfg["sources"]["pap_rollcalls"] in f]
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
