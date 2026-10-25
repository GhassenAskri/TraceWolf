const puppeteer = require('puppeteer-core');
(async () => {
  const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const page = await browser.newPage(); page.setDefaultTimeout(10000);
  const log = [];
  page.on('console', (m) => { if (m.type() === 'error') log.push(m.text().slice(0, 200)); });
  page.on('requestfailed', (r) => log.push('requestfailed ' + r.url().slice(0, 80) + ' ' + (r.failure() || {}).errorText));
  await page.goto('http://localhost:4173/volumes/tools-demo', { waitUntil: 'networkidle0' });
  await new Promise((r) => setTimeout(r, 1500));
  console.log('page text:', JSON.stringify((await page.$eval('main', (e) => e.innerText)).replace(/\s+/g, ' ').slice(0, 160)));
  console.log('sidebar text:', JSON.stringify((await page.$eval('.sidebar', (e) => e.innerText)).replace(/\s+/g, ' ').slice(0, 120)));
  console.log('console:', log.length ? log : 'none');
  await browser.close();
})();
