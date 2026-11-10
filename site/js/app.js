// congress front end. Engine-agnostic: the live site passes the DuckDB-WASM engine, the day snapshot passes the
// precomputed one. Every number on screen comes from engine.query(name, params, needs) with SQL in site/sql/.
// Builds DOM with createElement/textContent only (no innerHTML with data).
(function (root) {
  const CG = (root.CG = root.CG || {});
  const M = CG.metrics;

  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'style') el.style.cssText = v; // CSSOM, allowed under the page's CSP (no inline style attributes)
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid instanceof Node ? kid : String(kid));
    return el;
  }
  const svgNS = 'http://www.w3.org/2000/svg';
  function s(tag, attrs, ...kids) {
    const el = document.createElementNS(svgNS, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v != null) el.setAttribute(k, v);
    for (const kid of kids.flat()) if (kid != null) el.append(kid instanceof Node ? kid : String(kid));
    return el;
  }

  let engine, settings, manifest, view;

  function ordinal(n) {
    const v = n % 100, suf = ['th', 'st', 'nd', 'rd'];
    return n + (suf[(v - 20) % 10] || suf[v] || suf[0]);
  }
  const partyShort = (p) => (p || '').replace(/ Party$/, '');
  function memberLabel(m) {
    const where = m.chamber === 'House' || m.district_code ? `${m.state_abbrev}${m.district_code ? '-' + m.district_code : ''}` : m.state_abbrev;
    return `${m.bioname} (${partyShort(m.party)}, ${where || '—'})`;
  }
  const link = (href, text, cls) => h('a', { href, class: cls }, text);
  const table = (...kids) => h('div', { class: 'table-wrap' }, h('table', { class: 'grid' }, ...kids));

  function parseHash() {
    const raw = location.hash.replace(/^#\/?/, '');
    const [path, qs] = raw.split('?');
    return { parts: path ? path.split('/').map(decodeURIComponent) : [], q: new URLSearchParams(qs || '') };
  }

  function partitionsFor(chamber) {
    return manifest.partitions.filter((p) => p.chamber === chamber).map((p) => p.congress).sort((a, b) => a - b);
  }
  function hasPartition(chamber, congress) {
    return manifest.partitions.some((p) => p.chamber === chamber && p.congress === congress);
  }

  function pickers(chamber, congress, routeFor) {
    const chambers = settings.scope.chambers.filter((c) => partitionsFor(c).length);
    const chamberSel = h('select', { 'aria-label': 'Chamber', onchange: (e) => {
      const list = partitionsFor(e.target.value);
      const c = list.includes(congress) ? congress : list[list.length - 1];
      location.hash = routeFor(e.target.value, c);
    } }, chambers.map((c) => h('option', { value: c, selected: c === chamber }, c)));
    const congressSel = h('select', { 'aria-label': 'Congress', onchange: (e) => (location.hash = routeFor(chamber, Number(e.target.value))) },
      partitionsFor(chamber).slice().reverse().map((c) => {
        const p = manifest.partitions.find((x) => x.chamber === chamber && x.congress === c);
        const yrs = p.first_date ? ` (${p.first_date.slice(0, 4)}–${(p.last_date || '').slice(0, 4)})` : '';
        return h('option', { value: c, selected: c === congress }, `${ordinal(c)} Congress${yrs}`);
      }));
    return h('div', { class: 'pickers' }, h('label', {}, 'Chamber', chamberSel), h('label', {}, 'Congress', congressSel));
  }

  function definition(text) {
    return h('p', { class: 'def' }, text);
  }

  function notice(text) {
    return h('div', { class: 'notice' }, text);
  }

  async function run(name, params, needs) {
    try {
      return await engine.query(name, params, needs);
    } catch (e) {
      if (e && e.code === 'not_in_snapshot') throw e;
      console.warn(e);
      throw e;
    }
  }

  // ---------- Home ----------
  async function home() {
    const ch = settings.scope.default_chamber, c = settings.scope.default_congress;
    const okC = hasPartition(ch, c) ? c : partitionsFor(ch).slice(-1)[0];
    return [
      h('h1', {}, 'Roll-call voting in the U.S. House and Senate'),
      h('p', { class: 'lede' }, 'Who votes with whom, on what, and how each vote split. Every number is computed in your browser from Voteview roll-call records; each one is shown with its definition and its count.'),
      h('div', { class: 'cards' },
        h('a', { class: 'card', href: `#/h2h/${ch}/${okC}` }, h('strong', {}, 'Head-to-head'), h('span', {}, 'Agreement between any two members who served together, on contested votes and on all votes.')),
        h('a', { class: 'card', href: `#/votes/${ch}/${okC}` }, h('strong', {}, 'Roll calls'), h('span', {}, 'Every roll call in a Congress: the split by party, who crossed party lines, and the NOMINATE cutting line.')),
        h('a', { class: 'card', href: '#/about' }, h('strong', {}, 'Definitions and sources'), h('span', {}, 'How each metric is computed, what the data covers, and what is still untagged.'))),
      h('p', { class: 'muted' }, `Data: ${manifest.partitions.length} chamber-Congresses loaded from the manifest.`),
    ];
  }

  // ---------- Head-to-head ----------
  async function headToHead(chamber, congress, q) {
    const out = [h('h1', {}, 'Head-to-head'), pickers(chamber, congress, (c, n) => `#/h2h/${c}/${n}`)];
    const members = await run('members', [chamber, congress], [[chamber, congress]]);
    const a = Number(q.get('a')) || null, b = Number(q.get('b')) || null;
    const route = (na, nb, scope) => {
      const p = new URLSearchParams();
      if (na) p.set('a', na);
      if (nb) p.set('b', nb);
      if (scope) p.set('scope', scope);
      return `#/h2h/${chamber}/${congress}?${p}`;
    };
    const scope = q.get('scope') === 'congress' ? 'congress' : 'all';
    const sel = (label, value, onPick) => h('label', {}, label, h('select', { onchange: (e) => onPick(Number(e.target.value) || null) },
      h('option', { value: '' }, 'Pick a member…'),
      members.map((m) => h('option', { value: m.icpsr, selected: m.icpsr === value }, memberLabel({ ...m, chamber })))));
    out.push(h('div', { class: 'pickers' },
      sel('Member A', a, (v) => (location.hash = route(v, b, scope))),
      sel('Member B', b, (v) => (location.hash = route(a, v, scope))),
      h('button', { type: 'button', onclick: () => (location.hash = route(b, a, scope)), disabled: !(a && b) }, 'Swap')));
    if (!(a && b)) return [...out, h('p', { class: 'muted' }, 'Pick two members of this chamber and Congress.')];
    if (a === b) return [...out, notice('Pick two different members.')];

    const shared = (await run('shared_congresses', [a, b, chamber], [])).map((r) => Number(r.congress));
    const span = scope === 'congress' ? [congress] : shared.filter((c) => hasPartition(chamber, c));
    const missing = scope === 'all' ? shared.filter((c) => !hasPartition(chamber, c)) : [];
    out.push(h('div', { class: 'seg', role: 'group', 'aria-label': 'Congresses counted' },
      h('a', { href: route(a, b, 'all'), class: scope === 'all' ? 'on' : '' }, `All Congresses together (${shared.length})`),
      h('a', { href: route(a, b, 'congress'), class: scope === 'congress' ? 'on' : '' }, `${ordinal(congress)} only`)));
    const t = settings.analysis.contested_threshold, minN = settings.analysis.min_shared_votes;
    const rows = span.length ? await run('h2h', [a, b, chamber, Math.min(...span), Math.max(...span), t], span.map((c) => [chamber, c])) : [];
    const used = rows.filter((r) => span.includes(Number(r.congress)));
    const sum = M.summarizeH2h(used, minN);
    const names = [a, b].map((id) => members.find((m) => m.icpsr === id));

    const stat = (title, pct, n, shown, def) => h('div', { class: 'stat' },
      h('div', { class: 'stat-title' }, title),
      shown ? h('div', { class: 'stat-value' }, M.formatPct(pct)) : h('div', { class: 'stat-value hidden-n' }, 'Not shown'),
      h('div', { class: 'stat-n' }, shown ? `n = ${M.formatInt(n)} shared votes` : `n = ${M.formatInt(n)}, below the minimum of ${minN}`),
      definition(def));
    out.push(h('section', { class: 'result' },
      h('h2', {}, `${names[0] ? names[0].bioname : a} and ${names[1] ? names[1].bioname : b}`),
      h('div', { class: 'stats' },
        stat('Agreement on contested votes', sum.pct_contested, sum.shared_contested, sum.contested_shown,
          `Share of contested roll calls where both voted the same way. Contested: the smaller side had at least ${M.formatPct(t, 0)} of the yea and nay votes. Shared: both voted yea or nay (present and not voting are left out).`),
        stat('Agreement on all shared votes', sum.pct_all, sum.shared_all, sum.all_shown,
          'The same measure over every shared roll call, including near-unanimous ones. Shown for comparison: lopsided votes push every pair toward agreement.')),
      missing.length ? notice(`Not loaded in this build: ${missing.map(ordinal).join(', ')} Congress. Totals cover only the Congresses listed below.`) : null,
      used.length ? table(
        h('thead', {}, h('tr', {}, h('th', {}, 'Congress'), h('th', {}, 'Contested'), h('th', {}, 'n'), h('th', {}, 'All'), h('th', {}, 'n'))),
        h('tbody', {}, used.map((r) => {
          const one = M.summarizeH2h([r], minN);
          return h('tr', {}, h('td', {}, ordinal(Number(r.congress))),
            h('td', {}, one.contested_shown ? M.formatPct(one.pct_contested) : '—'), h('td', {}, M.formatInt(r.shared_contested)),
            h('td', {}, one.all_shown ? M.formatPct(one.pct_all) : '—'), h('td', {}, M.formatInt(r.shared_all)));
        }))) : h('p', { class: 'muted' }, 'No shared yea/nay votes in the selected Congresses.'),
      h('p', { class: 'muted' }, `Cells with n below ${minN} show —.`),
      h('p', {}, link(`#/member/${a}`, `${names[0] ? names[0].bioname : a}: member page`), ' · ', link(`#/member/${b}`, `${names[1] ? names[1].bioname : b}: member page`))));
    return out;
  }

  // ---------- Roll-call list ----------
  async function rollcallList(chamber, congress, q) {
    const out = [h('h1', {}, 'Roll calls'), pickers(chamber, congress, (c, n) => `#/votes/${c}/${n}`)];
    const rows = await run('rollcalls', [chamber, congress], [[chamber, congress]]);
    const filter = (q.get('q') || '').toLowerCase();
    const shown = filter ? rows.filter((r) => [r.bill_number, r.vote_question, r.description, r.crs_policy_area_resolved].join(' ').toLowerCase().includes(filter)) : rows;
    const limit = Number(q.get('n')) || 100;
    const input = h('input', { type: 'search', value: q.get('q') || '', placeholder: 'Filter by bill, question, text or topic', 'aria-label': 'Filter roll calls' });
    out.push(h('form', { class: 'filter', onsubmit: (e) => { e.preventDefault(); location.hash = `#/votes/${chamber}/${congress}?q=${encodeURIComponent(input.value)}`; } },
      input, h('button', { type: 'submit' }, 'Filter')));
    out.push(h('p', { class: 'muted' }, `${M.formatInt(shown.length)} of ${M.formatInt(rows.length)} roll calls.`));
    out.push(h('ol', { class: 'rc-list' }, shown.slice(0, limit).map((r) => h('li', {},
      h('a', { href: `#/vote/${chamber}/${congress}/${r.rollnumber}` },
        h('span', { class: 'rc-top' }, `#${r.rollnumber} · ${r.date || ''}${r.bill_number ? ' · ' + r.bill_number : ''}`),
        h('span', { class: 'rc-q' }, r.vote_question || r.description || 'Roll call'),
        h('span', { class: 'rc-n' }, `Yea ${r.yea_n} – Nay ${r.nay_n}${r.crs_policy_area_resolved ? ' · ' + r.crs_policy_area_resolved : ''}`))))));
    if (shown.length > limit) {
      const p = new URLSearchParams(q); p.set('n', limit + 200);
      out.push(h('p', {}, link(`#/votes/${chamber}/${congress}?${p}`, 'Show more', 'button-link')));
    }
    return out;
  }

  // ---------- Bill view ----------
  function topicLine(r) {
    const bits = [];
    if (r.pap_majortopic != null) bits.push(`Policy Agendas: ${settings.topics.pap_major_topics[r.pap_majortopic] || 'code ' + r.pap_majortopic}${r.pap_subtopic ? ' (' + r.pap_subtopic + ')' : ''}`);
    else bits.push('Policy Agendas: not coded');
    if (r.crs_policy_area_resolved) bits.push(`CRS policy area: ${r.crs_policy_area_resolved}${r.crs_source === 'inherited' ? ' (inherited from ' + r.bill_number + ')' : ''}`);
    else bits.push('CRS policy area: none');
    return bits.join(' · ');
  }

  function plot(points, rc) {
    const pts = points.filter((p) => p.nominate_dim1 != null && p.nominate_dim2 != null);
    if (!pts.length) return null;
    const S = 300, pad = 12, sc = (v) => pad + ((v + 1) / 2) * (S - 2 * pad), sy = (v) => pad + ((1 - v) / 2) * (S - 2 * pad);
    const line = M.cuttingLine(rc.nominate_mid_1, rc.nominate_mid_2, rc.nominate_spread_1, rc.nominate_spread_2, settings.analysis.nominate_dim2_weight);
    const svg = s('svg', { viewBox: `0 0 ${S} ${S}`, class: 'plot', role: 'img', 'aria-label': 'Members by NOMINATE position, marked by vote' },
      s('circle', { cx: S / 2, cy: S / 2, r: (S - 2 * pad) / 2, class: 'plot-frame' }),
      s('line', { x1: pad, y1: S / 2, x2: S - pad, y2: S / 2, class: 'plot-axis' }),
      s('line', { x1: S / 2, y1: pad, x2: S / 2, y2: S - pad, class: 'plot-axis' }),
      pts.map((p) => s('circle', { cx: sc(p.nominate_dim1).toFixed(1), cy: sy(p.nominate_dim2).toFixed(1), r: 3.2, class: `pt ${p.position === 1 ? 'yea' : p.position === -1 ? 'nay' : 'nv'}` },
        s('title', {}, `${p.bioname} (${partyShort(p.party)}): ${M.positionLabel(p.position)}`))),
      line ? s('line', { x1: sc(line[0][0]), y1: sy(line[0][1]), x2: sc(line[1][0]), y2: sy(line[1][1]), class: 'cut' }) : null);
    return h('figure', { class: 'plot-wrap' }, svg,
      h('figcaption', {}, h('span', { class: 'key yea' }, 'Yea'), h('span', { class: 'key nay' }, 'Nay'), h('span', { class: 'key nv' }, 'Present / not voting'),
        h('br'), line ? 'Line: Voteview NOMINATE cutting line for this roll call (midpoint and spread from Voteview). '
          : 'Voteview has no cutting line for this roll call (none is estimated for lopsided votes). ',
        'Axes: DW-NOMINATE first (horizontal) and second (vertical) dimensions.'));
  }

  async function billView(chamber, congress, roll) {
    const needs = [[chamber, congress]];
    const [rc] = await run('rollcall', [chamber, congress, roll], needs);
    if (!rc) return [h('h1', {}, 'Roll call not found'), link(`#/votes/${chamber}/${congress}`, 'Back to the list')];
    const [split, crossers, points] = await Promise.all([
      run('bill_party_split', [chamber, congress, roll], needs), run('bill_crossers', [chamber, congress, roll], needs),
      run('bill_points', [chamber, congress, roll], needs)]);
    const total = (r) => r.yea + r.nay + r.not_voting;
    const t = settings.analysis.contested_threshold;
    const contested = rc.minority_share != null && rc.minority_share >= t;
    return [
      h('p', { class: 'crumb' }, link(`#/votes/${chamber}/${congress}`, `← ${chamber}, ${ordinal(congress)} Congress`)),
      h('h1', {}, `${rc.bill_number ? rc.bill_number + ': ' : ''}${rc.vote_question || 'Roll call ' + roll}`),
      h('p', { class: 'muted' }, `${chamber} roll call ${roll} · ${rc.date || 'date unknown'}${rc.vote_result ? ' · Result: ' + rc.vote_result : ''}`),
      rc.vote_desc || rc.dtl_desc ? h('p', {}, rc.vote_desc || rc.dtl_desc) : null,
      h('p', { class: 'muted' }, topicLine(rc)),
      h('div', { class: 'stats' },
        h('div', { class: 'stat' }, h('div', { class: 'stat-title' }, 'Yea – Nay'), h('div', { class: 'stat-value' }, `${rc.yea_n} – ${rc.nay_n}`),
          h('div', { class: 'stat-n' }, `${rc.not_voting_n} present / not voting`),
          definition(`Counted from members' recorded votes. Smaller side: ${M.formatPct(rc.minority_share)} of yea and nay votes, so this roll call is ${contested ? '' : 'not '}contested at the ${M.formatPct(t, 0)} threshold.`))),
      h('h2', {}, 'By party'),
      table(
        h('thead', {}, h('tr', {}, h('th', {}, 'Party'), h('th', {}, 'Yea'), h('th', {}, 'Nay'), h('th', {}, 'Not voting'), h('th', { class: 'barcol' }, ''))),
        h('tbody', {}, split.map((r) => h('tr', {}, h('td', {}, r.party), h('td', {}, r.yea), h('td', {}, r.nay), h('td', {}, r.not_voting),
          h('td', { class: 'barcol' }, h('span', { class: 'bar' },
            h('span', { class: 'bar-yea', style: `width:${(100 * r.yea) / total(r)}%` }), h('span', { class: 'bar-nay', style: `width:${(100 * r.nay) / total(r)}%` }))))))),
      h('h2', {}, `Voted against their party's majority (${crossers.length})`),
      definition("A member is listed when their yea or nay differs from the majority of their own party's yea and nay votes. A party split exactly evenly has no majority."),
      crossers.length ? h('ul', { class: 'people' }, crossers.map((m) => h('li', {}, link(`#/member/${m.icpsr}`, `${m.bioname} (${partyShort(m.party)}, ${m.state_abbrev})`), ` voted ${M.positionLabel(m.position)}`)))
        : h('p', { class: 'muted' }, 'None.'),
      h('h2', {}, 'By bloc'),
      h('p', { class: 'muted' }, 'Bloc splits arrive with the blocs view (community detection on the agreement network). Not built yet.'),
      h('h2', {}, 'NOMINATE map'),
      plot(points, rc),
    ];
  }

  // ---------- Member page ----------
  async function memberPage(icpsr, chamber, congress) {
    const rows = await run('member', [icpsr], []);
    if (!rows.length) return [h('h1', {}, 'Member not found')];
    const last = rows[rows.length - 1];
    const out = [h('h1', {}, last.bioname),
      h('p', { class: 'muted' }, [last.born ? `Born ${last.born}` : null, last.died ? `died ${last.died}` : null, last.bioguide_id ? `Bioguide ID ${last.bioguide_id}` : null].filter(Boolean).join(' · ')),
      table(
        h('thead', {}, h('tr', {}, h('th', {}, 'Congress'), h('th', {}, 'Chamber'), h('th', {}, 'Party'), h('th', {}, 'State'), h('th', {}, 'NOMINATE 1'), h('th', {}, 'Links'))),
        h('tbody', {}, rows.map((r) => h('tr', {}, h('td', {}, ordinal(r.congress)), h('td', {}, r.chamber), h('td', {}, partyShort(r.party)),
          h('td', {}, `${r.state_abbrev}${r.chamber === 'House' && r.district_code ? '-' + r.district_code : ''}`),
          h('td', {}, r.nominate_dim1 == null ? '—' : Number(r.nominate_dim1).toFixed(3)),
          h('td', {}, hasPartition(r.chamber, r.congress) ? [link(`#/member/${icpsr}/${r.chamber}/${r.congress}`, 'Votes'), ' · ', link(`#/h2h/${r.chamber}/${r.congress}?a=${icpsr}`, 'Head-to-head')] : 'not loaded'))))),
      definition('NOMINATE 1: DW-NOMINATE first-dimension score from Voteview, estimated from all of this member\'s roll-call votes. It locates members relative to each other; it is not a label.'),
      h('p', { class: 'muted' }, 'By topic and blocs: next on the build list.')];
    if (chamber && congress) {
      const votes = await run('member_votes', [icpsr, chamber, congress], [[chamber, congress]]);
      const counts = { 1: 0, '-1': 0, 0: 0 };
      votes.forEach((v) => counts[v.position]++);
      out.push(h('h2', {}, `${ordinal(congress)} Congress, ${chamber}: ${votes.length} roll calls`),
        h('p', { class: 'muted' }, `Yea ${counts[1]} · Nay ${counts[-1]} · Present / not voting ${counts[0]}`),
        h('ol', { class: 'rc-list' }, votes.slice(0, 300).map((v) => h('li', {}, h('a', { href: `#/vote/${chamber}/${congress}/${v.rollnumber}` },
          h('span', { class: 'rc-top' }, `#${v.rollnumber} · ${v.date || ''}${v.bill_number ? ' · ' + v.bill_number : ''}`),
          h('span', { class: 'rc-q' }, v.vote_question || v.description || 'Roll call'),
          h('span', { class: `rc-n pos-${v.position === 1 ? 'yea' : v.position === -1 ? 'nay' : 'nv'}` }, `${M.positionLabel(v.position)} · result ${v.yea_n}–${v.nay_n}`))))),
        votes.length > 300 ? h('p', { class: 'muted' }, `Showing the first 300 of ${votes.length}.`) : null);
    }
    return out;
  }

  // ---------- About ----------
  async function about() {
    const a = settings.analysis;
    const cov = engine.coverage ? await engine.coverage() : null;
    return [
      h('h1', {}, 'Definitions and sources'),
      h('h2', {}, 'Metrics'),
      h('dl', { class: 'defs' },
        h('dt', {}, 'Shared vote'), h('dd', {}, 'A roll call on which both members voted yea or nay. Present and not voting are left out.'),
        h('dt', {}, 'Contested roll call'), h('dd', {}, `The smaller side had at least ${M.formatPct(a.contested_threshold, 0)} of the yea and nay votes cast by members.`),
        h('dt', {}, 'Agreement'), h('dd', {}, 'Shared votes on which both voted the same way, divided by shared votes. Always shown with its n.'),
        h('dt', {}, 'Minimum n'), h('dd', {}, `Results built on fewer than ${a.min_shared_votes} shared votes are not shown.`),
        h('dt', {}, 'Voted against party majority'), h('dd', {}, "A yea or nay that differs from the majority of the member's own party's yea and nay votes on that roll call.")),
      h('h2', {}, 'Sources'),
      h('ul', {},
        h('li', {}, 'Voteview (Lewis, Poole, Rosenthal, Boche, Rudkin and Sonnet): members, roll calls, member votes, DW-NOMINATE, and CRS policy areas.'),
        h('li', {}, 'Policy Agendas Project roll-call topic codes (comparativeagendas.net, 79th–118th Congress), joined on Congress, chamber and roll number.'),
        h('li', {}, 'CRS policy area: amendment and procedural votes with no tag take the area of their bill (same bill number, same Congress).')),
      cov ? h('h2', {}, 'Topic coverage') : null,
      cov ? table(
        h('thead', {}, h('tr', {}, h('th', {}, 'Chamber'), h('th', {}, 'Congress'), h('th', {}, 'Roll calls'), h('th', {}, 'CRS untagged'), h('th', {}, 'PAP untagged'))),
        h('tbody', {}, cov.crs_and_pap_by_partition.map((r) => h('tr', {}, h('td', {}, r.chamber), h('td', {}, ordinal(r.congress)), h('td', {}, M.formatInt(r.rollcalls)),
          h('td', {}, M.formatPct(r.crs_untagged_share)), h('td', {}, M.formatPct(r.pap_untagged_share)))))) : null,
      h('p', { class: 'muted' }, `Settings: contested threshold ${a.contested_threshold}, minimum shared votes ${a.min_shared_votes}. Data built ${manifest.generated_at || 'unknown'}.`),
    ];
  }

  async function render() {
    const { parts, q } = parseHash();
    const main = view;
    main.replaceChildren(h('p', { class: 'loading' }, 'Loading…'));
    document.querySelectorAll('nav a').forEach((a) => a.classList.toggle('on', (a.getAttribute('href') || '').split('/')[1] === (parts[0] || '')));
    try {
      let kids;
      const [r, x, y, z] = parts;
      const defCh = settings.scope.default_chamber;
      const valid = (ch, c) => hasPartition(ch, Number(c));
      if (r === 'h2h') kids = valid(x, y) ? await headToHead(x, Number(y), q) : await headToHead(defCh, partitionsFor(defCh).slice(-1)[0], q);
      else if (r === 'votes') kids = valid(x, y) ? await rollcallList(x, Number(y), q) : await rollcallList(defCh, partitionsFor(defCh).slice(-1)[0], q);
      else if (r === 'vote' && valid(x, y)) kids = await billView(x, Number(y), Number(z));
      else if (r === 'member' && x) kids = await memberPage(Number(x), y, y ? Number(z) : null);
      else if (r === 'about') kids = await about();
      else kids = await home();
      if (main === view) main.replaceChildren(...kids.flat().filter(Boolean));
    } catch (e) {
      main.replaceChildren(h('h1', {}, e && e.code === 'not_in_snapshot' ? 'Not in this snapshot' : 'Something went wrong'),
        h('p', {}, e && e.code === 'not_in_snapshot' ? e.message : 'This view could not be computed. Details are in the browser console.'),
        link('#/', 'Back to the start'));
      if (!(e && e.code === 'not_in_snapshot')) console.warn(e);
    }
    window.scrollTo(0, 0);
  }

  async function start(eng, sett, mountId = 'app') {
    engine = eng; settings = sett;
    view = document.getElementById(mountId);
    manifest = await engine.manifest();
    window.addEventListener('hashchange', render);
    await render();
  }

  CG.app = { start };
})(globalThis);
