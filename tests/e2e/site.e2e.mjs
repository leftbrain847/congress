// End-to-end: open the built site (build/site) and the day page (build/day.html) in Chromium at phone width and use
// them like a visitor. Every view must render with no errors, no requests to another origin and no sideways scroll,
// and the numbers on screen must match the result files. Build first (README "Run"), then: npm run e2e
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import '../../site/js/metrics.js';
import '../../site/js/compute.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const SITE = path.resolve(ROOT, process.env.E2E_SITE || 'build/site');
const DAY = path.resolve(ROOT, process.env.E2E_DAY || 'build/day.html');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' };
const M = globalThis.CG.metrics, K = globalThis.CG.compute;
const read = (rel) => JSON.parse(fs.readFileSync(path.join(SITE, 'results', rel), 'utf8'));
const settings = JSON.parse(fs.readFileSync(path.join(SITE, 'settings.json'), 'utf8'));

// E2E_DELAY_MS slows every response, to flush out tests that read the page before it re-renders.
const DELAY = Number(process.env.E2E_DELAY_MS || 0);
let server, base, browser;

before(async () => {
  assert.ok(fs.existsSync(SITE) && fs.existsSync(DAY), 'build the site and day page first (README "Run")');
  server = http.createServer((req, res) => {
    let p = decodeURIComponent(req.url.split('?')[0]);
    if (p === '/') p = '/index.html';
    const f = p === '/day.html' ? DAY : path.join(SITE, path.normalize(p));
    if (!f.startsWith(SITE) && f !== DAY) { res.writeHead(403); return res.end(); }
    fs.readFile(f, (err, buf) => setTimeout(() => {
      if (err) { res.writeHead(404); return res.end(); }
      res.writeHead(200, { 'Content-Type': TYPES[path.extname(f)] || 'application/octet-stream' });
      res.end(buf);
    }, DELAY));
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  base = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch();
});

after(async () => {
  await browser?.close();
  server?.close();
});

// Opens a route, waits for it to finish rendering, and checks what every view must satisfy.
async function visit(url, { colorScheme = 'light' } = {}) {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, colorScheme });
  const problems = [];
  page.on('pageerror', (e) => problems.push(`page error: ${e.message}`));
  page.on('console', (m) => m.type() === 'error' && problems.push(`console: ${m.text()}`));
  page.on('request', (r) => { if (!r.url().startsWith(base) && !r.url().startsWith('data:')) problems.push(`outside request: ${r.url()}`); });
  await page.goto(url);
  await page.waitForFunction(() => document.querySelector('main h1') && !document.querySelector('main .loading'), null, { timeout: 30000 });
  const check = async () => {
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    assert.ok(width <= 392, `${url}: page is ${width}px wide at a 390px screen`);
    assert.deepEqual(problems, [], url);
  };
  return { page, check, text: async (sel = 'main') => (await page.textContent(sel)).replace(/\s+/g, ' ') };
}

const senate = read('Senate/118/members.json');
const house = read('House/118/members.json');
const byName = (list, prefix) => list.find((m) => m.bioname.startsWith(prefix));

function expectedPair(chamber, congress, a, b, scheme) {
  const rc = read(`${chamber}/${congress}/rollcalls.json`), pos = read(`${chamber}/${congress}/positions.json`);
  const res = K.pairAgreement([{ congress, rows: rc.rows, positions: pos }], a, b, settings.analysis.contested_threshold, scheme);
  return { res, sum: M.summarizeH2h(res.byCongress, settings.analysis.min_shared_votes) };
}

for (const [label, root] of [['live site', () => `${base}/`], ['day page', () => `${base}/day.html`]]) {
  test(`${label}: home links to every section`, async () => {
    const { page, check, text } = await visit(`${root()}#/`);
    assert.match(await text(), /Head-to-head/);
    assert.equal(await page.locator('.card').count(), 3);
    await check();
    await page.close();
  });

  test(`${label}: head-to-head shows the same numbers as the result files, with context and topics`, async () => {
    const a = byName(senate, 'SANDERS').icpsr, b = byName(senate, 'MURKOWSKI').icpsr;
    const { page, check, text } = await visit(`${root()}#/h2h/Senate/118?a=${a}&b=${b}&topic=pap`);
    const { res, sum } = expectedPair('Senate', 118, a, b, 'pap');
    const t = await text('.result');
    assert.ok(t.includes(M.formatPct(sum.pct_contested)), `contested ${M.formatPct(sum.pct_contested)} on screen`);
    assert.ok(t.includes(`n = ${M.formatInt(sum.shared_contested)} shared votes`));
    assert.ok(t.includes(M.formatPct(sum.pct_all)));
    assert.match(t, /Compared with every pair in the 118th Congress Senate/);
    assert.match(t, /different-party pairs/);
    // Topic rows: every topic at or above the minimum n is drawn as a bar, the rest are listed as hidden.
    const shownTopics = res.byTopic.filter((r) => r.topic !== '' && r.shared_contested >= settings.analysis.min_shared_votes);
    assert.equal(await page.locator('.topic').count(), shownTopics.length + (res.byTopic.some((r) => r.topic === '' && r.shared_contested >= settings.analysis.min_shared_votes) ? 1 : 0));
    // Switch scheme, then swap the members: same totals, CRS topics.
    // Wait for the new content itself: the old view stays on screen until the re-render finishes.
    await page.click('text=CRS policy areas');
    await page.waitForFunction(() => /Congressional Research Service/.test(document.querySelector('.result')?.textContent || ''));
    await page.click('button:has-text("Swap")');
    await page.waitForFunction(() => /^MURKOWSKI.* and SANDERS/.test(document.querySelector('.result h2')?.textContent || ''));
    assert.ok((await text('.result')).includes(M.formatPct(sum.pct_contested)), 'swap keeps the same agreement');
    await check();
    await page.close();
  });

  test(`${label}: picking a member from the list updates the result`, async () => {
    const a = byName(house, 'PELOSI').icpsr, b = byName(house, 'BACON').icpsr;
    const { page, check, text } = await visit(`${root()}#/h2h/House/118?a=${a}`);
    assert.match(await text(), /Pick two members/);
    await page.locator('select').nth(3).selectOption(String(b));
    await page.waitForFunction(() => /PELOSI.* and BACON/.test(document.querySelector('.result h2')?.textContent || ''));
    const { sum } = expectedPair('House', 118, a, b, settings.analysis.topic_scheme);
    assert.ok((await text('.result')).includes(M.formatPct(sum.pct_contested)));
    await check();
    await page.close();
  });

  test(`${label}: roll-call list filters and opens a vote with split, crossers and the NOMINATE map`, async () => {
    const rc = read('Senate/118/rollcalls.json');
    const { page, check, text } = await visit(`${root()}#/votes/Senate/118`);
    assert.match(await text(), new RegExp(`${M.formatInt(rc.rows.length)} of ${M.formatInt(rc.rows.length)} roll calls`));
    const want = rc.rows.filter((r) => [r.bill_number, r.vote_question, r.description, r.crs_policy_area_resolved].join(' ').toLowerCase().includes('nomination')).length;
    await page.fill('input[type=search]', 'nomination');
    await page.click('button:has-text("Filter")');
    // Wait for the filtered count itself: the unfiltered list stays on screen until the re-render finishes.
    await page.waitForFunction((n) => (document.querySelector('main')?.textContent || '').includes(`${n} of`), M.formatInt(want));
    await page.locator('.rc-list a').first().click();
    await page.waitForSelector('figure.plot-wrap');   // only the vote view has this figure, so no stale match
    const roll = Number((await page.evaluate(() => location.hash)).split('/').pop());
    const crossers = rc.crossers[String(roll)];
    assert.match(await text(), new RegExp(`Voted against their party's majority \\(${crossers.length}\\)`));
    assert.equal(await page.locator('table.grid tbody tr').count(), rc.split[String(roll)].length);
    assert.ok(await page.locator('svg.plot circle.pt').count() > 50);
    await check();
    await page.close();
  });

  test(`${label}: member page lists that member's votes`, async () => {
    const m = byName(senate, 'CRUZ');
    const { page, check, text } = await visit(`${root()}#/member/${m.icpsr}/Senate/118`);
    const votes = K.memberVotes(m.icpsr, read('Senate/118/rollcalls.json').rows, read('Senate/118/positions.json'));
    assert.match(await text(), new RegExp(`118th Congress, Senate: ${votes.length} roll calls`));
    await check();
    await page.close();
  });

  test(`${label}: definitions page shows coverage, in dark mode too`, async () => {
    const { page, check, text } = await visit(`${root()}#/about`, { colorScheme: 'dark' });
    assert.match(await text(), /Contested roll call/);
    assert.match(await text(), /Topic coverage/);
    const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    assert.notEqual(bg, 'rgb(251, 250, 247)', 'dark mode uses the dark palette');
    await check();
    await page.close();
  });
}

test('live site: vote by vote adds up to the totals, filters, and opens a vote', async () => {
  const a = byName(senate, 'SANDERS').icpsr, b = byName(senate, 'MURKOWSKI').icpsr;
  const { page, check, text } = await visit(`${base}/#/h2h/Senate/118?a=${a}&b=${b}&topic=pap`);
  const { sum } = expectedPair('Senate', 118, a, b, 'pap');
  const list = await text('#votes');
  // Default list: contested votes, which is exactly the headline's n and agreement.
  assert.ok(list.includes(`${M.formatInt(sum.shared_contested)} contested votes both cast yea or nay: agreed on ${M.formatInt(sum.agree_contested)}`), list.slice(0, 300));
  // Disagreed only: every row says Disagreed.
  await page.click('#votes a:has-text("Disagreed (")');
  await page.waitForFunction(() => location.hash.includes('show=disagreed') && [...document.querySelectorAll('#votes .seg a.on')].some((x) => x.textContent.startsWith('Disagreed')));
  const tags = await page.locator('#votes .agree-tag').allTextContents();
  assert.ok(tags.length > 0 && tags.every((t) => t === 'Disagreed'));
  // A topic name opens its votes.
  const topic = (await page.locator('a.topic-name').first().textContent()).trim();
  await page.locator('a.topic-name').first().click();
  await page.waitForFunction((tp) => (document.querySelector('#votes')?.textContent || '').includes(`Topic: ${tp}`), topic);
  // A row opens the bill view.
  await page.locator('#votes .rc-list a').first().click();
  await page.waitForSelector('figure.plot-wrap');
  await check();
  await page.close();
});

// Every chamber and Congress in the build (or the newest E2E_SWEEP_LAST Congresses): head-to-head with the vote
// list, roll-call list, a vote, and a member page all render with no errors.
const manifest = read('manifest.json');
const lastN = Number(process.env.E2E_SWEEP_LAST || 0);
const newest = Math.max(...manifest.partitions.map((p) => p.congress));
for (const p of manifest.partitions.filter((x) => !lastN || x.congress > newest - lastN)) {
  test(`sweep: ${p.chamber}, Congress ${p.congress}`, async () => {
    const members = read(`${p.chamber}/${p.congress}/members.json`);
    const rc = read(`${p.chamber}/${p.congress}/rollcalls.json`);
    const [a, b] = members.slice(0, 2).map((m) => m.icpsr);
    for (const route of [`#/h2h/${p.chamber}/${p.congress}?a=${a}&b=${b}`, `#/votes/${p.chamber}/${p.congress}`,
      `#/vote/${p.chamber}/${p.congress}/${rc.rows[0].rollnumber}`, `#/member/${a}/${p.chamber}/${p.congress}`]) {
      const { page, check, text } = await visit(`${base}/${route}`);
      if (route.includes('/h2h/')) assert.match(await text(), /Vote by vote|No shared yea\/nay votes/);
      await check();
      await page.close();
    }
  });
}

test('day page: a member outside the snapshot gets a clear message', async () => {
  const { page, check, text } = await visit(`${base}/day.html#/member/999999`);
  assert.match(await text(), /Not in this snapshot/);
  assert.equal(await page.locator('a:has-text("Open this view on the full site")').count(), 1);
  await check();
  await page.close();
});
