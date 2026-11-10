"""Cut the committed fixture (fixture/raw) from a full fetch: the fixture Congresses in settings, both chambers,
gzipped, plus the PAP rows for those Congresses (kept in the source's cp1252 bytes, header unchanged).

  python -m pipeline.fetch --raw build/raw --congress 1 93 118
  python -m pipeline.make_fixture --raw build/raw
"""
import argparse
import csv
import gzip
import io
import shutil
import sys
from pathlib import Path

from . import settings as settings_mod
from .fetch import voteview_name


def gz_copy(src: Path, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(src, "rb") as f, gzip.GzipFile(dest, "wb", mtime=0) as g:
        shutil.copyfileobj(f, g)


def main(argv=None) -> int:
    cfg = settings_mod.load()
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="build/raw")
    ap.add_argument("--out", default=cfg["output"]["fixture_raw_dir"])
    args = ap.parse_args(argv)
    raw, out = Path(args.raw), Path(args.out)
    congresses = cfg["output"]["fixture_congresses"]
    for chamber in cfg["scope"]["chambers"]:
        for c in congresses:
            for table, ext in cfg["sources"]["voteview_tables"].items():
                name = voteview_name(chamber, c, table, ext)
                gz_copy(raw / "voteview" / table / name, out / "voteview" / table / f"{name}.gz")
    gz_copy(raw / "voteview" / "parties" / "HSall_parties.csv", out / "voteview" / "parties" / "HSall_parties.csv.gz")

    keep = {str(c) for c in congresses}
    # Rows can span lines (quoted newlines), so filter parsed records, not lines.
    text = (raw / "pap" / "rcv.csv").read_text(encoding=cfg["sources"]["pap_encoding"], errors="replace")
    reader = csv.reader(io.StringIO(text, newline=""))
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(next(reader))
    for row in reader:
        if len(row) > 1 and row[1] in keep:
            w.writerow(row)
    dest = out / "pap" / "rcv.csv.gz"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(dest, "wb", mtime=0) as g:
        g.write(buf.getvalue().encode(cfg["sources"]["pap_encoding"], errors="replace"))
    print(f"fixture: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
