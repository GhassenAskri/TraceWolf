const puppeteer = require('puppeteer-core');
(async () => {
  const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const page = await browser.newPage(); page.setDefaultTimeout(10000); await page.setViewport({ width: 1200, height: 900 });
  for (const [label, base] of [['OLD', 'http://127.0.0.1:8011'], ['NEW', 'http://localhost:5173']]) {
    await page.goto(base + '/volumes/edge-cases', { waitUntil: 'networkidle0' });
    await page.waitForSelector('main ol.timeline > li.call');
    const cards = await page.$$eval('main ol.timeline > li.call', (els) => els.map((li) => li.querySelector('.meta').innerText.replace(/\s+/g, ' ').trim() + '  ||  ' + [...li.querySelectorAll('.msg')].map((m) => m.innerText.replace(/\s+/g, ' ').trim()).join(' / ')));
    console.log(label, cards.length, 'cards'); cards.forEach((c, i) => console.log('  ' + (i + 1) + '. ' + c));
  }
  await browser.close();
})();
