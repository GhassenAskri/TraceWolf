const puppeteer = require('puppeteer-core');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const page = await browser.newPage(); page.setDefaultTimeout(10000);
  await page.setViewport({ width: 600, height: 900 });
  for (const [label, base, isOld] of [['OLD', 'http://127.0.0.1:8011', true], ['NEW', 'http://localhost:5173', false]]) {
    await page.goto(base + '/volumes/tools-demo', { waitUntil: 'networkidle0' });
    await page.waitForSelector('main ol.timeline > li.call');
    const id = await page.$eval('main ol.timeline > li.call', (li) => li.id.replace('call-', ''));
    await page.click(`li#call-${id} button.link`);
    await page.waitForFunction((id, isOld) => { const b = isOld ? document.getElementById('full-' + id) : document.querySelector(`li#call-${id} .full`); return b && b.querySelector('.full-trace'); }, {}, id, isOld);
    await page.evaluate((id, isOld) => { (isOld ? document.getElementById('full-' + id) : document.querySelector(`li#call-${id} .full`)).querySelectorAll('details').forEach((d) => { d.open = true; }); }, id, isOld);
    await sleep(300);
    const r = await page.evaluate(() => {
      const iw = window.innerWidth;
      const offenders = [...document.querySelectorAll('body *')].filter((e) => e.getBoundingClientRect().right > iw + 1).map((e) => `${e.tagName.toLowerCase()}${e.className ? '.' + String(e.className).split(' ')[0] : ''} right=${Math.round(e.getBoundingClientRect().right)} w=${Math.round(e.getBoundingClientRect().width)}`).slice(0, 6);
      const pre = document.querySelector('.full pre');
      return { innerWidth: iw, pageScrollWidth: document.documentElement.scrollWidth, bodyScrollWidth: document.body.scrollWidth, mainWidth: Math.round(document.querySelector('main').getBoundingClientRect().width), preWidth: pre && Math.round(pre.getBoundingClientRect().width), preOverflow: pre && getComputedStyle(pre).overflowX, offenders };
    });
    console.log(label, JSON.stringify(r));
  }
  await browser.close();
})();
