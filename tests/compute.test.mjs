// The browser's pair aggregation (site/js/compute.js) on a hand-checked case: the same tiny Senate as tests/py/conftest.py.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import '../site/js/compute.js';

const K = globalThis.CG.compute;
// Members A..E = icpsr 1..5. Roll -> positions for 1..5 (y yea, n nay, p present / not voting).
const by_roll = { 1: 'yynnn', 2: 'ynyyy', 3: 'yyyyy', 4: 'ypnnn', 5: 'nnnyn', 6: 'yyypy' };
const minority = { 1: 0.4, 2: 0.2, 3: 0, 4: 0.25, 5: 0.2, 6: 0 };
const topics = { 1: 'Taxation', 2: 'Taxation', 6: 'Taxation' };
const rows = Object.keys(by_roll).map((r) => ({ rollnumber: Number(r), minority_share: minority[r], crs_policy_area_resolved: topics[r] || null, pap_majortopic: null }));
const part = { congress: 50, rows, positions: { order: [1, 2, 3, 4, 5], by_roll } };

test('A vs B: 4 of 5 shared, 2 of 3 contested', () => {
  const r = K.pairAgreement([part], 1, 2, 0.10, 'crs');
  assert.deepEqual(r.byCongress, [{ congress: 50, shared_all: 5, agree_all: 4, shared_contested: 3, agree_contested: 2 }]);
  assert.deepEqual(r.byTopic, [
    { topic: '', shared_all: 2, agree_all: 2, shared_contested: 1, agree_contested: 1 },
    { topic: 'Taxation', shared_all: 3, agree_all: 2, shared_contested: 2, agree_contested: 1 },
  ]);
});

test('threshold is inclusive', () => {
  const r = K.pairAgreement([part], 1, 3, 0.25, 'crs');
  assert.equal(r.byCongress[0].shared_contested, 2);
  assert.equal(r.byCongress[0].agree_contested, 0);
});

test('present is not a shared vote; unknown member gives nothing', () => {
  assert.equal(K.pairAgreement([part], 4, 5, 0.1, 'crs').byCongress[0].shared_all, 5);
  assert.deepEqual(K.pairAgreement([part], 1, 99, 0.1, 'crs').byCongress, []);
});
