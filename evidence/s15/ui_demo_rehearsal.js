// S15 demo rehearsal — the demo script in docs/presentation_script.md, executed in order
// against the live public URL by a real Chromium.
//
//   https://www.aihubcampus.online  →  Cloudflare edge  →  tunnel  →  http://web:2026
//
// This file is the rehearsal, not a second test suite: it walks the exact sequence the
// presenter will walk on demo day, records what each step actually rendered (probability,
// band, advice, rejection text, staged version, held-out numbers), times every step, and
// writes one screenshot per step. The numbers it prints are the numbers
// docs/presentation_script.md quotes.
//
// The administrator used here is synthetic (created for the run, deactivated after it): the
// operator's own account belongs to the operator and its credential is not rewritten. The
// demo user's credential is read from .env by this process and is never printed.
//
// Usage: BASE_URL=https://www.aihubcampus.online CRED_FILE=/path/creds.json \
//        VALID_CSV=/path/valid.csv INVALID_CSV=/path/invalid.csv OUT_DIR=evidence/s15 \
//        node ui_demo_rehearsal.js

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const BASE = (process.env.BASE_URL || 'https://www.aihubcampus.online').replace(/\/$/, '');
const OUT = process.env.OUT_DIR || '.';
const CRED_FILE = process.env.CRED_FILE;
const VALID_CSV = process.env.VALID_CSV;
const INVALID_CSV = process.env.INVALID_CSV;
const SETTLE = Number(process.env.SETTLE_MS || 2500);

// The demonstrator row the Predict page loads, copied here so the rehearsal can assert that the
// form actually shows these values. It is the same dictionary as
// src/pages_prediction.py:DEMO_EXAMPLE — the assertion fails loudly if the two ever drift.
const DEMO_EXAMPLE = {
  LIMIT_BAL: '120000',
  AGE: '34',
  BILL_AMT1: '35000',
  BILL_AMT2: '33500',
  BILL_AMT3: '30000',
  BILL_AMT4: '28000',
  BILL_AMT5: '26500',
  BILL_AMT6: '25000',
  PAY_AMT1: '2000',
  PAY_AMT2: '2500',
  PAY_AMT3: '3000',
  PAY_AMT4: '3000',
  PAY_AMT5: '3500',
  PAY_AMT6: '4000',
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

// The nine coded inputs, as ml/schema.py labels them. Read from the rendered widget so the
// rehearsal proves the demonstrator put these codes on screen, not just in session state.
const CODE_EXPECT = {
  'Sex code': '2 — female',
  'Education code': '2 — university',
  'Marital status code': '2 — single',
  'PAY_0 — repayment status, Sep 2005': '2 — two months of delay',
  'PAY_2 — repayment status, Aug 2005': '2 — two months of delay',
  'PAY_3 — repayment status, Jul 2005': '0 — revolving credit (minimum payment)',
  'PAY_4 — repayment status, Jun 2005': '0 — revolving credit (minimum payment)',
  'PAY_5 — repayment status, May 2005': '-1 — paid in full that month',
  'PAY_6 — repayment status, Apr 2005': '-1 — paid in full that month',
};

const checks = [];
const observations = [];
const timings = [];
let stepStart = Date.now();

function check(name, ok, detail) {
  checks.push({ name, ok: Boolean(ok), detail: detail === undefined ? '' : String(detail) });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`);
  return ok;
}

function step(label) {
  const now = Date.now();
  if (label) timings.push({ step: label, seconds: Number(((now - stepStart) / 1000).toFixed(1)) });
  stepStart = now;
}

function loadEnv(file) {
  const out = {};
  for (const raw of fs.readFileSync(file, 'utf8').split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq < 0) continue;
    let value = line.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
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

// Visible text only, for anything the reader must actually see.
const bodyText = (page) => page.evaluate(() => document.body.textContent.replace(/\s+/g, ' '));

const navLabels = async (page) => {
  await page.locator('[role="radiogroup"]').first().waitFor({ timeout: 30000 });
  return page.evaluate(() =>
    Array.from(document.querySelectorAll('[role="radiogroup"] label')).map((label) =>
      (label.innerText || label.textContent || '').trim()
    )
  );
};

// Streamlit keeps hidden aria-live nodes in the DOM, and getByText(...).waitFor() can bind to
// one of those and wait forever. Poll the rendered body text instead: it is what the presenter
// will actually read on screen.
async function waitText(page, needle, timeout = 60000) {
  const deadline = Date.now() + timeout;
  let last = '';
  while (Date.now() < deadline) {
    last = await body(page);
    if (last.includes(needle)) return last;
    await page.waitForTimeout(1000);
  }
  throw new Error(`timeout waiting for "${needle}"; page said: ${last.slice(0, 400)}`);
}

async function nav(page, label, expect) {
  const option = page.locator('[role="radiogroup"] label').filter({ hasText: label }).first();
  await option.waitFor({ timeout: 30000 });
  await option.click();
  await page.waitForTimeout(SETTLE);
  if (expect) {
    try {
      return await waitText(page, expect, 45000);
    } catch (error) {
      // One retry: a click that lands while Streamlit is still re-rendering the sidebar can be
      // swallowed, and the rehearsal should report that rather than fail the demo step.
      await option.click();
      await page.waitForTimeout(SETTLE);
      return waitText(page, expect, 45000);
    }
  }
  return body(page);
}

// The sign-in form can arrive a long time after the shell (a cold Streamlit session behind the
// Cloudflare edge measured 32 s once), so wait for the input itself, and recover from one stale
// page by reloading rather than failing the whole rehearsal.
async function signIn(page, username, password) {
  const user = page.getByLabel('Username').first();
  try {
    await user.waitFor({ timeout: 90000 });
  } catch (error) {
    await page.reload({ waitUntil: 'domcontentloaded' });
    await user.waitFor({ timeout: 90000 });
  }
  await user.fill(username);
  await page.getByLabel('Password').first().fill(password);
  await page.getByRole('button', { name: 'Sign in' }).first().click();
  await page.waitForTimeout(SETTLE);
}

async function signOut(page) {
  await nav(page, 'Home', 'Signed in as');
  await page.getByRole('button', { name: 'Sign out' }).first().click();
  await waitText(page, 'Sign in', 45000);
}

// Streamlit renders the file chip (and its size badge) before the bytes have finished crossing
// the tunnel, so pressing "Validate and stage dataset" too early legitimately answers "choose a
// file first". Retry the button until the page reports an outcome instead of assuming a timing.
async function stageUpload(page, csv, expectNeedle, timeout = 120000) {
  const needles = Array.isArray(expectNeedle) ? expectNeedle : [expectNeedle];
  await page.locator('input[type="file"]').first().setInputFiles(csv);
  await waitText(page, 'KB', 60000);
  const deadline = Date.now() + timeout;
  let text = '';
  while (Date.now() < deadline) {
    await page.waitForTimeout(4000);
    await page.getByRole('button', { name: 'Validate and stage dataset' }).first().click();
    await page.waitForTimeout(5000);
    text = await body(page);
    if (needles.some((needle) => text.includes(needle))) return text;
    if (!/Choose a CSV file first/.test(text)) return text;
  }
  return text;
}

const historyCount = (text) => {
  const match = text.match(/(\d+) row\(s\) shown for/);
  return match ? Number(match[1]) : undefined;
};

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  // ------------------------------------------------------- step 0 — open the live site
  const firstPaint = Date.now();
  // One retry on the first navigation: the host's route to the edge changed mid-run once
  // (net::ERR_NETWORK_CHANGED), which says nothing about the deployment.
  let first;
  try {
    first = await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  } catch (error) {
    console.log(`RETRY first navigation — ${(error.message || '').split('\n')[0]}`);
    await page.waitForTimeout(5000);
    first = await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  }
  const headers = first.headers();
  check('live URL answers through the Cloudflare edge',
        /cloudflare/i.test(headers['server'] || ''), `server=${headers['server']}`);
  await waitText(page, 'Sign in', 300000);
  check('sign-in form rendered', true,
        `first paint ${((Date.now() - firstPaint) / 1000).toFixed(1)}s after navigation`);
  await page.screenshot({ path: path.join(OUT, 's15_01_signin.png') });
  step('open the live URL');

  // ------------------------------------- step 1 — administrator signs in (demo step 1)
  await signIn(page, synth.username, synth.password);
  await waitText(page, 'Signed in as');
  const adminBody = await body(page);
  const adminNav = await navLabels(page);
  check('administrator signs in', adminBody.includes('Signed in as'), synth.username);
  check('administrator navigation offers six sections', adminNav.length === 6, adminNav.join(' | '));
  await page.screenshot({ path: path.join(OUT, 's15_02_admin_home.png') });
  step('administrator signs in');

  // ----------------------------------------- step 2 — user management (demo step 2)
  await nav(page, 'User management', 'Create an account');
  const userMgmtBody = await body(page);
  const userMgmtDom = await bodyText(page);
  const listedUsers = ['ds_hafyz', 'demo_user'].filter((name) => userMgmtBody.includes(name));
  check('user management lists the operator admin and the demo user',
        listedUsers.length === 2, listedUsers.join(', '));
  // Three of the four controls sit inside collapsed expanders: present in the DOM, not in the
  // visible text, so this check reads the DOM text rather than the rendered body.
  check('user management offers create / role / temporary password / deactivate',
        ['Create an account', 'Save role', 'Set temporary password', 'Deactivate account'].every(
          (needle) => userMgmtDom.includes(needle)),
        'all four controls present in the page');
  check('no password hash is rendered anywhere on the page',
        !/argon2id\$|\$argon2|password_hash/.test(userMgmtBody),
        'no hash or hash-column text in the page body');
  check('the audit panel is present', userMgmtBody.includes('Recent audit events'),
        'audit panel rendered; its event rows sit inside a collapsed expander');
  await page.screenshot({ path: path.join(OUT, 's15_03_user_management.png'), fullPage: true });
  step('user management');

  // -------------------------------------- step 3 — dataset validation (demo step 3)
  await nav(page, 'Dataset manager', 'Deployed model dataset vs active dataset');
  await page.waitForTimeout(2000);
  const datasetTop = await body(page);
  check('the deployed dataset and the active pointer are shown side by side',
        datasetTop.includes('In service — the deployed model') &&
        datasetTop.includes('Pointer — the active dataset version'),
        'both panels rendered');

  // 3a. a file that must be refused: the 25-column contract is broken
  const rejectBody = await stageUpload(page, INVALID_CSV, 'Rejection #');
  const rejectReason = (rejectBody.match(/The upload was rejected and recorded: ([^\n]+)/) || [])[1];
  const rejectId = (rejectBody.match(/Rejection #(\d+)/) || [])[1];
  const rejectCodes = (rejectBody.match(/stable error codes? ([a-z_, ]+)/) || [])[1];
  check('a CSV that breaks the column contract is refused, with a named reason',
        Boolean(rejectReason), rejectReason || 'no rejection message');
  check('the refusal names stable error codes and a rejection id',
        Boolean(rejectId) && Boolean(rejectCodes),
        `rejection #${rejectId || '?'} codes=${(rejectCodes || '?').trim()}`);
  check('nothing was repaired or partially loaded',
        /nothing was cleaned, coerced or partially loaded/.test(rejectBody),
        'the page states it explicitly');
  await page.screenshot({ path: path.join(OUT, 's15_04_dataset_rejected.png'), fullPage: true });

  // 3b. a valid file: staged, not activated, and it does not touch the live model
  const stageBody = await stageUpload(page, VALID_CSV, ['Staged as dataset version #', 'already version #']);
  await page.waitForTimeout(1500);
  const stagedId =
    (stageBody.match(/Staged as dataset version #(\d+)/) || [])[1] ||
    (stageBody.match(/already version #(\d+)/) || [])[1];
  const stagedDuplicate = /Those exact bytes are already version/.test(stageBody);
  // The per-upload fact table (records, columns, class shares, sha256) is an st.dataframe grid,
  // so those values are painted rather than readable as text; the sentence above it is not.
  const stageSentence = (stageBody.match(
    /(Staged as dataset version #\d+|Those exact bytes are already version #\d+)[^\n]*/
  ) || [''])[0];
  check('a valid CSV is validated and staged as a dataset version', Boolean(stagedId),
        `${stageSentence || 'version #' + (stagedId || '?')}` +
        `${stagedDuplicate ? ' [identical bytes: nothing new staged]' : ''}` +
        ' — the per-upload fact table below it is a painted grid');
  check('staging does not activate the version or retrain the model',
        /not\*\* active|not active/i.test(stageBody) || /deployed model has not changed/i.test(stageBody),
        'the page states the deployed model is unchanged');
  await page.screenshot({ path: path.join(OUT, 's15_05_dataset_staged.png'), fullPage: true });
  step('dataset validation');

  // --------------------------------------------- step 4 — administrator signs out
  await signOut(page);
  check('administrator signs out and the sign-in form returns',
        (await body(page)).includes('Sign in'));
  step('administrator signs out');

  // ------------------------------------------------ step 5 — user signs in (demo step 4)
  await signIn(page, repoEnv.INITIAL_USER_USERNAME, repoEnv.INITIAL_USER_PASSWORD);
  await waitText(page, 'Signed in as');
  const userNav = await navLabels(page);
  const userBody = await body(page);
  check('user signs in', userBody.includes('Signed in as'), repoEnv.INITIAL_USER_USERNAME);
  check('user navigation offers three sections only', userNav.length === 3, userNav.join(' | '));
  check('the user is not offered the administrator sections',
        !userNav.some((label) => /User management|Dataset manager|Model evaluation/.test(label)),
        userNav.join(' | '));
  step('user signs in');

  // ------------------------------- step 6 — the 23 preset values and the scored result
  await nav(page, 'Predict default risk', 'Load synthetic demonstrator example');
  const groups = await page.evaluate(() =>
    Array.from(document.querySelectorAll('details summary, [data-testid="stExpander"] summary'))
      .map((node) => (node.innerText || '').trim())
      .filter((text) => /inputs/.test(text))
  );
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
  const mismatches = Object.entries(DEMO_EXAMPLE).filter(
    ([name, expected]) => String(shown[name]) !== expected
  );
  check('the demonstrator loads all 23 values, and the 14 numeric ones read back as typed',
        mismatches.length === 0,
        mismatches.length === 0
          ? 'LIMIT_BAL=120000, AGE=34, BILL_AMT1..6=35000/33500/30000/28000/26500/25000, ' +
            'PAY_AMT1..6=2000/2500/3000/3000/3500/4000'
          : mismatches.map(([n, e]) => `${n}: expected ${e} got ${shown[n]}`).join('; '));
  const codeSelects = await page.evaluate(() => {
    const out = {};
    for (const node of document.querySelectorAll('input[role="combobox"]')) {
      out[node.getAttribute('aria-label')] = (node.value || '').replace(/\s+/g, ' ').trim();
    }
    return out;
  });
  const codeMismatches = Object.entries(CODE_EXPECT).filter(
    ([label, expected]) => codeSelects[label] !== expected
  );
  check('the nine coded inputs show their documented labels', codeMismatches.length === 0,
        codeMismatches.length === 0
          ? Object.values(CODE_EXPECT).join(' | ')
          : codeMismatches.map(([l, e]) => `${l}: expected "${e}" got "${codeSelects[l]}"`).join('; '));
  await page.screenshot({ path: path.join(OUT, 's15_06_prediction_form.png'), fullPage: true });

  await page.getByRole('button', { name: 'Predict default risk' }).first().click();
  await page.waitForTimeout(4000);
  const resultBody = await body(page);
  const probability = (resultBody.match(/([\d.]+%)\s*\*?\s*\(estimated/i) || [])[1];
  const band = ((resultBody.match(/Risk band: \**([^*\n]+)/i) || [])[1] || '').trim();
  const advice = ((resultBody.match(/What this suggests: \**([^\n]+)/i) || [])[1] || '').trim();
  const caption = (resultBody.match(/Decision threshold [\d.]+[^\n]*/) || [''])[0];
  const threshold = (resultBody.match(/Decision threshold ([\d.]+)/) || [])[1];
  const modelVersion = (caption.match(/model version (\S+)/) || [])[1];
  const classLabel = (resultBody.match(/(No default next month|Default next month)/) || [])[1] || '';
  check('the model returns a probability, a band and advice', Boolean(probability) && Boolean(band),
        `probability=${probability || '?'} band=${band || '?'}`);
  check('the result states the threshold and the model version',
        Boolean(threshold) && Boolean(modelVersion),
        `threshold=${threshold || '?'} model=${modelVersion || '?'}`);
  observations.push({
    item: 'scored result on the demonstrator row',
    measured: `probability ${probability}, band ${band}, threshold ${threshold}, model ${modelVersion}`,
    advice,
    classLabel,
    recorded: /already recorded at/.test(resultBody)
      ? 'identical request already recorded — not logged a second time'
      : 'recorded as a new prediction',
  });
  await page.screenshot({ path: path.join(OUT, 's15_07_prediction_result.png'), fullPage: true });
  step('preset 23 values and the scored result');

  // ------------------------------------ step 7 — the scored request reached the history
  await nav(page, 'My prediction history');
  await page.waitForTimeout(2000);
  const beforeCount = historyCount(await body(page));
  check('the scored request appears in the user\'s own history',
        beforeCount !== undefined && beforeCount >= 1,
        `${beforeCount === undefined ? 'no count' : beforeCount + ' row(s) for this account'}`);

  // ------------------------------- step 8 — invalid input is refused before the model
  await nav(page, 'Predict default risk', 'Load synthetic demonstrator example');
  const clearResult = page.getByRole('button', { name: 'Clear result' });
  if (await clearResult.count()) {
    await clearResult.first().click();
    await page.waitForTimeout(SETTLE);
  }
  const limitInput = page.locator(`input[aria-label="${LABELS.LIMIT_BAL}"]`).first();
  await limitInput.fill('');
  await limitInput.press('Tab');
  await page.waitForTimeout(1500);
  await page.getByRole('button', { name: 'Predict default risk' }).first().click();
  await page.waitForTimeout(3000);
  const invalidBody = await body(page);
  const invalidMessage =
    (invalidBody.match(/(feature '[A-Z_0-9]+'[^\n]*|missing feature\(s\)[^\n]*)/) || [])[1];
  check('an incomplete submission is refused with a named feature', Boolean(invalidMessage),
        invalidMessage || 'no validation message rendered');
  check('the refusal states that nothing was scored and nothing was recorded',
        /rejected before the model was called/.test(invalidBody),
        'caption rendered');
  await page.screenshot({ path: path.join(OUT, 's15_08_invalid_input.png'), fullPage: true });

  await nav(page, 'My prediction history');
  await page.waitForTimeout(2000);
  const afterCount = historyCount(await body(page));
  check('the refused submission added no history row',
        beforeCount !== undefined && afterCount === beforeCount,
        `before=${beforeCount} after=${afterCount}`);
  step('invalid input is refused');

  // ------------------------------ step 9 — the model evaluation page (admin only) is closed
  const userNavNow = await navLabels(page);
  check('the user cannot reach the evaluation page from their navigation',
        !userNavNow.some((label) => /Model evaluation/.test(label)), userNavNow.join(' | '));
  await signOut(page);
  check('user signs out and the sign-in form returns', (await body(page)).includes('Sign in'));
  step('user signs out');

  // ------------------- step 10 — model evaluation, driven as the administrator (demo step 7)
  await signIn(page, synth.username, synth.password);
  await waitText(page, 'Signed in as');
  await nav(page, 'Model evaluation', 'Model metadata');
  // The page paints in sections; wait for the last heading before reading the text, otherwise
  // the numbers below are read from a half-rendered page.
  await waitText(page, 'Limitations, in plain language', 180000);
  await page.waitForTimeout(4000);
  const evalBody = await body(page);
  const sections = [
    'Model comparison',
    'Confusion matrices',
    'Exploratory data analysis',
    'Feature importance',
    'Model metadata',
    'Limitations',
  ].filter((section) => evalBody.includes(section));
  check('the evaluation page renders all six sections', sections.length === 6,
        `${sections.length}/6`);
  // The comparison table and the confusion matrices are st.dataframe grids: their cells are
  // painted, not text in the DOM, so the numbers cannot be read out of the page. What can be
  // asserted is the prose the page writes from the same metrics — the Limitations section states
  // the deployed model's accuracy, recall and counts in words — plus the fact that the figures
  // and grids actually painted.
  const painted = await page.evaluate(() => ({
    images: Array.from(document.querySelectorAll('img')).filter((img) =>
      (img.src || '').includes('/media/')).length,
    canvases: document.querySelectorAll('canvas').length,
  }));
  const pageNumbers = {
    'accuracy 0.817167': /0\.817167/.test(evalBody),
    'recall 0.356': /0\.356/.test(evalBody),
    'missed 855': /missed 855/.test(evalBody),
    '1,327 actual defaults': /1,327/.test(evalBody),
    'constant-answer 77.88%': /77\.88%/.test(evalBody),
    'threshold 0.5': /threshold 0\.5/.test(evalBody),
  };
  check('the page states the deployed model\'s held-out numbers in words',
        Object.values(pageNumbers).every(Boolean),
        Object.entries(pageNumbers).map(([k, v]) => `${k}=${v}`).join(' '));
  check('the figures and the data grids paint', painted.images >= 6 && painted.canvases > 0,
        `${painted.images} figure image(s), ${painted.canvases} canvas grid(s)`);
  observations.push({
    item: 'model evaluation page',
    measured: `${sections.length}/6 sections, ${painted.images} figure images, ${painted.canvases} canvas grids`,
    note: 'the comparison table and confusion matrices are st.dataframe grids, so their cell ' +
      'values are painted rather than present as DOM text; the numbers quoted in the slides are ' +
      'checked against models/metrics.json by evidence/s15/check_script_numbers.py',
  });
  await page.screenshot({ path: path.join(OUT, 's15_09_model_evaluation.png'), fullPage: true });
  step('model evaluation');

  await signOut(page);
  check('administrator signs out and the sign-in form returns',
        (await body(page)).includes('Sign in'));
  step('administrator signs out (end)');

  await browser.close();

  const failed = checks.filter((c) => !c.ok);
  const total = timings.reduce((sum, row) => sum + row.seconds, 0);
  console.log('\n' + JSON.stringify({
    base: BASE,
    checks: checks.length,
    failed: failed.map((c) => c.name),
    observations,
    timings,
    measured_total_seconds: Number(total.toFixed(1)),
    verdict: failed.length === 0 ? 'PASS' : 'FAIL',
  }, null, 2));
  process.exit(failed.length === 0 ? 0 : 1);
})().catch(async (error) => {
  console.log('ERROR ' + (error.message || String(error)).split('\n')[0]);
  process.exit(1);
});
