// Live-site start: read the mirrored settings, then run the app on result files fetched from ./results/.
(async function () {
  try {
    const r = await fetch('settings.json');
    if (!r.ok) throw new Error(`settings.json: HTTP ${r.status}`);
    await globalThis.CG.app.start(globalThis.CG.createData(null), await r.json());
  } catch (e) {
    console.warn(e);
    document.getElementById('app').textContent = 'The page could not load its data. Reload to try again.';
  }
})();
