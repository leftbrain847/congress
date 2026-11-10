// Pure helpers shared by the page and the node tests. No DOM, no engine.
// Loaded as a classic script in the browser (sets globalThis.CG.metrics) and imported by tests/metrics.test.mjs.
(function (root) {
  const CG = (root.CG = root.CG || {});

  // Same rule as pipeline/queries.py summarize_h2h: totals across Congresses; a result built on fewer shared votes
  // than min_shared_votes is not shown.
  function summarizeH2h(rows, minShared) {
    const tot = { shared_all: 0, agree_all: 0, shared_contested: 0, agree_contested: 0 };
    for (const r of rows) for (const k of Object.keys(tot)) tot[k] += Number(r[k]) || 0;
    const pct = (a, n) => (n ? a / n : null);
    return {
      ...tot,
      pct_all: pct(tot.agree_all, tot.shared_all),
      pct_contested: pct(tot.agree_contested, tot.shared_contested),
      contested_shown: tot.shared_contested >= minShared,
      all_shown: tot.shared_all >= minShared,
    };
  }

  function formatPct(x, digits = 1) {
    return x == null ? '—' : `${(x * 100).toFixed(digits)}%`;
  }

  function formatInt(n) {
    return n == null ? '—' : Number(n).toLocaleString('en-US');
  }

  // NOMINATE cutting line: points p with (p - mid) · spread = 0, clipped to the unit circle.
  // Returns [[x1, y1], [x2, y2]] or null when Voteview has no estimate or the line misses the circle.
  function cuttingLine(mid1, mid2, spread1, spread2) {
    const vals = [mid1, mid2, spread1, spread2];
    if (vals.some((v) => v == null || !Number.isFinite(Number(v)))) return null;
    const [mx, my, sx, sy] = vals.map(Number);
    if (sx === 0 && sy === 0) return null;
    const dx = -sy, dy = sx; // direction along the line
    const a = dx * dx + dy * dy, b = 2 * (mx * dx + my * dy), c = mx * mx + my * my - 1;
    const disc = b * b - 4 * a * c;
    if (disc <= 0) return null;
    const r = Math.sqrt(disc);
    const t1 = (-b - r) / (2 * a), t2 = (-b + r) / (2 * a);
    return [[mx + t1 * dx, my + t1 * dy], [mx + t2 * dx, my + t2 * dy]];
  }

  function positionLabel(p) {
    return p === 1 ? 'Yea' : p === -1 ? 'Nay' : 'Present / not voting';
  }

  CG.metrics = { summarizeH2h, formatPct, formatInt, cuttingLine, positionLabel };
})(globalThis);
