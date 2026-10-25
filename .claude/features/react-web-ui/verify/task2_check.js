const puppeteer = require('puppeteer-core');
let failures = 0;
const check = (label, ok, detail = '') => { if (!ok) failures++; console.log((ok ? 'PASS ' : 'FAIL ') + label + (detail ? '  ' + detail : '')); };
(async () => {
  const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const page = await browser.newPage();
  await page.setViewport({ width: 1200, height: 700 });
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });

  await page.goto('http://localhost:5173/', { waitUntil: 'networkidle0' });
  check('title', (await page.title()) === 'AIControl');
  check('landing heading, hint and snippet', (await page.$eval('main h1', (e) => e.textContent)) === 'Monitoring'
    && (await page.$eval('main p', (e) => e.textContent)) === 'Click Monitoring to browse your conversations.'
    && (await page.$eval('main pre', (e) => e.textContent)).includes('aicontrol.volume("my-first-volume")'));
  check('sidebar: brand + Monitoring, collapsed', (await page.$eval('.sidebar .brand', (e) => e.textContent)) === 'AIControl'
    && (await page.$eval('#monitoring > summary', (e) => e.textContent)) === 'Monitoring'
    && !(await page.$eval('#monitoring', (d) => d.open)));

  // Same layout as the old server-rendered landing page (same CSS): compare element boxes.
  const boxes = (p) => p.evaluate(() => ['.sidebar', '.brand', '#monitoring > summary', 'main h1', 'main p', 'main h3', 'main pre']
    .map((s) => { const r = document.querySelector(s).getBoundingClientRect(); return [s, Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; }));
  const oldPage = await browser.newPage(); await oldPage.setViewport({ width: 1200, height: 700 });
  await oldPage.goto('http://127.0.0.1:8011/', { waitUntil: 'networkidle0' });
  const a = await boxes(oldPage), b = await boxes(page);
  await oldPage.close(); await page.bringToFront(); // a background tab stops rendering and clicks can hang
  const diffs = a.filter((x, i) => x.slice(1).some((v, j) => Math.abs(v - b[i][j + 1]) > 1));
  check('layout matches the old landing page (element boxes within 1px)', diffs.length === 0, diffs.length ? JSON.stringify({ old: diffs, new: b.filter((y) => diffs.some((x) => x[0] === y[0])) }) : '');
  await page.screenshot({ path: __dirname + '/t2_landing.png' });

  // The app's own typed client, from the 5173 origin to the API on 8011 (real cross-origin call).
  const viaClient = await page.evaluate(async () => {
    const { api } = await import('/src/api/client.ts');
    const r = await api.conversations(2);
    let notFound = null;
    try { await api.calls('does-not-exist', {}); } catch (e) { notFound = { name: e.name, status: e.status, message: e.message }; }
    return { n: r.items.length, hasMore: r.has_more, first: r.items[0].name, notFound };
  });
  check('client: /api/conversations across origins (CORS)', viaClient.n === 2 && viaClient.hasMore === true && viaClient.first === 'team/support', JSON.stringify(viaClient));
  check('client: a 404 becomes an ApiError with the API message', viaClient.notFound?.status === 404 && viaClient.notFound?.name === 'ApiError', JSON.stringify(viaClient.notFound));

  // Routes: slash name in both forms, unknown page.
  for (const url of ['/volumes/team%2Fsupport', '/volumes/team/support']) {
    await page.goto('http://localhost:5173' + url, { waitUntil: 'networkidle0' });
    check(`route ${url}: heading is the decoded name, Monitoring opens`, (await page.$eval('main h1', (e) => e.textContent)) === 'team/support'
      && (await page.title()) === 'team/support · AIControl' && (await page.$eval('#monitoring', (d) => d.open)));
  }
  await page.goto('http://localhost:5173/nope', { waitUntil: 'networkidle0' });
  check('unknown route shows "Page not found"', (await page.$eval('main h1', (e) => e.textContent)) === 'Page not found');

  // Navigation keeps the sidebar mounted (state survives): open it on "/", go to a conversation via history.
  await page.goto('http://localhost:5173/', { waitUntil: 'networkidle0' });
  await page.click('#monitoring > summary');
  await page.evaluate(() => { window.history.pushState({}, '', '/volumes/abc'); window.dispatchEvent(new PopStateEvent('popstate')); });
  await new Promise((r) => setTimeout(r, 200));
  check('sidebar stays open across client-side navigation', (await page.$eval('#monitoring', (d) => d.open)) && (await page.$eval('main h1', (e) => e.textContent)) === 'abc');

  check('no console or page errors', errors.length === 0, errors.length ? JSON.stringify(errors) : '');
  console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECK(S) FAILED`);
  await browser.close(); process.exit(failures ? 1 : 0);
})().catch((e) => { console.error('SCRIPT ERROR', e); process.exit(2); });
