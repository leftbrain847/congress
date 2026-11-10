"""Parse the Policy Agendas Project roll-call file (rcv_voteview_v3_4.csv).

What the file actually looks like (checked 2026-11-09 against the downloaded file, not the codebook):
- Encoding cp1252, not UTF-8. 28 header columns, the last one unnamed; "bill_number " has a trailing space.
- Covers the 79th-118th Congresses (1945-2024). The 118th is partial (House 1,033 of 1,235 roll calls,
  Senate 511 of 691 when checked).
- chamber is "1"/"2" in most rows and "House"/"Senate" in recent ones. 1 = House, 2 = Senate (every roll call in
  the 93rd and 118th joins to Voteview with identical yea/nay counts under that mapping).
- Layout A (most rows): pap_majortopic at column 23, pap_subtopic at 24.
- Layout B (569 rows of the 118th): one extra field after nominate_log_likelihood shifts the topics right by one
  (major at 24, subtopic at 25) and fills the last column.
- A few rows have no codes ("NA") and a handful carry codes outside the codebook; both become untagged.
"""
import csv
import io
import re
from collections import Counter

DIGITS = re.compile(r"\d+")
CHAMBERS = {"1": "House", "2": "Senate", "House": "House", "Senate": "Senate"}


def _int(s):
    s = (s or "").strip()
    return int(s) if DIGITS.fullmatch(s) else None


def topic_fields(row: list[str]) -> tuple[int | None, int | None, str]:
    """Return (major, subtopic, layout) for one data row."""
    a_major, a_sub = _int(row[23]), _int(row[24])
    if a_major is not None:
        return a_major, a_sub, "A"
    b_major, b_sub = _int(row[24]), _int(row[25])
    if b_major is not None and len(row) > 27 and row[27].strip():
        return b_major, b_sub, "B"
    return None, None, "none"


def valid(major, sub, known_majors) -> bool:
    if major not in known_majors:
        return False
    return sub is None or sub // 100 == major


def parse(text: str, known_majors) -> tuple[dict, dict]:
    """Return ({(congress, chamber, rollnumber): (major, sub)}, report)."""
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader)
    if len(header) < 27 or header[1] != "congress" or header[3] != "rollnumber":
        raise ValueError(f"unexpected PAP header: {header[:5]}")
    out, report = {}, Counter()
    for row in reader:
        if len(row) < 27:
            report["short_row"] += 1
            continue
        congress, rollnumber, chamber = _int(row[1]), _int(row[3]), CHAMBERS.get(row[2].strip())
        if congress is None or rollnumber is None or chamber is None:
            report["bad_key"] += 1
            continue
        major, sub, layout = topic_fields(row)
        report[f"layout_{layout}"] += 1
        if major is not None and not valid(major, sub, known_majors):
            report["code_outside_codebook"] += 1
            major = sub = None
        key = (congress, chamber, rollnumber)
        if key in out:
            report["duplicate_key"] += 1
            if out[key] != (major, sub):
                report["duplicate_conflict"] += 1
                out[key] = (None, None)  # conflicting codes for one roll call: leave it untagged
            continue
        out[key] = (major, sub)
    return out, dict(report)


def read(path, encoding: str, known_majors):
    import gzip

    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding=encoding, errors="replace", newline="") as f:
        return parse(f.read(), known_majors)
