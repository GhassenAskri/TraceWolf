// Real pages + real fragment (rendered by the app), real htmx 2.0.11, in jsdom. Polling shortened to 1s.
const { JSDOM } = require('jsdom');
const fs = require('fs');
const htmxSrc = fs.readFileSync(__dirname + '/htmx.js', 'utf8');
const read = (f) => fs.readFileSync(__dirname + '/' + f, 'utf8').replaceAll('every 5s', 'every 1s');
const fragment = read('fragment.html');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function open(file) {
  const dom = new JSDOM(read(file), { runScripts: 'outside-only', pretendToBeVisual: true, url: 'http://localhost/' });
  const w = dom.window;
  const proto = w.XPathExpression.prototype, ev = proto.evaluate;
  proto.evaluate = function (c, t, r) { return ev.call(this, c, t || 5, r); };
  w.CSS = { escape: (x) => String(x).replace(/[^a-zA-Z0-9_-]/g, (c) => '\\' + c) };
  w.XMLHttpRequest = class {
    constructor() { this.status = 0; this.readyState = 0; this.responseText = ''; this.response = ''; this.upload = { addEventListener() {} }; }
    open(m, u) { this.responseURL = new URL(u, 'http://localhost/').href; this.path = u; }
    setRequestHeader() {} getAllResponseHeaders() { return ''; } getResponseHeader() { return null; }
    overrideMimeType() {} addEventListener() {} abort() {}
    send() { setTimeout(() => { this.status = 200; this.readyState = 4; this.responseText = this.response = this.path.startsWith('/ui/conversations') ? fragment : ''; this.onload && this.onload(); }, 5); }
  };
  const state = { paths: [], errors: [] };
  w.document.body.addEventListener('htmx:beforeRequest', (e) => { if (e.detail.requestConfig.path.startsWith('/ui/conversations')) state.paths.push(e.detail.requestConfig.path); });
  for (const t of ['htmx:syntax:error', 'htmx:eventFilter:error', 'htmx:swapError', 'htmx:responseError', 'htmx:onLoadError'])
    w.document.body.addEventListener(t, (e) => state.errors.push(t));
  w.eval(htmxSrc);
  w.htmx.process(w.document.body);
  const d = w.document;
  return {
    w, state, details: d.getElementById('monitoring'),
    take: () => { const n = state.paths.length; state.paths.length = 0; return n; },
    items: () => [...d.querySelectorAll('#conversations a.conversation')].map((a) => a.querySelector('.conv-name').textContent + (a.hasAttribute('aria-current') ? ' [current]' : '')),
    lists: () => d.querySelectorAll('#conversations').length,
    note: () => (d.querySelector('#conversations .note') || {}).textContent,
  };
}

(async () => {
  console.log('--- /volumes/alice-chat-42 (server renders <details open>) ---');
  const a = open('conv.html');
  console.log('details open at load:       ', a.details.open);
  console.log('before any wait:             list shows', JSON.stringify(a.note()));
  await sleep(300);
  console.log('300ms after load:            requests =', a.take(), '(want 1: the `load` trigger)');
  console.log('list now:                   ', a.items(), '| #conversations count =', a.lists());
  await sleep(2600);
  console.log('open, 2.6s:                  requests =', a.take(), '(want >= 2), #conversations count =', a.lists());
  a.details.open = false; await sleep(200); a.take();
  await sleep(2500);
  console.log('closed, 2.5s:                requests =', a.take(), '(want 0)');
  a.details.open = true; await sleep(300);
  console.log('re-opened:                   requests =', a.take(), '(want exactly 1)');
  console.log('errors:', a.state.errors.length ? a.state.errors : 'none');
  a.w.close();

  console.log('--- / (home: <details> closed) ---');
  const h = open('home.html');
  console.log('details open at load:       ', h.details.open);
  await sleep(2600);
  console.log('closed, 2.6s:                requests =', h.take(), '(want 0); list still shows', JSON.stringify(h.note()));
  h.details.open = true; await sleep(300);
  console.log('opened by the user:          requests =', h.take(), '(want 1)');
  console.log('list now:                   ', h.items());
  console.log('errors:', h.state.errors.length ? h.state.errors : 'none');
  process.exit(0);
})();
