// The context sentence's percentile wording, including tied quantiles (tests the function the page uses).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const src = fs.readFileSync(new URL('../site/js/app.js', import.meta.url), 'utf8');
const body = src.slice(src.indexOf('  function percentileBand(g, v) {'), src.indexOf('  function contextStrip('));
const ordinal = (n) => { const v = n % 100, s = ['th', 'st', 'nd', 'rd']; return n + (s[(v - 20) % 10] || s[v] || s[0]); };
const percentileBand = new Function('ordinal', `${body}; return percentileBand;`)(ordinal);
const g = { p10: 0.1, p25: 0.2, p50: 0.4, p75: 0.6, p90: 0.8 };

test('plain bands', () => {
  assert.equal(percentileBand(g, 0.05), 'below the 10th percentile');
  assert.equal(percentileBand(g, 0.3), 'between the 25th and 50th percentiles');
  assert.equal(percentileBand(g, 0.4), 'at the 50th percentile');
  assert.equal(percentileBand(g, 0.9), 'above the 90th percentile');
  assert.equal(percentileBand(g, 0.8), 'at the 90th percentile');
});

test('tied quantiles name the whole span', () => {
  assert.equal(percentileBand({ p10: 0.5, p25: 0.7, p50: 0.9, p75: 1, p90: 1 }, 1), 'at the 75th to 90th percentile');
  assert.equal(percentileBand({ p10: 0.2, p25: 0.2, p50: 0.2, p75: 0.6, p90: 0.8 }, 0.2), 'at the 10th to 50th percentile');
  assert.equal(percentileBand({ p10: 0.2, p25: 0.2, p50: 0.2, p75: 0.6, p90: 0.8 }, 0.25), 'between the 50th and 75th percentiles');
});
