const { JSDOM } = require('jsdom');
const fs = require('fs');
const htmxSrc = fs.readFileSync(__dirname + '/htmx.js', 'utf8');
const fragment = fs.readFileSync(__dirname + '/fragment.html', 'utf8').replace('every 5s', 'every 1s');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function page(body) {
  const dom = new JSDOM(`<!doctype html><body>${body}</body>`, {
    runScripts: 'outside-only', pretendToBeVisual: true, url: 'http://localhost/',
  });
  const w = dom.window;
  // jsdom's XPath rejects a missing result type (browsers default it); htmx's hx-on scan omits it.
  const proto = w.XPathExpression.prototype;
  const evaluate = proto.evaluate;
  proto.evaluate = function (ctx, type, res) { return evaluate.call(this, ctx, type || 5, res); };
  w.eval(htmxSrc);
  const state = { requests: [], errors: [] };
  w.document.body.addEventListener('htmx:beforeRequest', (e) => {
    state.requests.push(e.detail.requestConfig.path);
    e.preventDefault(); // count it, don't send it
  });
  for (const type of ['htmx:syntax:error', 'htmx:eventFilter:error']) {
    w.document.body.addEventListener(type, (e) => state.errors.push(type + ' ' + JSON.stringify(e.detail.source || e.detail.token || '')));
  }
  w.htmx.process(w.document.body);
  return { w, state, dom };
}
const take = (state) => { const n = state.requests.length; state.requests.length = 0; return n; };

(async () => {
  console.log('--- inside <details> (the sidebar) ---');
  const a = page(`<details id="monitoring"><summary>Monitoring</summary>${fragment}</details>`);
  const details = a.w.document.getElementById('monitoring');
  await sleep(2600);
  console.log('closed, 2.6s:                 requests =', take(a.state), '(want 0)');
  details.open = true;
  await sleep(150);
  console.log('just opened (toggle event):   requests =', take(a.state), '(want 1)');
  await sleep(2600);
  console.log('open, 2.6s of polling:        requests =', take(a.state), '(want >= 2)');
  details.open = false;
  await sleep(150);
  take(a.state);
  await sleep(2600);
  console.log('closed again, 2.6s:           requests =', take(a.state), '(want 0)');
  console.log('htmx errors:', a.state.errors.length ? a.state.errors : 'none');
  a.dom.window.close();

  console.log('--- list not inside any <details> ---');
  const b = page(fragment);
  await sleep(2600);
  console.log('standalone, 2.6s:             requests =', take(b.state), '(want >= 2)');
  console.log('htmx errors:', b.state.errors.length ? b.state.errors : 'none');
  b.dom.window.close();
  process.exit(0);
})();
