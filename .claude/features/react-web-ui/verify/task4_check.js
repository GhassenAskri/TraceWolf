// Task 4 (timeline) in real Chrome: new React UI on 5173 vs the old server-rendered UI on 8011.
// Prepares its own data (throwaway database + API on 8011 must be running).
const puppeteer = require('puppeteer-core');
const { execSync } = require('child_process');
const NEW = 'http://localhost:5173', OLD = 'http://127.0.0.1:8011';
const API_DIR = '/Users/g.askri/Desktop/AIControl/api';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const sh = (cmd) => execSync(cmd, { stdio: ['ignore', 'pipe', 'pipe'] }).toString().trim();
let failures = 0;
const check = (label, ok, detail = '') => { if (!ok) failures++; console.log((ok ? 'PASS ' : 'FAIL ') + label + (detail ? '  ' + String(detail).slice(0, 300) : '')); };
const enc = encodeURIComponent;
const HOSTILE = '<img src=x onerror=alert(1)>';

(async () => {
  console.log('--- preparing data');
  sh(`bash ${__dirname}/reset_data.sh`);
  sh(`cd ${API_DIR} && PYTHONPATH=. uv run python ${__dirname}/seed_timeline.py 2>&1 | grep -v UV_NATIVE`);
  sh(`cd ${API_DIR} && PYTHONPATH=. uv run python ${__dirname}/post_demo_spans.py 2>&1 | grep -v UV_NATIVE`);

  const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const page = await browser.newPage(); page.setDefaultTimeout(10000); page.setDefaultNavigationTimeout(15000);
  await page.setViewport({ width: 1200, height: 800 });
  await page.evaluateOnNewDocument(() => { window.alert = () => { window.__alerted = true; }; });
  let phase = 'normal'; const errors = []; const callReqs = [];
  page.on('pageerror', (e) => errors.push(`[${phase}] pageerror ${e.message}`));
  page.on('response', (r) => { if (r.status() >= 400 && phase === 'normal' && !r.url().endsWith('/favicon.ico')) errors.push(`[${phase}] HTTP ${r.status()} ${r.url()}`); });
  page.on('request', (r) => { if (/\/api\/volumes\/.*\/calls/.test(r.url())) callReqs.push(r.url()); });
  const cards = () => page.$$eval('main ol.timeline > li.call', (els) => els.map((li) => ({
    cls: li.className.trim(), id: li.id,
    text: li.innerText.replace(/\s+/g, ' ').replace(/ ?Show full input ?/, ' ').trim(),
    roles: [...li.querySelectorAll('.msg')].map((m) => m.className).join('|'),
  })));
  const count = () => page.$$eval('main ol.timeline > li.call', (e) => e.length);
  const waitCards = (n, t = 10000) => page.waitForFunction((n) => document.querySelectorAll('main ol.timeline > li.call').length === n, { timeout: t }, n);
  const loadMoreBtn = () => page.$('main ol.timeline li.more button');

  console.log('--- same cards as the old UI (text, classes, message roles)');
  for (const [volume, label] of [['tools-demo', 'tool calls'], ['error-demo', 'an error call'], ['timeline-long', '50 calls'], [HOSTILE, 'hostile text']]) {
    await page.goto(`${OLD}/volumes/${enc(volume)}`, { waitUntil: 'networkidle0' });
    const old = await cards();
    await page.goto(`${NEW}/volumes/${enc(volume)}`, { waitUntil: 'networkidle0' });
    await waitCards(old.length);
    const now = await cards();
    const same = old.length === now.length && old.every((o, i) => o.text === now[i].text && o.cls === now[i].cls && o.roles === now[i].roles && o.id === now[i].id);
    const firstDiff = same ? '' : JSON.stringify(old.map((o, i) => [o, now[i]]).find(([o, n]) => !n || o.text !== n.text || o.cls !== n.cls || o.roles !== n.roles));
    check(`${label} (${volume.slice(0, 20)}): ${old.length} cards identical`, same && old.length > 0, firstDiff);
  }

  console.log('--- what the tool and error cards show');
  await page.goto(`${NEW}/volumes/tools-demo`, { waitUntil: 'networkidle0' });
  await waitCards(2);
  const tools = await cards();
  check('tool call card: badge, call text, tags', tools[0].text.includes('tool call get_weather({"city": "Paris"})') && tools[0].text.includes('10 cached') && tools[0].text.includes('3 reasoning') && tools[0].text.includes('tool_call') && tools[0].text.includes('1 tool'), tools[0].text);
  check('tool result card: tool role with call id', tools[1].text.toLowerCase().includes('tool · call_1') && tools[1].text.includes('{"temp": 22}') && tools[1].roles.includes('role-tool'), tools[1].text);
  await page.goto(`${NEW}/volumes/error-demo`, { waitUntil: 'networkidle0' });
  await waitCards(2);
  const errs = await cards();
  check('error card highlighted with the error type', errs.some((c) => c.cls === 'call error' && c.text.includes('error: RateLimitError')) && errs.some((c) => c.cls === 'call'), JSON.stringify(errs.map((c) => c.cls)));

  console.log('--- hostile text stays text');
  await page.goto(`${NEW}/volumes/${enc(HOSTILE)}`, { waitUntil: 'networkidle0' });
  await waitCards(1);
  const hostile = await page.evaluate(() => ({
    h1: document.querySelector('main h1').textContent, content: [...document.querySelectorAll('main .content')].map((e) => e.textContent),
    injected: document.querySelectorAll('main script, main img, main b, .sidebar img').length, alerted: !!window.__alerted,
  }));
  check('name and messages are shown literally, nothing injected, no alert', hostile.h1 === HOSTILE && hostile.content.includes('<script>alert("x")</script>') && hostile.content.some((c) => c.startsWith('<b>bold</b>')) && hostile.injected === 0 && !hostile.alerted, JSON.stringify(hostile));

  console.log('--- Load more: 50 -> 100 -> 120');
  await page.goto(`${NEW}/volumes/timeline-long`, { waitUntil: 'networkidle0' });
  await waitCards(50);
  const first = await cards();
  check('first page: 50 oldest calls, in order', first[0].text.includes('2026-09-24 10:00:00') && first[0].text.includes('question 0') && first[49].text.includes('question 49'));
  check('Load more offered (no refresh while more exist)', !!(await loadMoreBtn()));
  callReqs.length = 0; await sleep(4500);
  check('no refresh requests while "Load more" is pending', callReqs.length === 0, callReqs.length);
  await (await loadMoreBtn()).click(); await waitCards(100);
  check('Load more adds the next 50', (await count()) === 100 && !!(await loadMoreBtn()));
  await (await loadMoreBtn()).click(); await waitCards(120);
  const all = await cards();
  check('all 120, in order, unique, button gone', all.length === 120 && new Set(all.map((c) => c.id)).size === 120 && all[119].text.includes('question 119') && !(await loadMoreBtn()));

  console.log('--- a live call arrives (everything loaded: refresh every 2s)');
  callReqs.length = 0; await sleep(4500);
  check('refresh requests flow once everything is loaded (every ~2s)', callReqs.length >= 2 && callReqs.every((u) => /cursor=/.test(u)), callReqs.length + ' requests');
  sh(`cd ${API_DIR} && PYTHONPATH=. uv run python ${__dirname}/post_span.py timeline-long 2>&1 | grep -v UV_NATIVE`);
  const t0 = Date.now(); let arrived = true;
  try { await waitCards(121, 9000); } catch { arrived = false; }
  const live = await cards();
  check('the new call is appended by itself', arrived && live[120]?.text.includes("What's the weather in Paris?"), `after ${Date.now() - t0} ms`);
  check('sidebar shows the new activity too (121 calls, newest first)', await page.waitForFunction(() => document.querySelector('.conversations a.conversation .conv-name')?.textContent === 'timeline-long' && /121 calls/.test(document.querySelector('.conversations a.conversation .conv-meta').textContent), { timeout: 8000 }).then(() => true, () => false));

  console.log('--- time filter');
  await page.goto(`${NEW}/volumes/timeline-long`, { waitUntil: 'networkidle0' });
  await page.$eval('input[name=from]', (e) => { e.value = '2026-09-24T10:01:00'; });
  await page.$eval('input[name=to]', (e) => { e.value = '2026-09-24T10:03:00'; });
  await page.click('form.filters button[type=submit]');
  await waitCards(2);
  const filtered = await cards();
  check('From inclusive, To exclusive: only 10:01 and 10:02', filtered[0].text.includes('question 1') && filtered[1].text.includes('question 2'));
  check('filter is in the URL, inputs keep their values, Clear is offered', decodeURIComponent(page.url()).includes('from=2026-09-24T10:01') && (await page.$eval('input[name=from]', (e) => e.value)) === '2026-09-24T10:01' && !!(await page.$('form.filters a')));
  await page.goto(`${NEW}/volumes/timeline-long?from=2030-01-01T00:00`, { waitUntil: 'networkidle0' });
  await page.waitForFunction(() => document.querySelector('main p.empty')?.textContent.includes('No calls in this time range'));
  check('empty range message', (await page.$eval('main p.empty', (e) => e.textContent)) === 'No calls in this time range. New calls appear automatically.');
  await page.goto(`${NEW}/volumes/timeline-long?from=2026-09-24T10:01:00&to=2026-09-24T10:03:00`, { waitUntil: 'networkidle0' });
  await waitCards(2);
  await page.click('form.filters a');
  await page.waitForFunction(() => document.querySelectorAll('main ol.timeline > li.call').length === 50);
  check('Clear removes the filter and shows the first 50 again', !page.url().includes('from=') && (await count()) === 50);

  console.log('--- unknown conversation, navigation between conversations');
  phase = 'expected-404';
  await page.goto(`${NEW}/volumes/does-not-exist`, { waitUntil: 'networkidle0' });
  await page.waitForFunction(() => document.querySelector('main p.empty')?.textContent.includes('not found'));
  check('unknown conversation: friendly not-found message', (await page.$eval('main p.empty', (e) => e.textContent)).startsWith('Conversation “does-not-exist” not found.'));
  phase = 'normal';
  await page.goto(`${NEW}/volumes/timeline-long`, { waitUntil: 'networkidle0' });
  await waitCards(50);
  await page.evaluate(() => { window.__marker = 'same-document'; });
  await page.click(`.conversations a[href="/volumes/${enc('tools-demo')}"]`);
  await waitCards(2);
  const moved = await cards();
  check('clicking another conversation swaps the timeline without a reload', (await page.evaluate(() => window.__marker)) === 'same-document' && (await page.$eval('main h1', (e) => e.textContent)) === 'tools-demo' && moved.every((c) => !c.text.includes('question')) && (await page.title()) === 'tools-demo · AIControl');

  console.log('--- error states (requests intercepted)');
  phase = 'error-injection';
  await page.setRequestInterception(true);
  let mode = 'pass';
  page.on('request', (r) => {
    if (r.isInterceptResolutionHandled()) return;
    if (!/\/api\/volumes\/.*\/calls/.test(r.url()) || mode === 'pass') return r.continue();
    r.respond({ status: 500, headers: { 'access-control-allow-origin': '*', 'content-type': 'application/json' }, body: JSON.stringify({ detail: 'boom' }) });
  });
  mode = 'error'; await page.goto(`${NEW}/volumes/tools-demo`, { waitUntil: 'networkidle0' });
  await page.waitForFunction(() => document.querySelector('main p.error-text')?.textContent.includes('Could not load the calls: boom'));
  check('first load fails: message and a Retry button', !!(await page.$('main p.error-text button')));
  mode = 'pass'; await page.click('main p.error-text button'); await waitCards(2);
  check('Retry loads the calls', (await count()) === 2 && !(await page.$('main p.error-text')));
  mode = 'error';
  await page.waitForFunction(() => document.querySelector('main p.error-text')?.textContent.includes('Refresh failed: boom'), { timeout: 8000 });
  check('a failing refresh keeps the calls and adds a note', (await count()) === 2);
  mode = 'pass';
  await page.waitForFunction(() => !document.querySelector('main p.error-text'), { timeout: 8000 });
  check('the note disappears once the API is back', true);
  phase = 'normal';

  console.log('--- dark mode and a narrow window (screenshots)');
  await page.goto(`${NEW}/volumes/tools-demo`, { waitUntil: 'networkidle0' }); await waitCards(2);
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'dark' }]); await sleep(300);
  await page.screenshot({ path: __dirname + '/t4_dark.png' });
  await page.emulateMediaFeatures([]);
  await page.setViewport({ width: 600, height: 900 }); await sleep(300);
  check('narrow: no horizontal page scroll', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await page.screenshot({ path: __dirname + '/t4_narrow.png' });
  await page.setViewport({ width: 1200, height: 800 });
  await page.goto(`${NEW}/volumes/tools-demo`, { waitUntil: 'networkidle0' }); await waitCards(2);
  await page.screenshot({ path: __dirname + '/t4_light.png' });

  check('no failing requests or page errors outside the injected failures', errors.length === 0, JSON.stringify(errors));
  console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECK(S) FAILED`);
  await browser.close(); process.exit(failures ? 1 : 0);
})().catch((e) => { console.error('SCRIPT ERROR', e.message); process.exit(2); });
