// Task 3 (sidebar conversation list) in real Chrome: new React UI on 5173 vs the old UI on 8011.
const puppeteer = require('puppeteer-core');
const { execSync } = require('child_process');
const NEW = 'http://localhost:5173', OLD = 'http://127.0.0.1:8011';
const API_DIR = '/Users/g.askri/Desktop/AIControl/api';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const LIVE = 'live-' + Date.now().toString(36);
let failures = 0;
const check = (label, ok, detail = '') => { if (!ok) failures++; console.log((ok ? 'PASS ' : 'FAIL ') + label + (detail ? '  ' + detail : '')); };

(async () => {
  // fresh data: the 40 seeded conversations (the throwaway database must be running)
  execSync(`bash ${__dirname}/reset_data.sh`, { stdio: 'ignore' });
  const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const page = await browser.newPage(); page.setDefaultTimeout(10000); page.setDefaultNavigationTimeout(15000);
  await page.setViewport({ width: 1200, height: 800 });
  let phase = 'normal'; const reqs = []; const errors = [];
  page.on('request', (r) => { if (r.url().includes('/api/conversations')) reqs.push(r.url()); });
  page.on('pageerror', (e) => errors.push(`[${phase}] pageerror ${e.message}`));
  page.on('response', (r) => { if (r.status() >= 400 && phase === 'normal' && !r.url().endsWith('/favicon.ico')) errors.push(`[${phase}] HTTP ${r.status()} ${r.url()}`); });
  const take = () => { const n = reqs.length; reqs.length = 0; return n; };
  const items = () => page.$$eval('.conversations a.conversation', (as) => as.map((a) => ({ name: a.querySelector('.conv-name').textContent, meta: a.querySelector('.conv-meta').textContent.replace(/\s+/g, ' ').trim(), href: a.getAttribute('href'), current: a.hasAttribute('aria-current') })));
  const lists = () => page.$$eval('.conversations', (e) => e.length);
  const isOpen = () => page.$eval('#monitoring', (d) => d.open);
  const summary = '#monitoring > summary';

  console.log('--- collapsed, then opened');
  await page.goto(NEW + '/', { waitUntil: 'networkidle0' });
  take();
  await sleep(6500);
  check('collapsed for 6.5s (refresh is 5s): no request', take() === 0);
  await page.click(summary);
  await page.waitForSelector('.conversations a.conversation');
  let list = await items();
  check('opening loads the latest 30 with exactly one request', list.length === 30 && take() === 1, `items=${list.length}`);
  check('newest first: team/support, then the long name', list[0].name === 'team/support' && list[1].name.startsWith('customer-support'));
  check('subtitle format "1 call · Oct 4, 09:39"', list[0].meta === '1 call · Oct 4, 09:39', list[0].meta);
  check('Load more offered, one list', !!(await page.$('.conversations li.more button')) && (await lists()) === 1);
  const long = await page.$$eval('.conversations a.conversation', (as) => { const a = as[1]; const n = a.querySelector('.conv-name'); return { truncated: n.scrollWidth > n.clientWidth, title: a.title.length }; });
  check('long name: ellipsis + full name in tooltip', long.truncated && long.title > 60, JSON.stringify(long));
  check('no horizontal page scroll', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));

  console.log('--- refresh while open, nothing while collapsed');
  await sleep(6000);
  check('open for 6s: the 5s refresh happened', take() >= 1);
  await page.click(summary); await sleep(300); take();
  await sleep(6500);
  check('collapsed again for 6.5s: no request', take() === 0 && !(await isOpen()));
  await page.click(summary); await sleep(700);
  check('re-opened: refreshes at once, same single list, list kept', take() === 1 && (await lists()) === 1 && (await items()).length === 30);

  console.log('--- Load more');
  await page.click('.conversations li.more button');
  await page.waitForFunction(() => document.querySelectorAll('.conversations a.conversation').length === 40);
  const lastUrl = reqs[reqs.length - 1];
  list = await items();
  check('Load more requests limit=60 and shows all 40', /limit=60/.test(lastUrl) && list.length === 40, lastUrl);
  check('no duplicates, Load more gone, one list', new Set(list.map((x) => x.name)).size === 40 && !(await page.$('.conversations li.more')) && (await lists()) === 1);

  console.log('--- slash name, client-side navigation');
  check('link is encoded', list[0].href === '/volumes/team%2Fsupport', list[0].href);
  await page.evaluate(() => { window.__marker = 'same-document'; });
  await page.click('.conversations a.conversation');
  await page.waitForFunction(() => document.querySelector('main h1')?.textContent === 'team/support');
  const after = await items();
  check('navigated without a page reload', (await page.evaluate(() => window.__marker)) === 'same-document' && page.url().endsWith('/volumes/team%2Fsupport'));
  check('current conversation marked, loaded list kept (40)', after.filter((x) => x.current).map((x) => x.name).join() === 'team/support' && after.length === 40);

  console.log('--- a new conversation arrives while open');
  check('new conversation not there yet', !after.some((x) => x.name === LIVE));
  console.log('   ' + execSync(`cd ${API_DIR} && PYTHONPATH=. uv run python ${__dirname}/post_span.py ${LIVE} 2>&1 | grep -v UV_NATIVE`).toString().trim());
  const t0 = Date.now(); let appeared = true;
  try { await page.waitForFunction((name) => document.querySelector('.conversations a.conversation .conv-name')?.textContent === name, { timeout: 9000, polling: 200 }, LIVE); } catch { appeared = false; }
  check('the new conversation appears at the top by itself', appeared, `after ${Date.now() - t0} ms`);
  await page.screenshot({ path: __dirname + '/t3_live.png' });

  console.log('--- same list as the old UI (first 30: names and subtitles)');
  const newList = (await items()).slice(0, 30).map((x) => x.name + ' | ' + x.meta);
  await page.goto(OLD + '/volumes/' + LIVE, { waitUntil: 'networkidle0' });
  await page.waitForSelector('.conversations a.conversation');
  const oldList = (await items()).slice(0, 30).map((x) => x.name + ' | ' + x.meta);
  check('old and new lists are identical', JSON.stringify(newList) === JSON.stringify(oldList), JSON.stringify(newList) === JSON.stringify(oldList) ? '' : JSON.stringify({ newList: newList.slice(0, 3), oldList: oldList.slice(0, 3) }));

  console.log('--- empty and error states (requests intercepted)');
  await page.setRequestInterception(true);
  let mode = 'pass';
  page.on('request', (r) => {
    if (r.isInterceptResolutionHandled()) return;
    if (!r.url().includes('/api/conversations') || mode === 'pass') return r.continue();
    const cors = { 'access-control-allow-origin': '*', 'content-type': 'application/json' };
    if (mode === 'error') return r.respond({ status: 500, headers: cors, body: JSON.stringify({ detail: 'boom' }) });
    return r.respond({ status: 200, headers: cors, body: JSON.stringify({ items: [], has_more: false }) });
  });
  const text = () => page.$eval('.conversations', (e) => e.innerText.replace(/\s+/g, ' ').trim());
  phase = 'error-injection';
  mode = 'empty'; await page.goto(NEW + '/volumes/abc', { waitUntil: 'networkidle0' });
  await page.waitForFunction(() => document.querySelector('.conversations').innerText.includes('No conversations yet'));
  check('empty state text', (await text()).startsWith('No conversations yet. They appear here as soon as an app using the SDK sends calls.'), await text());
  mode = 'error'; await page.goto(NEW + '/volumes/abc', { waitUntil: 'networkidle0' });
  await page.waitForFunction(() => document.querySelector('.conversations').innerText.includes('Could not load'));
  check('first load fails: error note, no crash', (await text()) === 'Could not load conversations: boom', await text());
  mode = 'pass';
  await page.waitForFunction(() => document.querySelectorAll('.conversations a.conversation').length > 0, { timeout: 8000 });
  check('recovers by itself on the next refresh', !(await text()).includes('Could not load'));
  mode = 'error';
  await page.waitForFunction(() => document.querySelector('.conversations').innerText.includes('Refresh failed'), { timeout: 8000 });
  check('a failing refresh keeps the list and adds a note', (await items()).length > 0 && (await text()).includes('Refresh failed: boom'));
  mode = 'pass';
  await page.waitForFunction(() => !document.querySelector('.conversations').innerText.includes('Refresh failed'), { timeout: 8000 });
  check('the note disappears once the API is back', true);
  phase = 'normal'; // interception stays on; in 'pass' mode the handler just continues requests

  console.log('--- dark mode and a narrow window (screenshots)');
  await page.goto(NEW + '/volumes/team%2Fsupport', { waitUntil: 'networkidle0' });
  await page.waitForSelector('.conversations a.conversation');
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'dark' }]); await sleep(300);
  await page.screenshot({ path: __dirname + '/t3_dark.png' });
  await page.emulateMediaFeatures([]);
  await page.setViewport({ width: 600, height: 900 }); await sleep(300);
  check('narrow: sidebar stacks above the content, no horizontal scroll', await page.evaluate(() => document.querySelector('.sidebar').getBoundingClientRect().bottom <= document.querySelector('main').getBoundingClientRect().top + 1 && document.documentElement.scrollWidth <= window.innerWidth));
  await page.screenshot({ path: __dirname + '/t3_narrow.png' });

  check('no console or page errors outside the injected failures', errors.length === 0, errors.length ? JSON.stringify(errors) : '');
  console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECK(S) FAILED`);
  await browser.close(); process.exit(failures ? 1 : 0);
})().catch((e) => { console.error('SCRIPT ERROR', e.message); process.exit(2); });
