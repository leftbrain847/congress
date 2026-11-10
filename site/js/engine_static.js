// Day-snapshot engine: answers the same queries as the DuckDB engine from results precomputed by
// pipeline/snapshot_page.py, which runs the site's SQL (site/sql) in Python DuckDB. No math happens here: queries are
// looked up, or reshaped from stored rows (bill_points, member_votes, shared_congresses).
// tests/py/test_snapshot_parity.py checks every reshaped answer against the SQL.
(function (root) {
  const CG = (root.CG = root.CG || {});

  function notInSnapshot(msg) {
    const e = new Error(msg);
    e.code = 'not_in_snapshot';
    return e;
  }

  function createStaticEngine(D) {
    const key = (ch, c) => `${ch}|${c}`;
    const need = (obj, k, what) => {
      if (!obj || !(k in obj)) throw notInSnapshot(`${what} is not in this day snapshot, which covers the ${D.scope_label}. The live site has every Congress.`);
      return obj[k];
    };
    const POS = { y: 1, n: -1, p: 0 };
    const pairCache = new Map();
    function pairMap(ch, c) {
      const k = key(ch, c);
      if (pairCache.has(k)) return pairCache.get(k);
      const P = D.h2h.by_partition[k];
      if (!P) return null;
      const m = new Map();
      for (let i = 0; i < P.rows.length; i += 6) {
        const r = P.rows;
        m.set(`${P.order[r[i]]}|${P.order[r[i + 1]]}`, [r[i + 2], r[i + 3], r[i + 4], r[i + 5]]);
      }
      pairCache.set(k, m);
      return m;
    }

    function positions(ch, c, roll) {
      const P = need(D.positions, key(ch, c), `${ch}, Congress ${c}`);
      const str = need(P.by_roll, String(roll), `Roll call ${roll}`);
      return { order: P.order, str };
    }

    const Q = {
      members: (ch, c) => need(D.members, key(ch, c), `${ch}, Congress ${c}`),
      member: (icpsr) => need(D.member, String(icpsr), 'This member'),
      shared_congresses: (a, b, ch) => {
        const ra = need(D.member, String(a), 'This member'), rb = need(D.member, String(b), 'This member');
        const cb = new Set(rb.filter((r) => r.chamber === ch).map((r) => r.congress));
        return [...new Set(ra.filter((r) => r.chamber === ch && cb.has(r.congress)).map((r) => r.congress))].sort((x, y) => x - y).map((congress) => ({ congress }));
      },
      h2h: (a, b, ch, from, to, t) => {
        const H = D.h2h;
        if (t !== H.threshold) throw notInSnapshot(`This snapshot was computed at a contested threshold of ${H.threshold}.`);
        const rows = [];
        for (let c = from; c <= to; c++) {
          const pairs = pairMap(ch, c);
          if (!pairs) continue;
          const [x, y] = a < b ? [a, b] : [b, a];
          const r = pairs.get(`${x}|${y}`);
          if (r) rows.push({ congress: c, shared_all: r[0], agree_all: r[1], shared_contested: r[2], agree_contested: r[3] });
        }
        return rows;
      },
      rollcalls: (ch, c) => need(D.rollcalls, key(ch, c), `${ch}, Congress ${c}`),
      rollcall: (ch, c, roll) => {
        const extra = need(D.rollcall[key(ch, c)] || {}, String(roll), `Roll call ${roll}`);
        const row = Q.rollcalls(ch, c).find((r) => r.rollnumber === roll);
        return [{ ...row, ...extra }];
      },
      bill_party_split: (ch, c, roll) => need(D.split[key(ch, c)] || {}, String(roll), `Roll call ${roll}`),
      bill_crossers: (ch, c, roll) => {
        const byId = new Map(Q.members(ch, c).map((m) => [m.icpsr, m]));
        return need(D.crossers[key(ch, c)] || {}, String(roll), `Roll call ${roll}`).map(([icpsr, position]) => {
          const m = byId.get(icpsr);
          return { icpsr, bioname: m.bioname, party: m.party, state_abbrev: m.state_abbrev, position, party_majority: -position };
        });
      },
      bill_points: (ch, c, roll) => {
        const { order, str } = positions(ch, c, roll);
        const byId = new Map(Q.members(ch, c).map((m) => [m.icpsr, m]));
        const out = [];
        order.forEach((icpsr, i) => {
          const ch_ = str[i];
          if (!(ch_ in POS)) return;
          const m = byId.get(icpsr);
          out.push({ icpsr, bioname: m.bioname, party: m.party, party_code: m.party_code,
            nominate_dim1: m.nominate_dim1, nominate_dim2: m.nominate_dim2, position: POS[ch_] });
        });
        return out;
      },
      member_votes: (icpsr, ch, c) => {
        const P = need(D.positions, key(ch, c), `${ch}, Congress ${c}`);
        const i = P.order.indexOf(icpsr);
        if (i < 0) return [];
        const out = [];
        for (const r of Q.rollcalls(ch, c)) {
          const s = P.by_roll[String(r.rollnumber)];
          if (!s || !(s[i] in POS)) continue;
          out.push({ rollnumber: r.rollnumber, date: r.date, bill_number: r.bill_number, vote_question: r.vote_question,
            description: r.description, position: POS[s[i]], yea_n: r.yea_n, nay_n: r.nay_n, minority_share: r.minority_share });
        }
        return out;
      },
    };

    return {
      manifest: async () => D.manifest,
      coverage: async () => D.coverage,
      query: async (name, params) => {
        if (!Q[name]) throw new Error(`unknown query ${name}`);
        return Q[name](...params);
      },
      _sync: (name, params) => Q[name](...params),
    };
  }

  CG.createStaticEngine = createStaticEngine;
})(globalThis);
