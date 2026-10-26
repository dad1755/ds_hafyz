// S7 browser check: a real Chromium at 375x812 (phone) and 1280x800 (desktop) drives the
// running container — sign in, open the prediction page, load the synthetic example, submit,
// read the result — and records whether the page overflows horizontally.
//
// Usage: node ui_screenshots.js <host> <port>
// Screenshots and a JSON summary are written to the working directory.

const { chromium } = require('playwright');
const fs = require('fs');

const HOST = process.argv[2] || 'aihubcampus-s7-ui';
const PORT = process.argv[3] || '2026';
const BASE = `http://${HOST}:${PORT}`;
const OUT = process.env.OUT_DIR || '.';
const USER = process.env.SYNTH_UI_USER;
const PASS = process.env.SYNTH_UI_PASSWORD;

async function overflow(page) {
  return page.evaluate(() => ({
    viewport: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    overflowPx: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
  }));
}

async function openSidebar(page) {
  const toggle = page.locator('[data-testid="stSidebarCollapsedControl"] button').first();
  if (await toggle.count()) {
    await toggle.click();
    await page.waitForTimeout(800);
  }
}

// The sidebar drawer sits off-canvas at phone width, so navigation is chosen by dispatching a
// click on the radio input itself rather than by a viewport-relative pointer click.
async function chooseSection(page, name) {
  const ok = await page.evaluate((wanted) => {
    const labels = Array.from(document.querySelectorAll('[role="radiogroup"] label'));
    const target = labels.find((l) => l.innerText.trim() === wanted);
    if (!target) return false;
    const input = target.querySelector('input[type="radio"]') || target;
    input.click();
    return true;
  }, name);
  if (!ok) throw new Error(`navigation option not found: ${name}`);
  await page.waitForTimeout(1500);
}

async function run(width, height, label) {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width, height } });
  const page = await context.newPage();
  const out = { label, width, height, steps: {} };

  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.locator('input[aria-label="Username"]').fill(USER);
  await page.locator('input[type="password"]').first().fill(PASS);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByText('Signed in as').first().waitFor({ timeout: 30000 });
  out.steps.sign_in = true;
  await page.screenshot({ path: `${OUT}/home_${label}.png`, fullPage: false });

  await openSidebar(page);
  await chooseSection(page, 'Predict default risk');
  await page.getByText('1 · Credit profile').first().waitFor({ timeout: 30000 });
  out.steps.predict_page = true;
  out.form_overflow = await overflow(page);
  await page.screenshot({ path: `${OUT}/form_${label}.png`, fullPage: false });

  await page.getByRole('button', { name: 'Load synthetic demonstrator example' }).click();
  await page.waitForTimeout(1500);
  out.demo_overflow = await overflow(page);
  await page.screenshot({ path: `${OUT}/form_filled_${label}.png`, fullPage: false });

  await page.getByRole('button', { name: 'Predict default risk' }).click();
  await page.getByText('Risk band').first().waitFor({ timeout: 30000 });
  await page.waitForTimeout(800);
  out.steps.result = true;
  out.result_overflow = await overflow(page);
  out.result_text = await page.evaluate(() => {
    const blocks = Array.from(document.querySelectorAll('[data-testid="stMarkdownContainer"]'));
    return blocks.map((b) => b.innerText.trim()).filter((t) => t.length > 0).join(' | ');
  });
  await page.screenshot({ path: `${OUT}/result_${label}.png`, fullPage: false });

  await openSidebar(page);
  await chooseSection(page, 'My prediction history');
  await page.getByText('My prediction history').first().waitFor({ timeout: 30000 });
  await page.waitForTimeout(1200);
  out.history_overflow = await overflow(page);
  out.history_text = await page.evaluate(() => {
    const blocks = Array.from(document.querySelectorAll('[data-testid="stMarkdownContainer"]'));
    return blocks.map((b) => b.innerText.trim()).filter((t) => t.length > 0).join(' | ');
  });
  await page.screenshot({ path: `${OUT}/history_${label}.png`, fullPage: false });

  await browser.close();
  return out;
}

(async () => {
  const results = [await run(375, 812, '375px'), await run(1280, 800, 'desktop')];
  fs.writeFileSync(`${OUT}/browser_check.json`, JSON.stringify(results, null, 2));
  for (const r of results) {
    console.log(`--- ${r.label} (${r.width}x${r.height}) ---`);
    console.log('steps:', JSON.stringify(r.steps));
    for (const key of ['form_overflow', 'demo_overflow', 'result_overflow', 'history_overflow']) {
      console.log(`${key}:`, JSON.stringify(r[key]));
    }
  }
})().catch((error) => {
  console.error('FAILED:', error.message);
  process.exit(1);
});
