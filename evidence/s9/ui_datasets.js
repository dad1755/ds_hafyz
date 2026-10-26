// S9 browser check: a real Chromium drives a throwaway container of this image and exercises
// the dataset manager the way an administrator would.
//
//   375x812 (phone): sign in → Dataset manager → stage a valid upload → activate it → upload a
//   malformed CSV and read the rejection. Screenshots at each step.
//   1280x800 (desktop): the page after that activation, then one more valid upload.
//
// It records what the page actually said, whether anything overflowed horizontally, and
// whether any password or Argon2id hash ever appeared in the rendered text. Passwords and
// fixture paths come from the environment; nothing secret is printed.
//
// Usage: node ui_datasets.js <host> <port>

const { chromium } = require('playwright');

const HOST = process.argv[2] || 'aihubcampus-s9-ui';
const PORT = process.argv[3] || '2026';
const BASE = `http://${HOST}:${PORT}`;
const OUT = process.env.OUT_DIR || '.';

const ADMIN_USER = process.env.SYNTH_ADMIN_USER;
const ADMIN_PASSWORD = process.env.SYNTH_ADMIN_PASSWORD;
const VALID_CSV = process.env.VALID_CSV || `${OUT}/stage_valid.csv`;
const SECOND_CSV = process.env.SECOND_CSV || `${OUT}/stage_second.csv`;
const BAD_CSV = process.env.BAD_CSV || `${OUT}/stage_missing_column.csv`;

const DEPLOYED_DATASET_SHA = 'a0f0ab49d6326671d6cd83be5c88dcf18007025fe9a53ecd699119c871176ca1';

async function overflow(page) {
  return page.evaluate(() => ({
    viewport: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    overflowPx: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
  }));
}

async function pageText(page) {
  // The whole rendered column, not a hand-picked selector list: captions, alerts, metrics and
  // the dataframes' accessibility DOM all carry text that an administrator is meant to read.
  return page.evaluate(() => document.body.innerText.replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n'));
}

async function openSidebar(page) {
  const selectors = [
    '[data-testid="stSidebarCollapsedControl"] button',
    '[data-testid="stExpandSidebarButton"]',
    'button[aria-label="Open sidebar"]',
    'button[aria-label="Expand sidebar"]',
    'button[aria-label="Collapse sidebar"]',
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
      await page.waitForTimeout(2500);
      return;
    }
    await page.waitForTimeout(1500);
    seen.push(
      await page.evaluate(() =>
        Array.from(document.querySelectorAll('[role="radiogroup"] label')).map((label) =>
          (label.innerText || label.textContent || '').trim()
        )
      )
    );
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

async function stage(page, csvPath) {
  await page.locator('input[type="file"]').setInputFiles(csvPath);
  await page.waitForTimeout(1500);
  await page.getByRole('button', { name: 'Validate and stage dataset' }).click();
  await page.waitForTimeout(4000);
}

async function run(width, height, label, options) {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width, height } });
  const page = await context.newPage();
  const out = { label, width, height, steps: {}, says: {}, overflow: {}, screenshots: [] };

  await signIn(page, ADMIN_USER, ADMIN_PASSWORD);
  out.steps.admin_sign_in = true;
  // The navigation radio mounts with the signed-in page; wait for it before choosing a section.
  await page.waitForSelector('[role="radiogroup"] label', { timeout: 60000 });

  // The navigation labels are in the DOM whether or not the sidebar is expanded on a phone, and
  // the section choice is driven through the radio itself, so the sidebar is left as the app
  // rendered it — expanding it at 375px would overlay the page's own controls.
  await chooseSection(page, 'Dataset manager');
  out.steps.navigation_chosen = true;
  await page.getByRole('heading', { name: 'Dataset manager' }).first().waitFor({ timeout: 60000 });
  await page.waitForTimeout(1500);
  out.steps.dataset_page = true;

  const initial = await pageText(page);
  out.says.initial = initial.slice(0, 2600);
  out.checks = {
    deployed_panel: initial.includes('Deployed model dataset vs active dataset'),
    deployed_dataset_sha_shown: initial.includes(DEPLOYED_DATASET_SHA),
    seed_is_active: initial.includes('UCI_Credit_Card.csv'),
    honest_panel_on_fresh_db: initial.includes('The active dataset version is the same bytes'),
    no_rejections_yet: initial.includes('No upload has been rejected'),
    never_retrains_notice: initial.includes('Uploading does not retrain anything'),
    staged_is_not_deployed_warning: initial.includes('is **not** the dataset that built') ||
      initial.includes('is not the dataset that built'),
  };
  out.overflow.initial = await overflow(page);
  await page.screenshot({ path: `${OUT}/dataset_${label}_initial.png`, fullPage: false });
  out.screenshots.push(`dataset_${label}_initial.png`);

  if (options.stageAndActivate) {
    await stage(page, VALID_CSV);
    const staged = await pageText(page);
    out.says.after_stage = staged.slice(0, 2600);
    out.checks.staged_version = staged.includes('Staged as dataset version');
    out.checks.staged_not_active = staged.includes('it is **not** active') ||
      staged.includes('it is not active');
    out.checks.aggregate_preview = staged.includes('Aggregate preview (no rows)');
    out.checks.counts_quoted = /\b400\b/.test(staged) && /\b306\b/.test(staged);
    out.overflow.staged = await overflow(page);
    await page.screenshot({ path: `${OUT}/dataset_${label}_staged.png`, fullPage: false });
    out.screenshots.push(`dataset_${label}_staged.png`);

    const activate = page.getByRole('button', { name: /Activate dataset #\d+/ }).first();
    out.steps.activate_button_present = (await activate.count()) > 0;
    await activate.click();
    await page.waitForTimeout(4000);
    const activated = await pageText(page);
    out.says.after_activate = activated.slice(0, 2600);
    out.checks.activated_pointer = activated.includes('is now the active pointer');
    out.checks.model_unchanged_stated = activated.includes('The deployed model is unchanged');
    out.checks.mismatch_now_shown = activated.includes('is **not** the dataset that built') ||
      activated.includes('is not the dataset that built the deployed model');
    out.checks.deployed_sha_still_shown = activated.includes(DEPLOYED_DATASET_SHA);
    out.overflow.activated = await overflow(page);
    await page.screenshot({ path: `${OUT}/dataset_${label}_activated.png`, fullPage: false });
    out.screenshots.push(`dataset_${label}_activated.png`);
  }

  if (options.secondUpload) {
    await stage(page, SECOND_CSV);
    const second = await pageText(page);
    out.says.after_second_upload = second.slice(0, 2000);
    out.checks.second_staged = second.includes('Staged as dataset version');
  }

  if (options.reject) {
    await stage(page, BAD_CSV);
    const rejected = await pageText(page);
    out.says.after_rejection = rejected.slice(0, 2600);
    out.checks.rejected = rejected.includes('The upload was rejected and recorded');
    out.checks.rejection_reason_quoted = rejected.includes('missing required column(s): PAY_6');
    out.checks.rejection_log_row = rejected.includes('missing_column');
    out.checks.rejection_in_log_table = rejected.includes('missing_pay6.csv');
    out.overflow.rejected = await overflow(page);
    await page.screenshot({ path: `${OUT}/dataset_${label}_rejected.png`, fullPage: true });
    out.screenshots.push(`dataset_${label}_rejected.png`);
  }

  const finalText = await pageText(page);
  out.secret_sweep = {
    adminPassword: finalText.includes(ADMIN_PASSWORD) ? 1 : 0,
    argon2: finalText.includes('$argon2') ? 1 : 0,
  };

  await browser.close();
  return out;
}

(async () => {
  const phone = await run(375, 812, '375px', { stageAndActivate: true, reject: true });
  const desktop = await run(1280, 800, 'desktop', { secondUpload: true });
  console.log(JSON.stringify({ phone, desktop }, null, 2));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
