"""The day page is one self-contained file: strict CSP, no outside URLs loaded, embedded data parses and cannot
break out of its <script> block, and the title is escaped."""
import json
import re

from pipeline import results, snapshot_page


def test_day_page_is_self_contained(fixture_data, cfg):
    files = results.build(fixture_data, [("Senate", 1)])
    # A hostile description must not be able to open or close tags inside the data block.
    files["Senate/1/rollcalls.json"]["rows"][0]["description"] = '<!--<script></script><img src=x onerror=alert(1)>'
    html = snapshot_page.page(files, cfg, "2026-11-10 - Congress <b>")
    assert "<title>2026-11-10 - Congress &lt;b&gt;</title>" in html
    assert f'<a href="{cfg["output"]["site_url"]}" target="_blank" rel="noopener">Open the full site</a>' in html
    assert "default-src 'none'" in html
    assert not re.search(r'src="https?://', html)                       # nothing loads from another origin
    assert not re.search(r'<link[^>]+href="https?://', html)
    outside_links = set(re.findall(r'<a [^>]*href="(https?://[^"]+)"', html))
    assert outside_links == {cfg["output"]["site_url"]}                  # the only outside link: the full site
    assert "boot.js" not in html and "results/" not in html.split('id="snapshot-data"')[0]
    m = re.search(r'<script type="application/json" id="snapshot-data">(.*?)</script>', html, re.S)
    assert "<" not in m.group(1)
    data = json.loads(m.group(1))
    assert data["Senate/1/rollcalls.json"]["rows"][0]["description"].startswith("<!--<script>")
    assert html.count("<script") == html.count("</script>")
