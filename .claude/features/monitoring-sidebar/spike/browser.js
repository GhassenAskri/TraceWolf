// Real Chrome (headless) against a running AIControl UI: click-through + request counting + dark mode.
const puppeteer = require('puppeteer-core');
const BASE = process.env.BASE || 'http://localhost:8011';
const OUT = __dirname;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true, args: ['--no-first-run'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1200, height: 700 });
  const sidebarRequests = [];
  page.on('request', (r) => { if (r.url().includes('/ui/conversations')) sidebarRequests.push(Date.now()); });
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  const take = () => { const n = sidebarRequests.length; sidebarRequests.length = 0; return n; };
  const state = () => page.evaluate(() => ({
    open: document.getElementById('monitoring').open,
    lists: document.querySelectorAll('#conversations').length,
    items: [...document.querySelectorAll('#conversations a.conversation')].map((a) => a.querySelector('.conv-name').textContent + (a.hasAttribute('aria-current') ? ' [current]' : '')),
  }));

  console.log('--- home page (Monitoring collapsed) ---');
  await page.goto(BASE + '/', { waitUntil: 'networkidle0' });
  console.log('at load:                      ', JSON.stringify(await state()), 'sidebar requests =', take());
  await sleep(6500);
  console.log('collapsed for 6.5s (poll=5s): requests =', take(), '(want 0)');
  await page.click('#monitoring > summary');
  await sleep(600);
  console.log('after clicking Monitoring:    ', JSON.stringify(await state()), 'requests =', take(), '(want 1)');
  await sleep(6000);
  console.log('open for 6s:                  requests =', take(), '(want >= 1, the 5s refresh)');
  await page.click('#monitoring > summary');
  await sleep(300); take();
  await sleep(6500);
  console.log('collapsed again for 6.5s:     requests =', take(), '(want 0)');
  await page.click('#monitoring > summary');
  await sleep(600);
  console.log('re-opened:                    requests =', take(), '(want 1), lists =', (await state()).lists);

  console.log('--- click a conversation ---');
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0' }), page.click('#conversations a[href="/volumes/demo-conversation"]')]);
  console.log('url:', page.url().replace(BASE, ''));
  console.log('after navigation:             ', JSON.stringify(await state()), 'requests so far =', take(), '(1 or 2: load [+ initial toggle])');
  await page.screenshot({ path: OUT + '/real_conv_light.png' });

  console.log('--- dark mode ---');
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'dark' }]);
  await sleep(300);
  await page.screenshot({ path: OUT + '/real_conv_dark.png' });
  await page.goto(BASE + '/', { waitUntil: 'networkidle0' });
  await page.click('#monitoring > summary'); await sleep(600);
  await page.screenshot({ path: OUT + '/real_home_dark.png' });
  console.log('page/console errors:', errors.length ? errors : 'none');
  await browser.close();
})().catch((e) => { console.error('FAILED', e); process.exit(1); });
