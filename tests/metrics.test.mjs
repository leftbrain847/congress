// Shared front-end math (site/js/metrics.js): suppression rule (same as pipeline/queries.py) and the cutting line.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import '../site/js/metrics.js';

const M = globalThis.CG.metrics;

test('summarizeH2h totals across Congresses and suppresses small n', () => {
  const rows = [
    { shared_all: 25, agree_all: 20, shared_contested: 19, agree_contested: 10 },
  ];
  let s = M.summarizeH2h(rows, 20);
  assert.equal(s.all_shown, true);
  assert.equal(s.contested_shown, false);
  assert.equal(s.pct_all, 0.8);
  s = M.summarizeH2h([...rows, { shared_all: 1, agree_all: 1, shared_contested: 1, agree_contested: 1 }], 20);
  assert.equal(s.contested_shown, true);
  assert.equal(s.pct_contested, 11 / 20);
  assert.equal(M.summarizeH2h([], 20).pct_all, null);
});

test('cutting line passes through the midpoint, perpendicular to the spread, ends on the unit circle', () => {
  const [[x1, y1], [x2, y2]] = M.cuttingLine(0.1, -0.2, 0.5, 0.3);
  for (const [x, y] of [[x1, y1], [x2, y2]]) assert.ok(Math.abs(Math.hypot(x, y) - 1) < 1e-9);
  // Perpendicular to the spread vector
  assert.ok(Math.abs((x2 - x1) * 0.5 + (y2 - y1) * 0.3) < 1e-9);
  // Midpoint lies on the segment's line
  const cross = (x2 - x1) * (-0.2 - y1) - (y2 - y1) * (0.1 - x1);
  assert.ok(Math.abs(cross) < 1e-9);
});

test('cutting line uses the second-dimension weight the way Voteview does', () => {
  const w = 0.4158127;
  const [[x1, y1], [x2, y2]] = M.cuttingLine(0, 0, 0.5, 0.5, w);
  // Every point on the line is indifferent: x*s1 + w^2*y*s2 = 0, so slope = -s1 / (w^2 s2) (Voteview's b_slope).
  assert.ok(Math.abs((y2 - y1) / (x2 - x1) - -0.5 / (w * w * 0.5)) < 1e-9);
  assert.ok(Math.abs(x1 * 0.5 + w * w * y1 * 0.5) < 1e-9);
});

test('no cutting line without an estimate or outside the circle', () => {
  assert.equal(M.cuttingLine(null, 0, 0.5, 0.1), null);
  assert.equal(M.cuttingLine(0, 0, 0, 0), null);
  assert.equal(M.cuttingLine(2, 2, 1, 0), null);
});

test('formatting', () => {
  assert.equal(M.formatPct(0.6234), '62.3%');
  assert.equal(M.formatPct(null), '—');
  assert.equal(M.formatInt(12345), '12,345');
  assert.equal(M.positionLabel(-1), 'Nay');
});
