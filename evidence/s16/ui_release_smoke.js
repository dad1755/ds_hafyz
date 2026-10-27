// S16 release smoke — the live site, both roles, end to end, with the probability checked
// against the pipeline that produced it.
//
//   BASE_URL=https://www.aihubcampus.online OUT_DIR=evidence/s16 CRED_FILE=<scratch>/creds.json \
//   INVALID_CSV=<scratch>/invalid.csv EXPECT_PROB=0.7195348837209302 EXPECT_CLASS=1 \
//   EXPECT_MODEL=aihubcampus-default-risk-1+48ce02563b2a \
//     node evidence/s16/ui_release_smoke.js
//
// This is the release acceptance smoke, not a second test suite. It walks what a user and an
// administrator actually do against the public URL through a real Chromium, and it fails loudly
// if the number on the screen is not the number the artifact produces:
//
//   administrator : sign in → user management → dataset manager (a broken CSV is refused) →
//                   model evaluation → sign out
//   user          : sign in → the 23 inputs → the scored result → own history →
//                   an incomplete submission is refused before the model → sign out
//   parity        : the displayed probability, class and model version against the values
//                   scripts passed in, which were computed from the artifact without Streamlit
//
// The administrator is synthetic (created for the run, deactivated after it): the operator's
// own account is the operator's. The user's credential is read from .env by this process and is
// never printed.
//
// Usage: see the header. Exit code 0 = every check passed.

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const BASE = (process.env.BASE_URL || 'https://www.aihubcampus.online').replace(/\/$/, '');
const OUT = process.env.OUT_DIR || '.';
const CRED_FILE = process.env.CRED_FILE;
const INVALID_CSV = process.env.INVALID_CSV;
const EXPECT_PROB = Number(process.env.EXPECT_PROB);
const EXPECT_CLASS = String(process.env.EXPECT_CLASS);
const EXPECT_MODEL = process.env.EXPECT_MODEL || '';
const SETTLE = Number(process.env.SETTLE_MS || 2500);

// The demonstrator row the Predict page loads (src/pages_prediction.py:DEMO_EXAMPLE), copied so
// the smoke can assert the form really shows these values rather than trusting session state.
const DEMO_EXAMPLE = {
  LIMIT_BAL: '120000', AGE: '34',
  BILL_AMT1: '35000', BILL_AMT2: '33500', BILL_AMT3: '30000',
  BILL_AMT4: '28000', BILL_AMT5: '26500', BILL_AMT6: '25000',
  PAY_AMT1: '2000', PAY_AMT2: '2500', PAY_AMT3: '3000',
  PAY_AMT4: '3000', PAY_AMT5: '3500', PAY_AMT6: '4000',
};
const LABELS = {
  LIMIT_BAL: 'Credit limit (NTD, including supplementary cards)',
  AGE: 'Age (whole years)',
  BILL_AMT1: 'BILL_AMT1 — statement balance, Sep 2005 (NTD)',
  BILL_AMT2: 'BILL_AMT2 — statement balance, Aug 2005 (NTD)',
  BILL_AMT3: 'BILL_AMT3 — statement balance, Jul 2005 (NTD)',
  BILL_AMT4: 'BILL_AMT4 — statement balance, Jun 2005 (NTD)',
  BILL_AMT5: 'BILL_AMT5 — statement balance, May 2005 (NTD)',
  BILL_AMT6: 'BILL_AMT6 — statement balance, Apr 2005 (NTD)',
  PAY_AMT1: 'PAY_AMT1 — amount paid, Sep 2005 (NTD)',
  PAY_AMT2: 'PAY_AMT2 — amount paid, Aug 2005 (NTD)',
  PAY_AMT3: 'PAY_AMT3 — amount paid, Jul 2005 (NTD)',
  PAY_AMT4: 'PAY_AMT4 — amount paid, Jun 2005 (NTD)',
  PAY_AMT5: 'PAY_AMT5 — amount paid, May 2005 (NTD)',
  PAY_AMT6: 'PAY_AMT6 — amount paid, Apr 2005 (NTD)',
};

const checks = [];
function check(name, ok, detail) {
  checks.push({ name, ok: Boolean(ok) });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`);
  return ok;
}

function loadEnv(file) {
  const out = {};
  for (const raw of fs.readFileSync(file, 'utf8').split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq < 0) continue;
    let value = line.slice(eq + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    out[line.slice(0, eq).trim()] = value;
  }
  return out;
}

const repoEnv = loadEnv(path.join(__dirname, '..', '..', '.env'));
const synth = JSON.parse(fs.readFileSync(CRED_FILE, 'utf8'));

const body = (page) =>
  page.evaluate(() => document.body.innerText.replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n'));
const domText = (page) => page.evaluate(() => document.body.textContent.replace(/\s+/g, ' '));

async function waitText(page, needle, timeout = 90000) {
  const deadline = Date.now() + timeout;
  let last = '';
  while (Date.now() < deadline) {
    last = await body(page);
    if (last.includes(needle)) return last;
    await page.waitForTimeout(1000);
  }
  throw new Error(`timeout waiting for "${needle}"; page said: ${last.slice(0, 400)}`);
}

const navLabels = async (page) => {
  await page.locator('[role="radiogroup"]').first().waitFor({ timeout: 60000 });
  return page.evaluate(() =>
    Array.from(document.querySelectorAll('[role="radiogroup"] label')).map((l) =>
      (l.innerText || l.textContent || '').trim()));
};

async function nav(page, label, expect) {
  const option = page.locator('[role="radiogroup"] label').filter({ hasText: label }).first();
  await option.waitFor({ timeout: 60000 });
  await option.click();
  await page.waitForTimeout(SETTLE);
  if (!expect) return body(page);
  try {
    return await waitText(page, expect, 60000);
  } catch (error) {
    await option.click();
    await page.waitForTimeout(SETTLE);
    return waitText(page, expect, 60000);
  }
}

async function signIn(page, username, password) {
  const user = page.getByLabel('Username').first();
  try {
    await user.waitFor({ timeout: 120000 });
  } catch (error) {
    await page.reload({ waitUntil: 'domcontentloaded' });
    await user.waitFor({ timeout: 120000 });
  }
  await user.fill(username);
  await page.getByLabel('Password').first().fill(password);
  await page.getByRole('button', { name: 'Sign in' }).first().click();
  await page.waitForTimeout(SETTLE);
}

async function signOut(page) {
  await nav(page, 'Home', 'Signed in as');
  await page.getByRole('button', { name: 'Sign out' }).first().click();
  await waitText(page, 'Sign in', 60000);
}

async function stageUpload(page, csv, needles, timeout = 150000) {
  const list = Array.isArray(needles) ? needles : [needles];
  await page.locator('input[type="file"]').first().setInputFiles(csv);
  await waitText(page, 'KB', 60000);
  const deadline = Date.now() + timeout;
  let text = '';
  while (Date.now() < deadline) {
    await page.waitForTimeout(4000);
    await page.getByRole('button', { name: 'Validate and stage dataset' }).first().click();
    await page.waitForTimeout(5000);
    text = await body(page);
    if (list.some((n) => text.includes(n))) return text;
    if (!/Choose a CSV file first/.test(text)) return text;
  }
  return text;
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  // ---------------------------------------------------------- 1. the public surface
  let response;
  try {
    response = await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 90000 });
  } catch (error) {
    console.log(`RETRY first navigation — ${(error.message || '').split('\n')[0]}`);
    await page.waitForTimeout(5000);
    response = await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 90000 });
  }
  const headers = response.headers();
  check('HTTPS root answers 200', response.status() === 200, `status=${response.status()}`);
  check('the response is served by the Cloudflare edge',
        /cloudflare/i.test(headers['server'] || '') && Boolean(headers['cf-ray']),
        `server=${headers['server']} cf-ray=${headers['cf-ray']}`);
  await waitText(page, 'Sign in', 300000);
  check('the sign-in form renders on the public URL', true, 'body contains "Sign in"');
  await page.screenshot({ path: path.join(OUT, 's16_01_signin.png') });

  // ------------------------------------------------- 2. administrator, end to end
  await signIn(page, synth.username, synth.password);
  const adminBody = await waitText(page, 'Signed in as');
  const adminNav = await navLabels(page);
  check('administrator signs in through the tunnel', adminBody.includes('Signed in as'), synth.username);
  check('administrator sees the six admin sections', adminNav.length === 6, adminNav.join(' | '));
  await page.screenshot({ path: path.join(OUT, 's16_02_admin_home.png') });

  await nav(page, 'User management', 'Create an account');
  const users = await body(page);
  const usersDom = await domText(page);
  const listed = ['ds_hafyz', 'demo_user'].filter((n) => users.includes(n));
  check('user management lists the operator admin and the demo user', listed.length === 2, listed.join(', '));
  check('the four account controls are present',
        ['Create an account', 'Save role', 'Set temporary password', 'Deactivate account']
          .every((n) => usersDom.includes(n)), 'create / role / temporary password / deactivate');
  check('no password hash is rendered on the page', !/argon2id\$|\$argon2|password_hash/.test(users),
        'no hash text in the body');
  await page.screenshot({ path: path.join(OUT, 's16_03_user_management.png'), fullPage: true });

  await nav(page, 'Dataset manager', 'Deployed model dataset vs active dataset');
  await page.waitForTimeout(2000);
  const rejectBody = await stageUpload(page, INVALID_CSV, 'Rejection #');
  const reason = (rejectBody.match(/The upload was rejected and recorded: ([^\n]+)/) || [])[1];
  const rejectId = (rejectBody.match(/Rejection #(\d+)/) || [])[1];
  const codes = (rejectBody.match(/stable error codes? ([a-z_, ]+)/) || [])[1];
  check('a CSV that breaks the 25-column contract is refused', Boolean(reason) && Boolean(rejectId),
        `rejection #${rejectId || '?'} — ${(reason || 'no message').trim()}`);
  check('the refusal names stable error codes', Boolean(codes), (codes || '?').trim());
  check('the refusal states nothing was repaired or partially loaded',
        /nothing was cleaned, coerced or partially loaded/.test(rejectBody), 'stated on the page');
  await page.screenshot({ path: path.join(OUT, 's16_04_invalid_csv_rejected.png'), fullPage: true });

  await nav(page, 'Model evaluation', 'Confusion matrices');
  const evalBody = await body(page);
  const panels = ['Model comparison', 'Confusion matrices', 'Feature importance', 'Model metadata']
    .filter((p) => evalBody.includes(p));
  check('model evaluation renders the shipped metrics, matrices, importances and metadata',
        panels.length === 4, panels.join(' | '));
  await page.screenshot({ path: path.join(OUT, 's16_05_model_evaluation.png'), fullPage: true });

  await signOut(page);
  check('administrator signs out', (await body(page)).includes('Sign in'), 'sign-in form returned');

  // -------------------------------------------------------------- 3. user, end to end
  await signIn(page, repoEnv.INITIAL_USER_USERNAME, repoEnv.INITIAL_USER_PASSWORD);
  const userBody = await waitText(page, 'Signed in as');
  const userNav = await navLabels(page);
  check('user signs in through the tunnel', userBody.includes('Signed in as'), repoEnv.INITIAL_USER_USERNAME);
  check('user sees three sections only', userNav.length === 3, userNav.join(' | '));
  check('the user is offered no administrator section',
        !userNav.some((l) => /User management|Dataset manager|Model evaluation/.test(l)),
        userNav.join(' | '));

  await nav(page, 'Predict default risk', 'Load synthetic demonstrator example');
  const groups = await page.evaluate(() =>
    Array.from(document.querySelectorAll('details summary, [data-testid="stExpander"] summary'))
      .map((n) => (n.innerText || '').trim()).filter((t) => /inputs/.test(t)));
  check('the form is the four documented groups covering 23 inputs', groups.length === 4,
        groups.join(' | '));

  await page.getByRole('button', { name: 'Load synthetic demonstrator example' }).first().click();
  await page.waitForTimeout(SETTLE);
  const shown = await page.evaluate((labels) => {
    const out = {};
    for (const [name, label] of Object.entries(labels)) {
      const input = document.querySelector(`input[aria-label="${label}"]`);
      out[name] = input ? input.value : null;
    }
    return out;
  }, LABELS);
  const mismatched = Object.entries(DEMO_EXAMPLE).filter(([n, v]) => String(shown[n]) !== v);
  check('all 23 inputs are loaded, the 14 numeric ones reading back as typed',
        mismatched.length === 0,
        mismatched.length ? mismatched.map(([n, v]) => `${n}: expected ${v} got ${shown[n]}`).join('; ')
                          : 'LIMIT_BAL=120000, AGE=34, BILL_AMT1..6, PAY_AMT1..6 as documented');
  await page.screenshot({ path: path.join(OUT, 's16_06_prediction_form.png'), fullPage: true });

  await page.getByRole('button', { name: 'Predict default risk' }).first().click();
  await page.waitForTimeout(4000);
  const result = await body(page);
  const probText = (result.match(/([\d.]+%)\s*\*?\s*\(estimated/i) || [])[1];
  const band = ((result.match(/Risk band: \**([^*\n]+)/i) || [])[1] || '').trim();
  const advice = ((result.match(/What this suggests: \**([^\n]+)/i) || [])[1] || '').trim();
  const threshold = (result.match(/Decision threshold ([\d.]+)/) || [])[1];
  const modelVersion = (result.match(/model version (\S+)/) || [])[1];
  const classLabel = (result.match(/(No default next month|Default next month)/) || [])[1] || '';
  check('the model returns a probability, a band and advice',
        Boolean(probText) && Boolean(band) && Boolean(advice),
        `probability=${probText || '?'} band=${band || '?'}`);
  check('the result states the decision threshold and the model version',
        Boolean(threshold) && Boolean(modelVersion),
        `threshold=${threshold || '?'} model=${modelVersion || '?'}`);
  await page.screenshot({ path: path.join(OUT, 's16_07_prediction_result.png'), fullPage: true });

  // ------------------------------------------------------- 4. the parity check
  const shownPct = probText ? Number(probText.replace('%', '')) : NaN;
  const expectPct = EXPECT_PROB * 100;
  const deltaPct = Math.abs(shownPct - expectPct);
  check('the displayed probability equals the artifact\'s own probability',
        Number.isFinite(shownPct) && deltaPct <= 0.01,
        `displayed ${probText} vs direct ${expectPct.toFixed(4)}% (delta ${Number.isFinite(deltaPct) ? deltaPct.toFixed(4) : '?'} pp, display is rounded to 2 dp)`);
  const expectLabel = EXPECT_CLASS === '1' ? 'Default next month' : 'No default next month';
  check('the displayed class equals the artifact\'s own class', classLabel === expectLabel,
        `displayed "${classLabel}" vs direct class ${EXPECT_CLASS} ("${expectLabel}")`);
  check('the displayed model version is the artifact the pipeline loaded',
        Boolean(EXPECT_MODEL) && modelVersion === EXPECT_MODEL,
        `displayed ${modelVersion || '?'} vs ${EXPECT_MODEL || '?'}`);

  // ------------------------------------------------------------ 5. the user's history
  await nav(page, 'My prediction history');
  await page.waitForTimeout(2000);
  const histBody = await body(page);
  const rows = (histBody.match(/(\d+) row\(s\) shown for/) || [])[1];
  check('the scored request is in the user\'s own history', Number(rows) >= 1,
        `${rows === undefined ? 'no count rendered' : rows + ' row(s) for this account'}`);
  await page.screenshot({ path: path.join(OUT, 's16_08_history.png'), fullPage: true });

  // ------------------------------------------ 6. an incomplete submission is refused
  await nav(page, 'Predict default risk', 'Load synthetic demonstrator example');
  const clear = page.getByRole('button', { name: 'Clear result' });
  if (await clear.count()) {
    await clear.first().click();
    await page.waitForTimeout(SETTLE);
  }
  const limit = page.locator(`input[aria-label="${LABELS.LIMIT_BAL}"]`).first();
  await limit.fill('');
  await limit.press('Tab');
  await page.waitForTimeout(1500);
  await page.getByRole('button', { name: 'Predict default risk' }).first().click();
  await page.waitForTimeout(3000);
  const invalid = await body(page);
  const message = (invalid.match(/(feature '[A-Z_0-9]+'[^\n]*|missing feature\(s\)[^\n]*)/) || [])[1];
  check('an incomplete submission is refused with a named feature', Boolean(message),
        message || 'no validation message rendered');
  check('the refusal says nothing was scored and nothing recorded',
        /rejected before the model was called/.test(invalid), 'caption rendered');
  await page.screenshot({ path: path.join(OUT, 's16_09_invalid_input.png'), fullPage: true });

  await signOut(page);
  check('user signs out', (await body(page)).includes('Sign in'), 'sign-in form returned');

  await browser.close();

  const failed = checks.filter((c) => !c.ok);
  console.log('');
  console.log(`RESULT: ${checks.length - failed.length} passed, ${failed.length} failed`);
  if (failed.length) {
    console.log('FAILED: ' + failed.map((c) => c.name).join(' | '));
    process.exit(1);
  }
  console.log('RELEASE SMOKE PASSED — both roles complete end to end on the live URL and the');
  console.log('displayed probability is the artifact\'s own probability.');
})().catch(async (error) => {
  console.log('ERROR ' + (error && error.message ? error.message : error));
  process.exit(2);
});
