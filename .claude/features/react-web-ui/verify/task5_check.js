// Task 5 ("Show full input") in real Chrome: new React UI on 5173 vs the old server-rendered UI on 8011.
const puppeteer = require('puppeteer-core');
const { execSync } = require('child_process');
const NEW = 'http://localhost:5173', OLD = 'http://127.0.0.1:8011';
const API_DIR = '/Users/g.askri/Desktop/AIControl/api';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const sh = (cmd) => execSync(cmd, { stdio: ['ignore', 'pipe', 'pipe'] }).toString().trim();
let failures = 0;
const check = (label, ok, detail = '') => { if (!ok) failures++; console.log((ok ? 'PASS ' : 'FAIL ') + label + (detail ? '  ' + String(detail).slice(0, 320) : '')); };
const enc = encodeURIComponent;
const norm = (t) => t.replace(/\s+/g, ' ').trim();

(async () => {
  console.log('--- preparing data');
  sh(`bash ${__dirname}/reset_data.sh`);
  sh(`cd ${API_DIR} && PYTHONPATH=. uv run python ${__dirname}/seed_timeline.py 2>&1 | grep -v UV_NATIVE`);
  sh(`cd ${API_DIR} && PYTHONPATH=. uv run python ${__dirname}/post_demo_spans.py 2>&1 | grep -v UV_NATIVE`);

  const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const page = await browser.newPage(); page.setDefaultTimeout(10000); page.setDefaultNavigationTimeout(15000);
  await page.setViewport({ width: 1200, height: 900 });
  await page.evaluateOnNewDocument(() => { window.alert = () => { window.__alerted = true; }; });
  let phase = 'normal'; const errors = [];
  page.on('pageerror', (e) => errors.push(`[${phase}] pageerror ${e.message}`));
  page.on('response', (r) => { if (r.status() >= 400 && phase === 'normal' && !r.url().endsWith('/favicon.ico')) errors.push(`[${phase}] HTTP ${r.status()} ${r.url()}`); });
  const callIds = () => page.$$eval('main ol.timeline > li.call', (els) => els.map((li) => li.id.replace('call-', '')));

  // Open "Show full input" on every card of a conversation and return {id: normalised text of the panel}.
  async function panels(base, volume, isOld) {
    await page.goto(`${base}/volumes/${enc(volume)}`, { waitUntil: 'networkidle0' });
    await page.waitForSelector('main ol.timeline > li.call');
    const ids = await callIds();
    const out = {};
    for (const id of ids) {
      await page.click(`li#call-${id} button.link`);
      await page.waitForFunction((id, isOld) => {
        const box = isOld ? document.getElementById('full-' + id) : document.querySelector(`li#call-${id} .full`);
        return box && box.textContent.trim() !== '' && !/^Loading/.test(box.textContent.trim());
      }, { timeout: 8000 }, id, isOld);
      // open every collapsed section so innerText includes it, then compare what a reader would see
      out[id] = norm(await page.evaluate((id, isOld) => {
        const box = isOld ? document.getElementById('full-' + id) : document.querySelector(`li#call-${id} .full`);
        box.querySelectorAll('details').forEach((d) => { d.open = true; });
        return box.innerText;
      }, id, isOld));
    }
    return out;
  }

  console.log('--- identical to the old panel (all text, incl. collapsed details and the S3 key)');
  for (const [volume, label] of [['tools-demo', 'tool definitions + tool call/result'], ['error-demo', 'an error call (no output)'], ['hostile-trace', 'hostile text in the trace'], ['chat-37', 'a call whose trace object is missing']]) {
    const oldP = await panels(OLD, volume, true);
    const newP = await panels(NEW, volume, false);
    const ids = Object.keys(oldP);
    const same = ids.length > 0 && ids.every((id) => oldP[id] === newP[id]);
    const diff = same ? '' : JSON.stringify(ids.filter((id) => oldP[id] !== newP[id]).map((id) => ({ id, old: oldP[id].slice(0, 200), new: (newP[id] || '').slice(0, 200) }))[0]);
    check(`${label} (${volume}): ${ids.length} panel(s) identical`, same, diff);
  }

  console.log('--- what the panels contain');
  await page.goto(`${NEW}/volumes/tools-demo`, { waitUntil: 'networkidle0' });
  await page.waitForSelector('main ol.timeline > li.call');
  const [first] = await callIds();
  await page.click(`li#call-${first} button.link`);
  await page.waitForSelector(`li#call-${first} .full .full-trace`);
  const content = await page.$eval(`li#call-${first} .full`, (box) => ({
    headings: [...box.querySelectorAll('h3')].map((h) => h.textContent),
    summaries: [...box.querySelectorAll('details > summary')].map((s) => s.textContent),
    roles: [...box.querySelectorAll('.msg .role')].map((r) => r.textContent),
    key: box.querySelector('.trace-key code').textContent,
    attrs: box.querySelectorAll('details')[1].querySelector('pre').textContent,
  }));
  check('headings, collapsible sections and roles', content.headings[0] === 'Input (2 messages)' && content.headings[1] === 'Output' && content.summaries.join() === 'Tool definitions (1),All attributes' && content.roles.join() === 'system,user,assistant', JSON.stringify(content));
  check('S3 key of the trace is shown', /^volumes\/tools-demo\/\d{4}\/\d{2}\/\d{2}\/\d{6}_[0-9a-f]{32}_[0-9a-f]{16}\.json$/.test(content.key), content.key);
  check('all attributes are indented JSON', content.attrs.includes('"gen_ai.request.model": "gpt-4o-mini"') && content.attrs.startsWith('{\n  "'), content.attrs.slice(0, 80));
  check('the details sections start collapsed', await page.$$eval(`li#call-${first} .full details`, (ds) => ds.every((d) => !d.open)));

  console.log('--- open and close, and the panel survives the live refresh');
  check('button now says Hide full input', (await page.$eval(`li#call-${first} button.link`, (b) => b.textContent)) === 'Hide full input');
  await sleep(5000);
  check('the open panel stays open across refresh polls (5s)', !!(await page.$(`li#call-${first} .full .full-trace`)));
  await page.click(`li#call-${first} button.link`);
  check('clicking again hides it', !(await page.$(`li#call-${first} .full .full-trace`)) && (await page.$eval(`li#call-${first} button.link`, (b) => b.textContent)) === 'Show full input');

  console.log('--- hostile text in a stored trace stays text');
  await page.goto(`${NEW}/volumes/hostile-trace`, { waitUntil: 'networkidle0' });
  await page.waitForSelector('main ol.timeline > li.call');
  const [hid] = await callIds();
  await page.click(`li#call-${hid} button.link`);
  await page.waitForSelector(`li#call-${hid} .full .full-trace`);
  const hostile = await page.evaluate((hid) => {
    const box = document.querySelector(`li#call-${hid} .full`);
    return { contents: [...box.querySelectorAll('.content')].map((e) => e.textContent), injected: document.querySelectorAll('main script, main img, main b').length, rawAttr: box.querySelectorAll('details')[0].querySelector('pre').textContent.includes('<script>'), alerted: !!window.__alerted };
  }, hid);
  check('system and user text shown literally, nothing injected, no alert', hostile.contents.includes('<img src=x onerror=alert(2)>') && hostile.contents.some((c) => c.startsWith('<script>alert("t")</script>')) && hostile.injected === 0 && !hostile.alerted, JSON.stringify(hostile));

  console.log('--- missing trace and errors');
  await page.goto(`${NEW}/volumes/chat-37`, { waitUntil: 'networkidle0' });
  await page.waitForSelector('main ol.timeline > li.call');
  const [mid] = await callIds();
  await page.click(`li#call-${mid} button.link`);
  await page.waitForSelector(`li#call-${mid} .full p.error-text`);
  check('missing trace object: clear message with the S3 key', /^Trace object volumes\/seed\/\d+\.json not found in storage$/.test(await page.$eval(`li#call-${mid} .full p.error-text`, (e) => e.textContent)));
  phase = 'error-injection';
  await page.setRequestInterception(true);
  let mode = 'error';
  page.on('request', (r) => {
    if (r.isInterceptResolutionHandled()) return;
    if (!/\/api\/calls\/\d+/.test(r.url()) || mode === 'pass') return r.continue();
    r.respond({ status: 500, headers: { 'access-control-allow-origin': '*', 'content-type': 'application/json' }, body: JSON.stringify({ detail: 'boom' }) });
  });
  await page.goto(`${NEW}/volumes/tools-demo`, { waitUntil: 'networkidle0' });
  await page.waitForSelector('main ol.timeline > li.call');
  const [eid] = await callIds();
  await page.click(`li#call-${eid} button.link`);
  await page.waitForFunction((eid) => document.querySelector(`li#call-${eid} .full`).textContent.includes('Could not load the full input: boom'), {}, eid);
  check('API failure: message instead of a crash', true);
  mode = 'pass';
  await page.click(`li#call-${eid} button.link`); // hide
  await page.click(`li#call-${eid} button.link`); // show again = try again
  await page.waitForSelector(`li#call-${eid} .full .full-trace`);
  check('hide and show again retries and succeeds', true);
  phase = 'normal';

  console.log('--- screenshots (light, dark, narrow) with a panel open');
  await page.goto(`${NEW}/volumes/tools-demo`, { waitUntil: 'networkidle0' });
  await page.waitForSelector('main ol.timeline > li.call');
  const [sid] = await callIds();
  await page.click(`li#call-${sid} button.link`);
  await page.waitForSelector(`li#call-${sid} .full .full-trace`);
  await page.$eval(`li#call-${sid} .full details`, (d) => { d.open = true; });
  await page.screenshot({ path: __dirname + '/t5_light.png' });
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'dark' }]); await sleep(300);
  await page.screenshot({ path: __dirname + '/t5_dark.png' });
  await page.emulateMediaFeatures([]);
  await page.setViewport({ width: 600, height: 900 }); await sleep(300);
  check('narrow: no horizontal page scroll with the panel open', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await page.screenshot({ path: __dirname + '/t5_narrow.png' });

  check('no failing requests or page errors outside the injected failures', errors.length === 0, JSON.stringify(errors));
  console.log(failures === 0 ? '\nALL CHECKS PASSED' : `\n${failures} CHECK(S) FAILED`);
  await browser.close(); process.exit(failures ? 1 : 0);
})().catch((e) => { console.error('SCRIPT ERROR', e.message); process.exit(2); });
