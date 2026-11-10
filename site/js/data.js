// Loads precomputed result files (pipeline/results.py). The live site fetches them from ./results/ one Congress at a
// time; the day snapshot passes the same files embedded in the page. Each file is fetched once and cached.
(function (root) {
  const CG = (root.CG = root.CG || {});

  function notInSnapshot(what) {
    const e = new Error(`${what} is not in this day snapshot. The live site has every Congress.`);
    e.code = 'not_in_snapshot';
    return e;
  }

  function createData(embedded) {
    const cache = new Map();
    function get(path) {
      if (!cache.has(path)) {
        cache.set(path, (async () => {
          if (embedded) {
            if (!(path in embedded)) throw notInSnapshot(path.endsWith('.json') && path.startsWith('members/') ? 'This member' : 'This Congress');
            return embedded[path];
          }
          const r = await fetch(`results/${path}`);
          if (!r.ok) throw new Error(`results/${path}: HTTP ${r.status}`);
          return r.json();
        })());
        cache.get(path).catch(() => cache.delete(path));
      }
      return cache.get(path);
    }
    const part = (ch, c) => `${ch}/${c}`;
    return {
      manifest: () => get('manifest.json'),
      coverage: () => get('coverage.json'),
      members: (ch, c) => get(`${part(ch, c)}/members.json`),
      rollcalls: (ch, c) => get(`${part(ch, c)}/rollcalls.json`),
      positions: (ch, c) => get(`${part(ch, c)}/positions.json`),
      member: (icpsr) => get(`members/${Number(icpsr)}.json`),
    };
  }

  CG.createData = createData;
})(globalThis);
