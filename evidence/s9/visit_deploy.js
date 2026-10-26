// Open the deployed application once, the way a visitor would, so the app performs its own
// startup work (schema migration + seed dataset registration) before anyone signs in.
const { chromium } = require('playwright');

const HOST = process.argv[2] || 'web';
const PORT = process.argv[3] || '2026';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.goto(`http://${HOST}:${PORT}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(6000);
  const title = await page.title();
  const says = await page.evaluate(() =>
    document.body.innerText.replace(/[ \t]+/g, ' ').split('\n').filter(Boolean).slice(0, 8)
  );
  console.log(JSON.stringify({ url: page.url(), title, firstLines: says }, null, 2));
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
