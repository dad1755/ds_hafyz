// S10 browser check: a real Chromium opens the model evaluation page and reads it.
//
//   375x812 (phone): sign in as the synthetic administrator → Model evaluation → every section
//   present, the figures painted, no horizontal overflow. Screenshots at the top, at the
//   confusion matrices and at the metadata panel.
//   1280x800 (desktop): the same page, then a second sign-in as a user to prove the section is
//   not offered to that role at all.
//
// The figures are matplotlib images, so this counts <img> elements that actually decoded
// (naturalWidth > 0) — a figure that failed to load is counted as missing, not as present.
// The comparison table is a Streamlit dataframe grid drawn on a canvas, so its cell values are
// not in document.innerText; the test suite and evidence/s10/trace_metrics.txt cover the values.
//
// Usage: node ui_evaluation.js <host> <port>

const { chromium } = require('playwright');

const HOST = process.argv[2] || 'aihubcampus-s10-ui';
const PORT = process.argv[3] || '2026';
const BASE = `http://${HOST}:${PORT}`;
const OUT = process.env.OUT_DIR || '.';

const ADMIN_USER = process.env.SYNTH_ADMIN_USER;
const ADMIN_PASSWORD = process.env.SYNTH_ADMIN_PASSWORD;
const USER_USER = process.env.SYNTH_USER_USER;
const USER_PASSWORD = process.env.SYNTH_USER_PASSWORD;

const EXPECTED_FIGURES = 11;
const METRICS_SHA = process.env.METRICS_SHA || '';

async function overflow(page) {
  return page.evaluate(() => ({
    viewport: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    overflowPx: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
  }));
}

async function pageText(page) {
  return page.evaluate(() =>
    document.body.innerText.replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n')
  );
}

async function figureCount(page) {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll('img')).filter((img) => img.naturalWidth > 0).length
  );
}

async function figureSizes(page) {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll('img'))
      .filter((img) => img.naturalWidth > 0)
      .map((img) => ({ w: img.naturalWidth, h: img.naturalHeight, alt: img.alt || '' }))
  );
}

async function navLabels(page) {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll('[role="radiogroup"] label')).map((label) =>
      (label.innerText || label.textContent || '').trim()
    )
  );
}

async function openSidebar(page) {
  const selectors = [
    '[data-testid="stSidebarCollapsedControl"] button',
    '[data-testid="stExpandSidebarButton"]',
    'button[aria-label="Open sidebar"]',
    'button[aria-label="Expand sidebar"]',
  ];
  for (const selector of selectors) {
    const toggle = page.locator(selector).first();
    if (await toggle.count()) {
      await toggle.click();
      await page.waitForTimeout(1200);
      return;
    }
  }
}

async function chooseSection(page, name) {
  const seen = [];
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const found = await page.evaluate((wanted) => {
      const labels = Array.from(document.querySelectorAll('[role="radiogroup"] label'));
      const target = labels.find(
        (label) => (label.innerText || label.textContent || '').trim() === wanted
      );
      if (!target) return false;
      const input = target.querySelector('input[type="radio"]') || target;
      input.click();
      return true;
    }, name);
    if (found) {
      await page.waitForTimeout(3500);
      return;
    }
    await page.waitForTimeout(1500);
    seen.push(await navLabels(page));
    await openSidebar(page);
  }
  throw new Error(`navigation option not found: ${name}; labels seen: ${JSON.stringify(seen)}`);
}

async function signIn(page, username, password) {
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.locator('input[aria-label="Username"]').fill(username);
  await page.locator('input[type="password"]').first().fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByText('Signed in as').first().waitFor({ timeout: 60000 });
}

async function scrollTo(page, text) {
  await page.evaluate((wanted) => {
    const node = Array.from(document.querySelectorAll('h4, h5, h3, p, div')).find(
      (element) => (element.innerText || '').trim().startsWith(wanted)
    );
    if (node) node.scrollIntoView({ block: 'start' });
  }, text);
  await page.waitForTimeout(1500);
}

async function adminRun(width, height, label) {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width, height } });
  const page = await context.newPage();
  const out = { label, width, height, steps: {}, checks: {}, overflow: {}, screenshots: [] };

  await signIn(page, ADMIN_USER, ADMIN_PASSWORD);
  out.steps.admin_sign_in = true;
  await page.waitForSelector('[role="radiogroup"] label', { timeout: 60000 });
  out.nav_labels = await navLabels(page);
  out.checks.nav_offers_evaluation = out.nav_labels.includes('Model evaluation');

  await chooseSection(page, 'Model evaluation');
  out.steps.navigation_chosen = true;
  await page.getByRole('heading', { name: 'Model evaluation' }).first().waitFor({ timeout: 60000 });
  // Matplotlib figures arrive with the first script run; give them time to decode.
  await page.waitForTimeout(6000);
  out.steps.evaluation_page = true;

  const text = await pageText(page);
  out.says = text.slice(0, 4000);
  out.figures = await figureCount(page);
  out.figure_sizes = await figureSizes(page);

  out.checks.provenance_caption =
    text.includes('read from the generated evaluation record at render time') ||
    text.includes('Every number below is read from the generated evaluation record');
  out.checks.metrics_sha_shown = METRICS_SHA ? text.includes(METRICS_SHA) : null;
  out.checks.section_comparison = text.includes('Model comparison');
  out.checks.section_confusion = text.includes('Confusion matrices');
  out.checks.section_eda = text.includes('Exploratory data analysis');
  out.checks.section_importance = text.includes('Feature importance');
  out.checks.section_metadata = text.includes('Model metadata');
  out.checks.section_limitations = text.includes('Limitations, in plain language');
  out.checks.low_recall_stated = /misses most defaults/i.test(text);
  out.checks.uncalibrated_stated = /not a risk percentage/i.test(text);
  out.checks.all_six_eda_titles = [
    'Class distribution',
    'Age by class',
    'Credit limit by class',
    'repayment status',
    'education code',
    'Correlation between',
  ].every((needle) => text.includes(needle));
  out.checks.figure_count_is_eleven = out.figures === EXPECTED_FIGURES;

  out.overflow.top = await overflow(page);
  await page.screenshot({ path: `${OUT}/evaluation_${label}_top.png`, fullPage: false });
  out.screenshots.push(`evaluation_${label}_top.png`);

  await scrollTo(page, 'Confusion matrices');
  out.overflow.confusion = await overflow(page);
  await page.screenshot({ path: `${OUT}/evaluation_${label}_confusion.png`, fullPage: false });
  out.screenshots.push(`evaluation_${label}_confusion.png`);

  await scrollTo(page, 'Model metadata');
  out.overflow.metadata = await overflow(page);
  await page.screenshot({ path: `${OUT}/evaluation_${label}_metadata.png`, fullPage: false });
  out.screenshots.push(`evaluation_${label}_metadata.png`);

  const finalText = await pageText(page);
  out.secret_sweep = {
    adminPassword: finalText.includes(ADMIN_PASSWORD) ? 1 : 0,
    userPassword: USER_PASSWORD && finalText.includes(USER_PASSWORD) ? 1 : 0,
    argon2: finalText.includes('$argon2') ? 1 : 0,
  };

  await browser.close();
  return out;
}

async function userRun() {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  const out = { label: 'user', checks: {} };

  await signIn(page, USER_USER, USER_PASSWORD);
  await page.waitForSelector('[role="radiogroup"] label', { timeout: 60000 });
  await page.waitForTimeout(1500);
  out.nav_labels = await navLabels(page);
  out.checks.evaluation_offered = out.nav_labels.includes('Model evaluation');
  out.checks.admin_offered = out.nav_labels.includes('User management');
  out.checks.dataset_manager_offered = out.nav_labels.includes('Dataset manager');
  const text = await pageText(page);
  out.checks.admin_surface_caption = /Administration \(accounts, datasets, model evaluation\)/.test(
    text
  );
  out.checks.no_evaluation_content = !/Confusion matrices|Feature importance/.test(text);
  await page.screenshot({ path: `${OUT}/evaluation_user_nav.png`, fullPage: false });
  out.screenshots = ['evaluation_user_nav.png'];

  await browser.close();
  return out;
}

(async () => {
  const phone = await adminRun(375, 812, '375px');
  const desktop = await adminRun(1280, 800, 'desktop');
  const user = await userRun();
  console.log(JSON.stringify({ phone, desktop, user }, null, 2));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
