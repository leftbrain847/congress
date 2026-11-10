// The only computation done in the browser: aggregating the pair a visitor picks. Everything per roll call (counts,
// contested share, topics, party splits, crossers) arrives precomputed from the pipeline.
// Definitions match site/sql/h2h.sql and h2h_by_topic.sql; tests/py/test_compute_parity.py runs this file in node
// against that SQL on the fixture.
(function (root) {
  const CG = (root.CG = root.CG || {});
  const POS = { y: 1, n: -1, p: 0 };

  function topicOf(row, scheme) {
    if (scheme === 'pap') return row.pap_majortopic == null ? '' : String(row.pap_majortopic);
    return row.crs_policy_area_resolved || '';
  }

  // parts: [{congress, rows (rollcalls.json rows), positions (positions.json)}]
  // Returns per-Congress rows and per-topic rows, each with shared_all, agree_all, shared_contested, agree_contested.
  function pairAgreement(parts, a, b, threshold, scheme) {
    const byCongress = [], byTopic = new Map();
    const blank = () => ({ shared_all: 0, agree_all: 0, shared_contested: 0, agree_contested: 0 });
    for (const { congress, rows, positions } of parts) {
      const ia = positions.order.indexOf(a), ib = positions.order.indexOf(b);
      if (ia < 0 || ib < 0) continue;
      const c = blank();
      for (const r of rows) {
        const s = positions.by_roll[String(r.rollnumber)];
        if (!s) continue;
        const pa = POS[s[ia]], pb = POS[s[ib]];
        if (!pa || !pb) continue; // both must have voted yea or nay
        const same = pa === pb ? 1 : 0;
        const contested = r.minority_share != null && r.minority_share >= threshold;
        const t = topicOf(r, scheme);
        if (!byTopic.has(t)) byTopic.set(t, blank());
        for (const acc of [c, byTopic.get(t)]) {
          acc.shared_all++; acc.agree_all += same;
          if (contested) { acc.shared_contested++; acc.agree_contested += same; }
        }
      }
      if (c.shared_all) byCongress.push({ congress, ...c });
    }
    const topics = [...byTopic.entries()].map(([topic, v]) => ({ topic, ...v })).sort((x, y) => (x.topic < y.topic ? -1 : x.topic > y.topic ? 1 : 0));
    return { byCongress, byTopic: topics };
  }

  function sharedCongresses(rowsA, rowsB, chamber) {
    const inB = new Set(rowsB.filter((r) => r.chamber === chamber).map((r) => r.congress));
    return [...new Set(rowsA.filter((r) => r.chamber === chamber && inB.has(r.congress)).map((r) => r.congress))].sort((x, y) => x - y);
  }

  // Members' positions on one roll call, for the NOMINATE map (bill_points.sql).
  function points(members, positions, roll) {
    const s = positions.by_roll[String(roll)] || '';
    const byId = new Map(members.map((m) => [m.icpsr, m]));
    const out = [];
    positions.order.forEach((icpsr, i) => {
      if (!(s[i] in POS)) return;
      const m = byId.get(icpsr);
      out.push({ icpsr, bioname: m.bioname, party: m.party, party_code: m.party_code,
        nominate_dim1: m.nominate_dim1, nominate_dim2: m.nominate_dim2, position: POS[s[i]] });
    });
    return out;
  }

  // One member's positions across a Congress (member_votes.sql).
  function memberVotes(icpsr, rows, positions) {
    const i = positions.order.indexOf(icpsr);
    if (i < 0) return [];
    const out = [];
    for (const r of rows) {
      const s = positions.by_roll[String(r.rollnumber)];
      if (!s || !(s[i] in POS)) continue;
      out.push({ rollnumber: r.rollnumber, date: r.date, bill_number: r.bill_number, vote_question: r.vote_question,
        description: r.description, position: POS[s[i]], yea_n: r.yea_n, nay_n: r.nay_n, minority_share: r.minority_share });
    }
    return out;
  }

  CG.compute = { pairAgreement, sharedCongresses, points, memberVotes, topicOf };
})(globalThis);
