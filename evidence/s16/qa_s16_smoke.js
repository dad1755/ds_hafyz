// Independent S16 release smoke — QA re-run (agent 7899db8c). Read-only against the live site:
// signs in as the operator's own admin and user accounts, opens the pages, scores ONE prediction
// with the demonstrator values and reads the number back. Creates no account, uploads nothing,
// changes no data beyond the single prediction row the acceptance test requires.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const BASE = (process.env.BASE_URL || 'https://www.aihubcampus.online').replace(/\/$/, '');
const CRED = JSON.parse(fs.readFileSync(process.env.CRED_FILE, 'utf8'));
const OUT = process.env.OUT_DIR || '.';
const EXPECT_PROB = process.env.EXPECT_PROB;
const SETTLE = Number(process.env.SETTLE_MS || 3000);

const checks = [];
function check(name, ok, detail) {
  checks.push({ name, ok: Boolean(ok) });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`);
  return ok;
}
const body = (p) => p.evaluate(() => document.body.innerText.replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n'));
async function waitText(page, needle, timeout = 90000) {
  const deadline = Date.now() + timeout;
  let last = '';
  while (Date.now() < deadline) {
    last = await body(page);
    if (last.includes(needle)) return last;
    await page.waitForTimeout(1000);
  }
  throw new Error(`timeout waiting for "${needle}"; page said: ${last.slice(0, 300)}`);
}
async function signIn(page, username, password) {
  const u = page.getByLabel('Username', { exact: true }).first();
  await u.waitFor({ timeout: 120000 });
  await u.fill(username);
  await page.getByLabel('Password', { exact: true }).first().fill(password);
  await page.getByRole('button', { name: 'Sign in' }).first().click();
  await page.waitForTimeout(SETTLE);
}
async function navLabels(page) {
  await page.locator('[role="radiogroup"]').first().waitFor({ timeout: 60000 });
  return page.evaluate(() => Array.from(document.querySelectorAll('[role="radiogroup"] label')).map((l) => (l.innerText || '').trim()));
}
async function nav(page, label, expect) {
  const opt = page.locator('[role="radiogroup"] label').filter({ hasText: label }).first();
  await opt.waitFor({ timeout: 60000 });
  await opt.click();
  await page.waitForTimeout(SETTLE);
  if (expect) await waitText(page, expect, 90000);
  return body(page);
}
async function signOut(page) {
  const btn = page.getByRole('button', { name: /sign out|log out/i }).first();
  if (await btn.count()) { await btn.click(); await page.waitForTimeout(SETTLE); return true; }
  return false;
}

(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  const shot = async (page, name) => page.screenshot({ path: path.join(OUT, name), fullPage: false });

  async function freshPage() {
    const ctx = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
    const page = await ctx.newPage();
    const t0 = Date.now();
    const resp = await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 90000 });
    return { ctx, page, resp, ms: Date.now() - t0 };
  }

  // ---- administrator ----
  let { ctx, page, resp, ms } = await freshPage();
  check('live HTTPS 200', resp && resp.status() === 200, `status=${resp && resp.status()} url=${page.url()} t=${ms}ms`);
  check('served by cloudflare', (resp.headers()['server'] || '').includes('cloudflare'), `server=${resp.headers()['server']}`);
  await shot(page, 'qa_s16_01_signin.png');

  await signIn(page, CRED.admin_user, CRED.admin_pass);
  const adminNav = await navLabels(page);
  check('admin signed in', adminNav.length >= 3, `nav=${JSON.stringify(adminNav)}`);
  check('admin sees user management', adminNav.some((l) => /user management/i.test(l)));
  check('admin sees dataset manager', adminNav.some((l) => /dataset manager/i.test(l)));
  check('admin sees model evaluation', adminNav.some((l) => /model evaluation/i.test(l)));
  await shot(page, 'qa_s16_02_admin_home.png');
  let text = await nav(page, 'User management', 'User management');
  check('user management renders accounts', /qa_s16_gate_user|role/i.test(text), (text.match(/qa_s16_gate_user/) || [''])[0]);
  await shot(page, 'qa_s16_03_admin_users.png');
  text = await nav(page, 'Model evaluation', 'Model evaluation');
  check('model evaluation shows held-out metrics', /0\.3557|0\.6611|recall/i.test(text), (text.match(/0\.3557|0\.6611/) || [''])[0]);
  await shot(page, 'qa_s16_04_admin_evaluation.png');
  await nav(page, 'Home', 'Signed in as');
  const so = page.locator('button:has-text("Sign out")').first();
  const signedOut = (await so.count()) > 0;
  if (signedOut) { await so.click(); await page.waitForTimeout(SETTLE); }
  const backAtLogin = await page.getByLabel('Username', { exact: true }).first().isVisible().catch(() => false);
  check('admin sign out returns to sign-in', signedOut && backAtLogin, `button=${signedOut} login_form=${backAtLogin}`);
  await ctx.close();

  // ---- user ----
  ({ ctx, page } = await freshPage());
  await signIn(page, CRED.user_user, CRED.user_pass);
  const userNav = await navLabels(page);
  check('user signed in', userNav.length >= 3, `nav=${JSON.stringify(userNav)}`);
  check('user has no admin pages', !userNav.some((l) => /user management|dataset manager|model evaluation/i.test(l)), JSON.stringify(userNav));
  text = await nav(page, 'Predict default risk', 'Predict default risk');
  check('23-input form present', /Credit limit/.test(text), 'form rendered');
  await shot(page, 'qa_s16_05_predict_form.png');
  await page.getByRole('button', { name: 'Load synthetic demonstrator example' }).first().click();
  await page.waitForTimeout(SETTLE);
  await page.getByRole('button', { name: 'Predict default risk' }).last().click();
  text = await waitText(page, 'Estimated model probability', 120000);
  text = await waitText(page, 'model version', 60000).catch(async () => body(page));
  const m = text.match(/(\d{1,3}\.\d{1,2})\s*%/);
  const shown = m ? Number(m[1]) : NaN;
  const expPct = Number(EXPECT_PROB) * 100;
  check('live prediction shown', Number.isFinite(shown), `displayed=${shown}%`);
  check('prediction matches pipeline output', Math.abs(shown - expPct) <= 0.01, `displayed=${shown}% expected=${expPct.toFixed(4)}% delta=${Number.isFinite(shown) ? Math.abs(shown - expPct).toFixed(4) : 'n/a'}pp`);
  check('result states class and model version', /default next month/i.test(text) && /aihubcampus-default-risk-1/.test(text), (text.match(/aihubcampus-default-risk-1[^\s]*/) || [''])[0]);
  await shot(page, 'qa_s16_06_prediction_result.png');
  await nav(page, 'My prediction history', 'own submissions only');
  const exp = page.locator('[data-testid="stExpander"]').first();
  if (await exp.count()) { await exp.locator('summary, [role="button"]').first().click().catch(() => {}); await page.waitForTimeout(SETTLE); }
  text = await body(page);
  const rowCount = Number((text.match(/(\d+) row\(s\) shown/) || [])[1]);
  check('own history lists the account\'s submissions', rowCount >= 1, `rows=${rowCount} for qa_s16_gate_user`);
  await shot(page, 'qa_s16_07_history.png');
  await ctx.close();

  await browser.close();
  const failed = checks.filter((c) => !c.ok);
  console.log(`\nchecks: ${checks.length}  passed: ${checks.length - failed.length}  failed: ${failed.length}`);
  if (failed.length) { console.log('FAILED: ' + failed.map((f) => f.name).join('; ')); process.exit(1); }
})().catch((e) => { console.error('SMOKE ERROR:', e.message); process.exit(2); });
