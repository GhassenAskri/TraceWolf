// Task 6: pixel-by-pixel parity of the old server-rendered UI (8011) and the React UI, on the same data.
// NEW=http://localhost:5173 (dev server, default) or http://localhost:4173 (production build, `npm run preview`).
const puppeteer = require('puppeteer-core');
const { PNG } = require('pngjs');
const fs = require('fs');
const { execSync } = require('child_process');
const OLD = 'http://127.0.0.1:8011', NEW = process.env.NEW || 'http://localhost:5173';
const API_DIR = '/Users/g.askri/Desktop/AIControl/api';
const OUT = process.env.OUT || (__dirname + '/parity'); fs.mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const sh = (cmd) => execSync(cmd, { stdio: ['ignore', 'pipe', 'pipe'] }).toString().trim();
const enc = encodeURIComponent;
const HOSTILE = '<img src=x onerror=alert(1)>', LONG = 'customer-support-escalation-thread-for-the-enterprise-onboarding-project-2026';
const WIDE = { width: 1200, height: 800 }, NARROW = { width: 600, height: 900 };

// open the first "Show full input" panel (and its collapsed sections) the way each UI does it
async function openPanel(page, isOld) {
  const id = await page.$eval('main ol.timeline > li.call', (li) => li.id.replace('call-', ''));
  await page.click(`li#call-${id} button.link`);
  await page.waitForFunction((id, isOld) => { const b = isOld ? document.getElementById('full-' + id) : document.querySelector(`li#call-${id} .full`); return b && b.textContent.trim() !== '' && !/^Loading/.test(b.textContent.trim()); }, { timeout: 8000 }, id, isOld);
  await page.evaluate((id, isOld) => (isOld ? document.getElementById('full-' + id) : document.querySelector(`li#call-${id} .full`)).querySelectorAll('details').forEach((d) => { d.open = true; }), id, isOld);
  // The React button reads "Hide full input" while open (an intended change); put the old label back
  // so the comparison measures everything else.
  if (!isOld) await page.$eval(`li#call-${id} button.link`, (b) => { b.textContent = 'Show full input'; });
}
const scrollSidebarToBottom = (page) => page.evaluate(() => { const s = document.querySelector('.sidebar'); s.scrollTop = s.scrollHeight; });

const SCENARIOS = [
  { name: 'landing (closed)', path: '/', view: WIDE, wait: 'main h1' },
  { name: 'tool calls', path: '/volumes/tools-demo', view: WIDE },
  { name: 'tool calls + full input open', path: '/volumes/tools-demo', view: WIDE, act: openPanel },
  { name: 'error call', path: '/volumes/error-demo', view: WIDE },
  { name: '50 calls (first screen)', path: '/volumes/timeline-long', view: WIDE },
  { name: 'hostile name and text', path: `/volumes/${enc(HOSTILE)}`, view: WIDE },
  { name: 'hostile text in the full input', path: '/volumes/hostile-trace', view: WIDE, act: openPanel },
  { name: 'edge cases (nulls, ? tokens, stream tag, 0 ms, 2 finish reasons, 1/3 tools, nested tool args)', path: '/volumes/edge-cases', view: WIDE },
  { name: 'long conversation name', path: `/volumes/${enc(LONG)}`, view: WIDE },
  { name: 'slash name team/support', path: `/volumes/${enc('team/support')}`, view: WIDE },
  { name: 'missing trace object in the full input', path: `/volumes/${enc('chat-37')}`, view: WIDE, act: openPanel },
  { name: 'sidebar scrolled to Load more', path: '/volumes/tools-demo', view: WIDE, act: scrollSidebarToBottom },
  { name: 'time filter (2 calls)', path: '/volumes/timeline-long?from=2026-09-24T10:01&to=2026-09-24T10:03', view: WIDE },
  { name: 'empty time range', path: '/volumes/timeline-long?from=2030-01-01T00:00', view: WIDE, wait: 'main p.empty' },
  { name: 'DARK landing', path: '/', view: WIDE, dark: true, wait: 'main h1' },
  { name: 'DARK tool calls + full input', path: '/volumes/tools-demo', view: WIDE, dark: true, act: openPanel },
  { name: 'NARROW tool calls', path: '/volumes/tools-demo', view: NARROW },
  { name: 'NARROW full input (old UI overflows here)', path: '/volumes/tools-demo', view: NARROW, act: openPanel, expectDiff: true },
];

(async () => {
  const { default: pixelmatch } = await import('pixelmatch');
  console.log('--- preparing data');
  sh(`bash ${__dirname}/reset_data.sh`);
  sh(`cd ${API_DIR} && PYTHONPATH=. uv run python ${__dirname}/seed_timeline.py 2>&1 | grep -v UV_NATIVE`);
  sh(`cd ${API_DIR} && PYTHONPATH=. uv run python ${__dirname}/post_demo_spans.py 2>&1 | grep -v UV_NATIVE`);

  const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const page = await browser.newPage(); page.setDefaultTimeout(12000); page.setDefaultNavigationTimeout(15000);
  const consoleErrors = [];
  page.on('pageerror', (e) => consoleErrors.push('pageerror ' + e.message));
  page.on('response', (r) => { if (r.status() >= 400 && !r.url().endsWith('/favicon.ico') && r.url().startsWith(NEW)) consoleErrors.push(`HTTP ${r.status()} ${r.url()}`); });

  async function shoot(base, s, isOld) {
    await page.setViewport(s.view);
    await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: s.dark ? 'dark' : 'light' }]);
    await page.goto(base + s.path, { waitUntil: 'networkidle0' });
    await page.waitForSelector(s.wait || 'main ol.timeline > li.call');
    if (s.path !== '/') await page.waitForSelector('.conversations a.conversation'); // the sidebar list is open on conversation pages
    if (s.act) await s.act(page, isOld);
    await page.mouse.move(1199, 799); // park the pointer away from everything
    await sleep(400);
    return PNG.sync.read(Buffer.from(await page.screenshot({ type: 'png' })));
  }

  console.log(`--- ${OLD} (old, server-rendered)  vs  ${NEW} (React)\n`);
  let exact = 0, mismatched = 0;
  for (const [i, s] of SCENARIOS.entries()) {
    const a = await shoot(OLD, s, true), b = await shoot(NEW, s, false);
    let diffPixels = -1, note = '';
    if (a.width !== b.width || a.height !== b.height) { note = `size differs ${a.width}x${a.height} vs ${b.width}x${b.height}`; }
    else {
      const diff = new PNG({ width: a.width, height: a.height });
      diffPixels = pixelmatch(a.data, b.data, diff.data, a.width, a.height, { threshold: 0.05 });
      if (diffPixels > 0) fs.writeFileSync(`${OUT}/diff-${String(i + 1).padStart(2, '0')}.png`, PNG.sync.write(diff));
    }
    const ok = diffPixels === 0;
    if (ok) exact++; else if (!s.expectDiff) mismatched++;
    const tag = ok ? 'IDENTICAL' : s.expectDiff ? 'DIFFERS (expected)' : 'DIFFERS';
    console.log(`${tag.padEnd(19)} ${s.name}${diffPixels > 0 ? `  [${diffPixels} px = ${(100 * diffPixels / (a.width * a.height)).toFixed(3)}%]` : ''}${note ? '  ' + note : ''}`);
    if (diffPixels !== 0 || s.expectDiff) { fs.writeFileSync(`${OUT}/old-${String(i + 1).padStart(2, '0')}.png`, PNG.sync.write(a)); fs.writeFileSync(`${OUT}/new-${String(i + 1).padStart(2, '0')}.png`, PNG.sync.write(b)); }
  }
  console.log(`\n${exact} of ${SCENARIOS.length} screens are pixel-identical; unexpected differences: ${mismatched}`);
  console.log('console/network errors on the React UI:', consoleErrors.length ? JSON.stringify(consoleErrors) : 'none');
  await browser.close(); process.exit(mismatched || consoleErrors.length ? 1 : 0);
})().catch((e) => { console.error('SCRIPT ERROR', e.message); process.exit(2); });
