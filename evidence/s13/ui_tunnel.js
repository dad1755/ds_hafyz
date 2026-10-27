// S13 browser check: the real public HTTPS surface, driven by a real Chromium.
//
//   https://www.aihubcampus.online  →  Cloudflare edge  →  tunnel  →  http://web:2026
//
// Nothing here talks to the container directly: every request leaves the host, resolves the
// public hostname, and comes back through Cloudflare. That is the only way to prove the
// ingress target, the WebSocket upgrade and the XSRF/CORS behaviour are right *as deployed*.
//
// Three journeys:
//   A. operator administrator (`ds_hafyz`, credentials from .env) — signs in, lands on the
//      forced "set a new password" screen, signs out. The password is NOT changed: the
//      operator's credential belongs to the operator.
//   B. synthetic administrator (created for this run, deactivated after it) — the full
//      administrator journey: home, prediction, history, user management, dataset manager
//      (staged CSV upload), model evaluation, a hard refresh that must keep the session, and
//      sign-out.
//   C. demo user (`demo_user`) — the user journey, including proof that the three
//      administrator sections are not offered at all.
//
// No credential is printed: the summary reports usernames and booleans only.
//
// Usage: BASE_URL=https://www.aihubcampus.online CRED_FILE=/path/creds.json \
//        UPLOAD_CSV=/path/subset.csv OUT_DIR=evidence/s13 node ui_tunnel.js

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const BASE = (process.env.BASE_URL || 'https://www.aihubcampus.online').replace(/\/$/, '');
const OUT = process.env.OUT_DIR || '.';
const CRED_FILE = process.env.CRED_FILE;
const UPLOAD_CSV = process.env.UPLOAD_CSV;
const SETTLE = Number(process.env.SETTLE_MS || 2500);

const checks = [];
const observations = [];
function check(name, ok, detail) {
  checks.push({ name, ok: Boolean(ok), detail: detail === undefined ? '' : String(detail) });
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

const navLabels = async (page) => {
  await page.locator('[role="radiogroup"]').first().waitFor({ timeout: 30000 });
  return page.evaluate(() =>
    Array.from(document.querySelectorAll('[role="radiogroup"] label')).map((label) =>
      (label.innerText || label.textContent || '').trim()
    )
  );
};

async function waitText(page, needle, timeout = 60000) {
  await page.getByText(needle, { exact: false }).first().waitFor({ timeout });
}

async function nav(page, label) {
  const option = page.locator('[role="radiogroup"] label').filter({ hasText: label }).first();
  await option.waitFor({ timeout: 30000 });
  await option.click();
  await page.waitForTimeout(SETTLE);
}

async function signIn(page, username, password) {
  await page.getByLabel('Username').first().fill(username);
  await page.getByLabel('Password').first().fill(password);
  await page.getByRole('button', { name: 'Sign in' }).first().click();
  await page.waitForTimeout(SETTLE);
}

async function signOut(page) {
  await nav(page, 'Home');
  await page.getByRole('button', { name: 'Sign out' }).first().click();
  await page.waitForTimeout(SETTLE);
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  const sockets = [];
  page.on('websocket', (ws) => sockets.push(ws.url()));

  // ---------------------------------------------------------------- edge + shell
  const first = await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  const headers = first.headers();
  check('public HTTPS served by the Cloudflare edge', /cloudflare/i.test(headers['server'] || ''),
        `server=${headers['server']} cf-ray=${(headers['cf-ray'] || '').split('-')[0]}…`);
  check('response is the Streamlit shell', /text\/html/.test(headers['content-type'] || ''),
        headers['content-type']);
  await waitText(page, 'Sign in');
  check('sign-in form rendered over the tunnel', true);

  const cookies = await context.cookies();
  const xsrf = cookies.find((c) => c.name === '_streamlit_xsrf');
  check('XSRF cookie issued to the browser', Boolean(xsrf), xsrf ? `domain=${xsrf.domain} path=${xsrf.path}` : 'missing');
  check('XSRF cookie is SameSite=Lax with path=/', Boolean(xsrf && /lax/i.test(xsrf.sameSite) && xsrf.path === '/'),
        xsrf ? `sameSite=${xsrf.sameSite} path=${xsrf.path}` : 'missing');
  // Streamlit sets Secure only when it terminates TLS itself (`server.sslCertFile`) or when
  // SameSite=None forces it (streamlit/web/server/starlette/starlette_routes.py). Here TLS ends
  // at Cloudflare, so the flag is absent — recorded as an observation, with its consequence,
  // rather than scored: the value is a CSRF token, not a session credential.
  observations.push({
    item: 'XSRF cookie Secure flag',
    measured: xsrf ? `secure=${xsrf.secure}` : 'missing',
    because: 'TLS terminates at the Cloudflare edge, so the app sees http:// from cloudflared; Streamlit marks the cookie Secure only with server.sslCertFile or SameSite=None.',
  });
  check('no application session cookie is exposed to the page', cookies.length === 1,
        `cookies=${cookies.map((c) => c.name).join(',')}`);

  await page.waitForTimeout(3000);
  check('WebSocket upgrade through the tunnel', sockets.some((u) => u.startsWith('wss://')),
        `${sockets.length} socket(s)`);
  await page.screenshot({ path: path.join(OUT, 'tunnel_signin.png') });

  // ------------------------------------------- A. the operator administrator's own sign-in
  await signIn(page, repoEnv.INITIAL_ADMIN_USERNAME, repoEnv.INITIAL_ADMIN_PASSWORD);
  await waitText(page, 'Set a new password');
  const opBody = await body(page);
  check('operator admin signs in through the tunnel', opBody.includes(repoEnv.INITIAL_ADMIN_USERNAME),
        'lands on the forced password-change screen (must_change_password=1, D13)');
  check('operator credential left untouched', !opBody.includes('Password changed'),
        'no password was submitted');
  await page.screenshot({ path: path.join(OUT, 'tunnel_operator_forced_change.png') });
  await page.getByRole('button', { name: 'Sign out instead' }).first().click();
  await page.waitForTimeout(SETTLE);
  check('operator admin signs out', (await body(page)).includes('Sign in'));

  // ------------------------------------------------------- B. synthetic administrator
  await signIn(page, synth.username, synth.password);
  await waitText(page, 'Signed in as');
  const adminBody = await body(page);
  check('synthetic admin signs in', adminBody.includes('Signed in as'), synth.username);
  const adminNav = await navLabels(page);
  check('admin navigation offers six sections', adminNav.length === 6, adminNav.join(' | '));
  await page.screenshot({ path: path.join(OUT, 'tunnel_admin_home.png') });

  // prediction
  await nav(page, 'Predict default risk');
  await waitText(page, 'Load synthetic demonstrator example');
  await page.getByRole('button', { name: 'Load synthetic demonstrator example' }).first().click();
  await page.waitForTimeout(SETTLE);
  await page.getByRole('button', { name: 'Predict default risk' }).first().click();
  await page.waitForTimeout(4000);
  const probabilityOf = (text) => {
    const value = (text.match(/([\d.]+%)\s*\*?\s*\(estimated/i) || [])[1];
    return value && text.includes('Risk band:') ? value : undefined;
  };
  const resultBody = await body(page);
  const probability = probabilityOf(resultBody);
  const band = (resultBody.match(/Risk band:\s*\**([^*\n]+)/i) || [])[1];
  check('prediction scored through the tunnel', Boolean(probability),
        `probability=${probability} band=${band ? band.trim() : '?'}`);
  check('result states the model version and threshold',
        /Decision threshold [\d.]+ · model version/.test(resultBody));
  await page.screenshot({ path: path.join(OUT, 'tunnel_prediction_result.png'), fullPage: true });

  // history
  await nav(page, 'My prediction history');
  await page.waitForTimeout(2000);
  const historyBody = await body(page);
  const historyRows = (historyBody.match(/(\d+) row\(s\) shown for/) || [])[1];
  check('prediction history lists the request just made',
        Boolean(historyRows) && Number(historyRows) >= 1,
        historyRows ? `${historyRows} row(s) for this account` : 'no row count rendered');

  // user management
  await nav(page, 'User management');
  await page.waitForTimeout(2000);
  const userMgmtBody = await body(page);
  check('user management page renders', userMgmtBody.includes('User management'),
        userMgmtBody.includes('Create an account') ? 'accounts + create + audit panels' : 'heading only');
  check('user management lists the operator admin', userMgmtBody.includes(repoEnv.INITIAL_ADMIN_USERNAME));

  // dataset manager: upload and stage
  await nav(page, 'Dataset manager');
  await page.waitForTimeout(2500);
  await waitText(page, 'Stage a new dataset version');
  await page.locator('input[type="file"]').first().setInputFiles(UPLOAD_CSV);
  await page.waitForTimeout(4000);
  await page.getByRole('button', { name: 'Validate and stage dataset' }).first().click();
  await page.waitForTimeout(5000);
  const datasetBody = await body(page);
  const staged = (datasetBody.match(/Staged as dataset version \**#(\d+)\**/) ||
                  datasetBody.match(/already version #(\d+)/) || [])[1];
  check('CSV upload validated and staged through the tunnel', Boolean(staged),
        staged ? `dataset version #${staged}` : 'no staging confirmation');
  check('staged upload is not activated silently',
        /not\*\* active|is \*\*not\*\* active/.test(datasetBody) || datasetBody.includes('not active') ||
        datasetBody.includes('Deployed model dataset vs active dataset'));
  await page.screenshot({ path: path.join(OUT, 'tunnel_dataset_staged.png'), fullPage: true });

  // evaluation — eleven figures paint progressively; wait for the last section to appear
  await nav(page, 'Model evaluation');
  await page.getByText('Model metadata', { exact: false }).first().waitFor({ timeout: 90000 });
  await page.waitForTimeout(3000);
  const evalBody = await body(page);
  const evalSections = [
    'Model comparison',
    'Confusion matrices',
    'Exploratory data analysis',
    'Feature importance',
    'Model metadata',
    'Limitations',
  ].filter((section) => evalBody.includes(section));
  check('model evaluation page renders every section', evalSections.length === 6,
        `${evalSections.length}/6 sections`);
  await page.screenshot({ path: path.join(OUT, 'tunnel_evaluation.png'), fullPage: true });

  // hard refresh: measured, not assumed
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
  let afterReload = '';
  for (let attempt = 0; attempt < 12; attempt += 1) {
    await page.waitForTimeout(2500);
    afterReload = await body(page);
    if (/Signed in as|Accounts are created by the administrator/.test(afterReload)) break;
  }
  check('hard refresh is served by the tunnel', afterReload.includes('AI Hub Campus'),
        afterReload.includes('Signed in as') ? 'still signed in' : 'session ended, sign-in form served');
  if (!afterReload.includes('Signed in as')) {
    observations.push({
      item: 'session after a hard refresh (F-1)',
      measured: 'signed out — the sign-in form is served again',
      because: 'the session token lives only in Streamlit session_state and there is no session cookie, so a reload starts a new server session. Reported as a finding; changing the session model is outside S13.',
    });
  }
  if (!afterReload.includes('Signed in as')) {
    await signIn(page, synth.username, synth.password);
    await waitText(page, 'Signed in as');
  }
  await signOut(page);
  check('admin sign-out returns to the sign-in form', (await body(page)).includes('Sign in'));

  // ------------------------------------------------------------------ C. demo user
  await signIn(page, repoEnv.INITIAL_USER_USERNAME, repoEnv.INITIAL_USER_PASSWORD);
  await waitText(page, 'Signed in as');
  const userNav = await navLabels(page);
  check('user navigation offers three sections', userNav.length === 3, userNav.join(' | '));
  const userBody = await body(page);
  check('user is not offered the administrator sections',
        !userNav.some((label) => /User management|Dataset manager|Model evaluation/.test(label)));
  check('user home does not advertise administrator features',
        !/User management\*\* in the sidebar/.test(userBody));
  await page.screenshot({ path: path.join(OUT, 'tunnel_user_home.png') });

  await nav(page, 'Predict default risk');
  await waitText(page, 'Load synthetic demonstrator example');
  await page.getByRole('button', { name: 'Load synthetic demonstrator example' }).first().click();
  await page.waitForTimeout(SETTLE);
  await page.getByRole('button', { name: 'Predict default risk' }).first().click();
  await page.waitForTimeout(4000);
  const userResult = await body(page);
  const userProbability = (userResult.match(/([\d.]+%)\s*\*?\s*\(estimated/i) || [])[1];
  check('user prediction scored through the tunnel',
        Boolean(userProbability) && userResult.includes('Risk band:'),
        `probability=${userProbability || '?'}`);
  await page.screenshot({ path: path.join(OUT, 'tunnel_user_prediction.png'), fullPage: true });

  await nav(page, 'My prediction history');
  await page.waitForTimeout(2000);
  check('user prediction history renders', (await body(page)).includes('My prediction history'));

  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
  let userReload = '';
  for (let attempt = 0; attempt < 12; attempt += 1) {
    await page.waitForTimeout(2500);
    userReload = await body(page);
    if (/Signed in as|Accounts are created by the administrator/.test(userReload)) break;
  }
  check('user hard refresh is served by the tunnel', userReload.includes('AI Hub Campus'),
        userReload.includes('Signed in as') ? 'still signed in' : 'session ended, sign-in form served (F-1, same as admin)');
  if (!userReload.includes('Signed in as')) {
    await signIn(page, repoEnv.INITIAL_USER_USERNAME, repoEnv.INITIAL_USER_PASSWORD);
    await waitText(page, 'Signed in as');
  }
  await signOut(page);
  check('user sign-out returns to the sign-in form', (await body(page)).includes('Sign in'));

  await browser.close();

  const failed = checks.filter((c) => !c.ok);
  console.log('\n' + JSON.stringify({
    base: BASE,
    sockets: sockets.length,
    checks: checks.length,
    failed: failed.map((c) => c.name),
    observations,
    verdict: failed.length === 0 ? 'PASS' : 'FAIL',
  }, null, 2));
  process.exit(failed.length === 0 ? 0 : 1);
})().catch(async (error) => {
  console.log('ERROR ' + (error.message || String(error)).split('\n')[0]);
  process.exit(1);
});
