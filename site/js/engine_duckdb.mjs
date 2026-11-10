// Live-site engine: DuckDB-WASM, self-hosted under ./vendor (no outside loads). Loads members.parquet at start and
// each chamber/Congress partition the first time a view needs it. SQL comes from site/sql (bundled by the build).
import * as duckdb from '@duckdb/duckdb-wasm';
import SQL from './sql.generated.js';

const base = new URL('.', document.baseURI);
const url = (p) => new URL(p, base).href;

function normalize(rows) {
  return rows.map((r) => {
    const o = {};
    for (const [k, v] of Object.entries(r)) o[k] = typeof v === 'bigint' ? Number(v) : v;
    return o;
  });
}

async function fetchJson(p) {
  const r = await fetch(url(p));
  if (!r.ok) throw new Error(`${p}: HTTP ${r.status}`);
  return r.json();
}

export async function createEngine() {
  const bundles = {
    mvp: { mainModule: url('vendor/duckdb-mvp.wasm'), mainWorker: url('vendor/duckdb-browser-mvp.worker.js') },
    eh: { mainModule: url('vendor/duckdb-eh.wasm'), mainWorker: url('vendor/duckdb-browser-eh.worker.js') },
  };
  const bundle = await duckdb.selectBundle(bundles);
  const worker = new Worker(bundle.mainWorker);
  const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
  await db.instantiate(bundle.mainModule);
  const conn = await db.connect();
  // Parquet is an extension in DuckDB-WASM. Load it from this site (vendor/extensions, hash-pinned at build time),
  // never from extensions.duckdb.org, and never auto-load anything else.
  await conn.query('SET autoinstall_known_extensions = false');
  await conn.query('SET autoload_known_extensions = false');
  await conn.query(`SET custom_extension_repository = '${url('vendor/extensions').replace(/'/g, "''")}'`);
  await conn.query('INSTALL parquet');
  await conn.query('LOAD parquet');

  const manifest = await fetchJson('data/manifest.json');
  const loaded = new Set();

  async function loadFile(rel, name) {
    const r = await fetch(url(`data/${rel}`));
    if (!r.ok) throw new Error(`${rel}: HTTP ${r.status}`);
    await db.registerFileBuffer(name, new Uint8Array(await r.arrayBuffer()));
  }

  await loadFile(manifest.members, 'members.parquet');
  await conn.query("CREATE TABLE members AS SELECT * FROM read_parquet('members.parquet')");

  let created = false;
  async function ensure(needs) {
    const todo = needs.filter(([ch, c]) => !loaded.has(`${ch}|${c}`));
    for (const [ch, c] of todo) {
      const p = manifest.partitions.find((x) => x.chamber === ch && x.congress === c);
      if (!p) continue;
      const vn = `votes_${ch}_${c}.parquet`, rn = `rollcalls_${ch}_${c}.parquet`;
      await Promise.all([loadFile(p.votes, vn), loadFile(p.rollcalls, rn)]);
      if (!created) {
        await conn.query(`CREATE TABLE votes AS SELECT * FROM read_parquet('${vn}')`);
        await conn.query(`CREATE TABLE rollcalls AS SELECT * FROM read_parquet('${rn}')`);
        created = true;
      } else {
        await conn.query(`INSERT INTO votes SELECT * FROM read_parquet('${vn}')`);
        await conn.query(`INSERT INTO rollcalls SELECT * FROM read_parquet('${rn}')`);
      }
      loaded.add(`${ch}|${c}`);
    }
  }

  let queue = Promise.resolve();
  const serial = (fn) => (queue = queue.then(fn, fn));

  return {
    manifest: async () => manifest,
    coverage: async () => fetchJson(`data/${manifest.coverage}`),
    query: (name, params, needs = []) => serial(async () => {
      if (!(name in SQL)) throw new Error(`unknown query ${name}`);
      await ensure(needs);
      const stmt = await conn.prepare(SQL[name]);
      try {
        const res = await stmt.query(...params);
        return normalize(res.toArray().map((r) => r.toJSON()));
      } finally {
        await stmt.close();
      }
    }),
  };
}

async function boot() {
  const settings = await fetchJson('settings.json');
  try {
    const engine = await createEngine();
    await globalThis.CG.app.start(engine, settings);
  } catch (e) {
    console.warn(e);
    const el = document.getElementById('app');
    el.textContent = 'The data engine could not start in this browser. Try a current version of Chrome, Firefox, Safari or Edge.';
  }
}

boot();
