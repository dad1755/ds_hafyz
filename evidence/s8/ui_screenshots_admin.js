// S8 browser check: a real Chromium at 375x812 (phone) and 1280x800 (desktop) drives the
// running container — sign in as an administrator, open User management, create an account
// through the form, then sign out and sign in as that new account.
//
// It records whether the page overflows horizontally, what the page says, and whether the
// rendered page ever contains the Argon2id prefix or either password.
//
// Usage: node ui_screenshots_admin.js <host> <port>

const { chromium } = require('playwright');
const fs = require('fs');

const HOST = process.argv[2] || 'aihubcampus-s8-ui';
const PORT = process.argv[3] || '2026';
const BASE = `http://${HOST}:${PORT}`;
const OUT = process.env.OUT_DIR || '.';

const ADMIN_USER = process.env.SYNTH_ADMIN_USER;
const ADMIN_PASSWORD = process.env.SYNTH_ADMIN_PASSWORD;
const NEW_USER = process.env.SYNTH_NEW_USER;
const NEW_PASSWORD = process.env.SYNTH_NEW_PASSWORD;

async function overflow(page) {
  return page.evaluate(() => ({
    viewport: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    overflowPx: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
  }));
}

async function pageText(page) {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll('[data-testid="stMarkdownContainer"], [data-testid="stDataFrame"], [data-testid="stAlert"]'))
      .map((b) => b.innerText.trim())
      .filter((t) => t.length > 0)
      .join(' | ')
  );
}

async function openSidebar(page) {
  const toggle = page.locator('[data-testid="stSidebarCollapsedControl"] button').first();
  if (await toggle.count()) {
    await toggle.click();
    await page.waitForTimeout(800);
  }
}

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
  await page.waitForTimeout(1800);
}

async function signIn(page, username, password) {
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.locator('input[aria-label="Username"]').fill(username);
  await page.locator('input[type="password"]').first().fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await page.getByText('Signed in as').first().waitFor({ timeout: 40000 });
}

async function run(width, height, label) {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width, height } });
  const page = await context.newPage();
  // One account per viewport, so the two runs in this file do not collide on the username.
  const newUser = `${NEW_USER}_${width}`;
  const out = { label, width, height, newUser, steps: {} };

  await signIn(page, ADMIN_USER, ADMIN_PASSWORD);
  out.steps.admin_sign_in = true;
  out.home_text = await pageText(page);
  await page.screenshot({ path: `${OUT}/home_${label}.png` });

  await openSidebar(page);
  await chooseSection(page, 'User management');
  await page.getByRole('heading', { name: 'User management' }).first().waitFor({ timeout: 40000 });
  await page.waitForTimeout(1200);
  out.steps.admin_page = true;
  out.admin_overflow = await overflow(page);
  out.admin_text = await pageText(page);
  await page.screenshot({ path: `${OUT}/admin_${label}.png`, fullPage: false });

  // The accounts table and the guardrail captions, as rendered.
  out.table_headers = await page.evaluate(() => {
    const table = document.querySelector('[data-testid="stDataFrame"]');
    return table ? table.innerText.split('\n').slice(0, 3) : [];
  });

  // Create an account through the real form.
  await page.locator('input[aria-label="Username"]').last().fill(newUser);
  await page.locator('input[aria-label="Display name (optional)"]').fill('Created By Admin');
  await page.locator('input[aria-label="Initial password"]').fill(NEW_PASSWORD);
  await page.locator('input[aria-label="Confirm initial password"]').fill(NEW_PASSWORD);
  await page.getByRole('button', { name: 'Create account' }).click();

  // Wait on the page's own text rather than on a locator, so a re-render cannot race the wait.
  const deadline = Date.now() + 60000;
  let created = false;
  while (Date.now() < deadline) {
    const current = await pageText(page);
    if (current.includes(`Account ${newUser} created`)) {
      created = true;
      break;
    }
    await page.waitForTimeout(500);
  }
  if (!created) {
    throw new Error(`create form reported no success: ${(await pageText(page)).slice(-600)}`);
  }
  await page.waitForTimeout(1000);
  out.steps.create_account = true;
  out.create_overflow = await overflow(page);
  out.create_text = await pageText(page);
  await page.screenshot({ path: `${OUT}/created_${label}.png` });

  // Then sign in as the account that was just created — in a fresh browser context, so this is
  // a genuinely new session rather than the administrator's rerun.
  const freshContext = await browser.newContext({ viewport: { width, height } });
  const newPage = await freshContext.newPage();
  await signIn(newPage, newUser, NEW_PASSWORD);
  out.steps.new_user_sign_in = true;
  out.new_user_overflow = await overflow(newPage);
  out.new_user_text = await pageText(newPage);
  out.new_user_nav = await newPage.evaluate(() =>
    Array.from(document.querySelectorAll('[role="radiogroup"] label')).map((l) => l.innerText.trim())
  );
  await newPage.screenshot({ path: `${OUT}/new_user_${label}.png` });

  // Credential sweep over everything the browser can see.
  const everything = [out.home_text, out.admin_text, out.create_text, out.new_user_text].join(' ');
  out.grep = {
    hashPrefix: (everything.match(/\$argon2id\$/g) || []).length,
    adminPassword: (everything.match(new RegExp(ADMIN_PASSWORD.replace(/[-]/g, '\\-'), 'g')) || []).length,
    newPassword: (everything.match(new RegExp(NEW_PASSWORD.replace(/[-]/g, '\\-'), 'g')) || []).length,
    userManagementForNewUser: out.new_user_nav.includes('User management'),
  };

  await browser.close();
  return out;
}

(async () => {
  const results = [await run(375, 812, '375px'), await run(1280, 800, 'desktop')];
  fs.writeFileSync(`${OUT}/browser_check.json`, JSON.stringify(results, null, 2));
  for (const r of results) {
    console.log(`--- ${r.label} (${r.width}x${r.height}) ---`);
    console.log('steps:', JSON.stringify(r.steps));
    for (const key of ['admin_overflow', 'create_overflow', 'new_user_overflow']) {
      console.log(`${key}:`, JSON.stringify(r[key]));
    }
    console.log('table headers:', JSON.stringify(r.table_headers));
    console.log('grep:', JSON.stringify(r.grep));
    console.log('new user navigation:', JSON.stringify(r.new_user_nav));
    console.log('created text:', (r.create_text || '').slice(0, 400));
  }
  const ok = results.every(
    (r) =>
      r.steps.admin_sign_in &&
      r.steps.admin_page &&
      r.steps.create_account &&
      r.steps.new_user_sign_in &&
      r.grep.hashPrefix === 0 &&
      r.grep.adminPassword === 0 &&
      r.grep.newPassword === 0 &&
      r.grep.userManagementForNewUser === false &&
      r.admin_overflow.overflowPx === 0 &&
      r.create_overflow.overflowPx === 0
  );
  console.log(`\nRESULT: ${ok ? 'PASS' : 'FAIL'}`);
  process.exit(ok ? 0 : 1);
})().catch((error) => {
  console.error('FAILED:', error.message);
  process.exit(1);
});
