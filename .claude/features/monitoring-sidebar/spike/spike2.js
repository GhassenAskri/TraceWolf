const { JSDOM } = require('jsdom');
const fs = require('fs');
const htmxSrc = fs.readFileSync(__dirname + '/htmx.js', 'utf8');
const fragment = fs.readFileSync(__dirname + '/fragment.html', 'utf8').replace('every 5s', 'every 1s');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const dom = new JSDOM(`<!doctype html><body><details id="monitoring" open><summary>Monitoring</summary>${fragment}</details></body>`, {
  runScripts: 'outside-only', pretendToBeVisual: true, url: 'http://localhost/',
});
const w = dom.window;
const proto = w.XPathExpression.prototype; const ev = proto.evaluate;
proto.evaluate = function (c, t, r) { return ev.call(this, c, t || 5, r); };

// A fake server: every request is answered with the same fragment (a "refresh"), like the real route.
let served = 0;
w.XMLHttpRequest = class {
  constructor() { this.status = 0; this.readyState = 0; this.responseText = ''; this.response = ''; this.upload = { addEventListener() {} }; }
  open(m, u) { this.url = u; this.responseURL = new URL(u, 'http://localhost/').href; }
  setRequestHeader() {} getAllResponseHeaders() { return ''; } getResponseHeader() { return null; }
  overrideMimeType() {} addEventListener() {} abort() {}
  send() { setTimeout(() => { served++; this.status = 200; this.readyState = 4; this.responseText = this.response = fragment; this.onload && this.onload(); }, 5); }
};
w.CSS = { escape: (x) => String(x).replace(/[^a-zA-Z0-9_-]/g, (c) => '\\' + c) }; // missing in jsdom
w.eval(htmxSrc);

const log = [];
w.document.body.addEventListener('htmx:beforeRequest', () => log.push(Date.now()));
w.document.body.addEventListener('htmx:afterSwap', () => {});
const errors = [];
for (const t of ['htmx:syntax:error', 'htmx:eventFilter:error', 'htmx:swapError', 'htmx:responseError', 'htmx:onLoadError'])
  w.document.body.addEventListener(t, (e) => errors.push(t + ' ' + (e.detail && (e.detail.error || e.detail.source || ''))));
w.htmx.process(w.document.body);

const take = () => { const n = log.length; log.length = 0; return n; };
(async () => {
  const details = w.document.getElementById('monitoring');
  const first = w.document.getElementById('conversations');
  await sleep(6500); // ~6 refresh cycles, each one replaces the <ul>
  console.log('open, 6.5s (1s poll):          requests =', take(), '(want ~6, not growing)');
  console.log('list element was replaced:     ', w.document.getElementById('conversations') !== first, '| responses served =', served);
  console.log('exactly one #conversations:    ', w.document.querySelectorAll('#conversations').length);
  details.open = false; await sleep(200); take();
  await sleep(2500);
  console.log('closed, 2.5s:                  requests =', take(), '(want 0)');
  details.open = true; await sleep(300);
  console.log('re-opened (after many swaps):  requests =', take(), '(want exactly 1 — more would mean ghost listeners)');
  console.log('errors:', errors.length ? errors : 'none');
  process.exit(0);
})();
