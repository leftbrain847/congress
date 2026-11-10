"""CRS policy area per roll call, with inheritance for amendment and procedural votes.

Voteview's rollcalls JSON tags only some roll calls on a bill with crs_policy_area (in the 118th House, HR23's
motion to recommit carries "Taxation" and its passage vote carries nothing). An untagged roll call inherits the
area of its parent bill: the tags on other roll calls with the same bill_number in the same Congress (and, if
crs_inherit_scope is "chamber", the same chamber). When a bill's roll calls carry more than one area, the most
common wins, ties broken alphabetically, so the result never depends on row order.
"""
from collections import Counter, defaultdict


def norm_bill(b):
    b = (b or "").strip().upper().replace(" ", "")
    return b or None


def resolve_crs(rollcalls: list[dict], scope: str = "congress") -> list[dict]:
    """Add crs_policy_area_resolved and crs_source ('tagged' | 'inherited' | None) to each roll call (copies)."""
    if scope not in ("congress", "chamber"):
        raise ValueError(f"crs_inherit_scope must be 'congress' or 'chamber', not {scope!r}")

    def key(r):
        bill = norm_bill(r.get("bill_number"))
        if bill is None:
            return None
        return (r["congress"], bill) if scope == "congress" else (r["congress"], r["chamber"], bill)

    tags = defaultdict(Counter)
    for r in rollcalls:
        k, area = key(r), r.get("crs_policy_area")
        if k is not None and area:
            tags[k][area] += 1

    out = []
    for r in rollcalls:
        r = dict(r)
        area = r.get("crs_policy_area")
        if area:
            r["crs_policy_area_resolved"], r["crs_source"] = area, "tagged"
        else:
            counts = tags.get(key(r))
            if counts:
                best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
                r["crs_policy_area_resolved"], r["crs_source"] = best, "inherited"
            else:
                r["crs_policy_area_resolved"], r["crs_source"] = None, None
        out.append(r)
    return out


def coverage(rollcalls: list[dict]) -> list[dict]:
    """Per chamber and Congress: roll calls, tagged, inherited, still untagged, and the untagged share."""
    groups = defaultdict(Counter)
    for r in rollcalls:
        g = groups[(r["chamber"], r["congress"])]
        g["rollcalls"] += 1
        g[r.get("crs_source") or "untagged"] += 1
        g["pap_tagged"] += r.get("pap_majortopic") is not None
    rows = []
    for (chamber, congress), g in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        n = g["rollcalls"]
        rows.append({
            "chamber": chamber, "congress": congress, "rollcalls": n,
            "crs_tagged": g["tagged"], "crs_inherited": g["inherited"], "crs_untagged": g["untagged"],
            "crs_untagged_share": round(g["untagged"] / n, 4) if n else None,
            "pap_tagged": g["pap_tagged"],
            "pap_untagged_share": round(1 - g["pap_tagged"] / n, 4) if n else None,
        })
    return rows
