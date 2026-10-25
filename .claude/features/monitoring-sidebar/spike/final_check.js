// Task 5 checks in real Chrome against the throwaway app: Load more (40 conversations), slash name,
// long-name truncation, live arrival of a new conversation, dark mode and a narrow window.
const puppeteer = require('puppeteer-core');
const { execSync } = require('child_process');
const BASE = process.env.BASE || 'http://127.0.0.1:8011';
const API_DIR = '/Users/g.askri/Desktop/AIControl/api';
const OUT = process.env.OUT || __dirname;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let failures = 0;
const check = (label, ok, detail = '') => { if (!ok) failures++; console.log((ok ? 'PASS ' : 'FAIL ') + label + (detail ? '  ' + detail : '')); };

(async () => {
  const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const page = await browser.newPage();
  await page.setViewport({ width: 1200, height: 800 });
  const sidebarReqs = []; const errors = []; let navigations = 0;
  page.on('request', (r) => { if (r.url().includes('/ui/conversations')) sidebarReqs.push(r.url()); });
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('response', (r) => { if (r.status() >= 400 && !r.url().endsWith('favicon.ico')) errors.push(r.status() + ' ' + r.url()); });
  page.on('framenavigated', () => navigations++);
  const names = () => page.$$eval('#conversations a.conversation .conv-name', (e) => e.map((x) => x.textContent));
  const lists = () => page.$$eval('#conversations', (e) => e.length);
  const loadMore = () => page.$('#conversations li.more button');

  console.log('--- 1. landing page');
  await page.goto(BASE + '/', { waitUntil: 'networkidle0' });
  check('landing: heading and hint', (await page.$eval('main h1', (e) => e.textContent)) === 'Monitoring' && (await page.$eval('main p', (e) => e.textContent)).includes('Click Monitoring'));
  check('landing: Monitoring collapsed, no sidebar request at load', !(await page.$eval('#monitoring', (d) => d.open)) && sidebarReqs.length === 0);

  console.log('--- 2. open Monitoring: latest 30 of 40, Load more');
  await page.click('#monitoring > summary');
  await page.waitForSelector('#conversations a.conversation');
  let list = await names();
  check('30 conversations shown', list.length === 30, `got ${list.length}`);
  check('newest first: team/support, then the long name', list[0] === 'team/support' && list[1].startsWith('customer-support'), JSON.stringify(list.slice(0, 2)));
  check('Load more is offered, exactly one list', !!(await loadMore()) && (await lists()) === 1);
  const meta = await page.$eval('#conversations a.conversation .conv-meta', (e) => e.textContent.replace(/\s+/g, ' ').trim());
  check('subtitle format (newest: 1 call, UTC time)', meta === '1 call · Oct 4, 09:39', JSON.stringify(meta));
  const long = await page.$$eval('#conversations a.conversation', (as) => as.map((a) => ({ n: a.querySelector('.conv-name'), title: a.title })).filter((x) => x.n.textContent.startsWith('customer-support')).map((x) => ({ truncated: x.n.scrollWidth > x.n.clientWidth, title: x.title, fullLen: x.title.length }))[0]);
  check('long name is truncated with ellipsis and keeps the full name in the tooltip', long.truncated && long.fullLen > 60, JSON.stringify(long));
  check('no horizontal page scroll', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await page.evaluate(() => { const s = document.querySelector('.sidebar'); s.scrollTop = s.scrollHeight; });
  await sleep(200);
  await page.screenshot({ path: OUT + '/final-load-more.png' });

  console.log('--- 3. Load more');
  await (await loadMore()).click();
  await page.waitForFunction(() => document.querySelectorAll('#conversations a.conversation').length === 40, { timeout: 5000 });
  list = await names();
  check('all 40 shown after Load more', list.length === 40);
  check('Load more is gone, still exactly one list', !(await loadMore()) && (await lists()) === 1);
  check('no duplicates in the list', new Set(list).size === 40);

  console.log('--- 4. slash name');
  const href = await page.$eval('#conversations a.conversation', (a) => a.getAttribute('href'));
  check('link is encoded', href === '/volumes/team%2Fsupport', href);
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), page.click('#conversations a.conversation')]);
  check('timeline of the slash-named conversation opens', page.url().endsWith('/volumes/team%2Fsupport') && (await page.$eval('main h1', (e) => e.textContent)) === 'team/support' && (await page.content()).includes('Hello from team/support'));
  await page.waitForSelector('#conversations a.conversation[aria-current="page"]');
  check('Monitoring stays open and the current conversation is marked', (await page.$eval('#monitoring', (d) => d.open)) && (await page.$eval('#conversations a[aria-current="page"] .conv-name', (e) => e.textContent)) === 'team/support');

  console.log('--- 5. a new conversation arrives while the page is open');
  check('bob-chat-7 is not there yet', !(await names()).includes('bob-chat-7'));
  const navsBefore = navigations;
  console.log('   ' + execSync(`cd ${API_DIR} && PYTHONPATH=. uv run python ${__dirname}/post_span.py 2>&1 | grep -v UV_NATIVE`).toString().trim());
  const t0 = Date.now();
  let appeared = true;
  try { await page.waitForFunction(() => [...document.querySelectorAll('#conversations .conv-name')].some((e) => e.textContent === 'bob-chat-7'), { timeout: 9000, polling: 200 }); } catch { appeared = false; }
  const waited = Date.now() - t0;
  check('bob-chat-7 appears by itself within the 5s refresh', appeared && waited <= 6500, `after ${waited} ms`);
  list = await names();
  check('it is at the top (newest activity), one list, no page reload', list[0] === 'bob-chat-7' && (await lists()) === 1 && navigations === navsBefore, JSON.stringify(list.slice(0, 2)));
  await page.screenshot({ path: OUT + '/final-live-arrival.png' });
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), page.click('#conversations a.conversation')]);
  check('opening it shows its messages', page.url().endsWith('/volumes/bob-chat-7') && (await page.content()).includes('weather in Paris'));

  console.log('--- 6. dark mode and a narrow window');
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'dark' }]);
  await sleep(300);
  await page.screenshot({ path: OUT + '/final-dark.png' });
  await page.emulateMediaFeatures([]);
  await page.setViewport({ width: 600, height: 900 });
  await sleep(300);
  check('narrow: sidebar stacks above the content (not side by side)', await page.evaluate(() => document.querySelector('.sidebar').getBoundingClientRect().bottom <= document.querySelector('main').getBoundingClientRect().top + 1));
  check('narrow: no horizontal page scroll', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await page.screenshot({ path: OUT + '/final-narrow.png' });

  check('no page or network errors (favicon excluded)', errors.length === 0, errors.length ? JSON.stringify(errors) : '');
  console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECK(S) FAILED`);
  await browser.close();
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error('SCRIPT ERROR', e); process.exit(2); });
