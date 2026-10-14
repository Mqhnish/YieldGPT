// Run against a local demo server. Uses real sign-in/query APIs and controlled response fixtures.
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('playwright');
import assert from 'node:assert/strict';
const browser = await chromium.launch({headless:true, ...(process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH} : {})});
const context = await browser.newContext({viewport:{width:1440,height:1000}, reducedMotion:'reduce'});
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const pass = label => console.log('PASS ' + label);
async function signIn(persona='jdoe') {
  await page.locator('#account-button').click();
  await page.locator(`[data-persona="${persona}"]`).click();
  await page.locator('#demo-login-button').click();
  await page.locator('#login-dialog').waitFor({state:'hidden'});
}
async function ask(text) {
  await page.locator('#question').fill(text);
  await page.locator('#question-form').press('Enter');
  await page.locator('#answer-section').waitFor({state:'visible'});
}
try {
  await page.goto(process.env.APP_URL || 'http://127.0.0.1:8000');
  assert.equal(await page.title(), 'YieldGPT · Company A');
  assert.equal(/internal\s+brain/i.test(await page.locator('body').textContent()), false);
  await page.locator('#account-button').focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('#login-dialog').isVisible(), true);
  await page.keyboard.press('Escape');
  pass('YieldGPT naming and keyboard sign-in control');
  await signIn();
  assert.equal(await page.locator('#identity-name').textContent(), 'Jane Doe');
  assert.match(await page.locator('#source-mode-label').textContent(), /Simulated Company A data/);
  assert.equal(await page.locator('#console-link').isVisible(), false);
  pass('Real demo login, identity, source/generation metadata, privileged link hidden');
  await ask("What's the status of the database migration project and were there any blockers raised in Slack last week?");
  assert.ok(await page.locator('.source-card').count() > 0);
  assert.ok(await page.locator('.inline-citation').count() > 0);
  await page.locator('.inline-citation').first().click();
  await page.locator('.evidence-passage').first().waitFor();
  assert.match(await page.locator('.evidence-link').getAttribute('href'), /^https:/);
  assert.equal(await page.locator('.evidence-link').getAttribute('target'), '_blank');
  assert.equal(await page.locator('.evidence-followup').isVisible(), true);
  assert.equal(await page.locator('.evidence-copy').isVisible(), true);
  await page.locator('.evidence-followup').click();
  assert.equal(await page.locator('#evidence-dialog').isVisible(), false);
  assert.match(await page.locator('#question').inputValue(), /^Follow-up about/);
  assert.equal(await page.locator('#question').evaluate(element => element === document.activeElement), true);
  pass('Real retrieval, actionable evidence drawer, new-tab source and grounded follow-up');
  await signIn('kim');
  assert.equal(await page.locator('#answer-section').isVisible(), false);
  assert.equal(await page.locator('#answer-body').textContent(), '');
  assert.equal(await page.locator('#question').inputValue(), '');
  await ask('Show me the security incident report from the Q3 breach');
  assert.equal(await page.locator('.source-card').count(), 0);
  pass('Account switch clears answer and question; contractor query has no source metadata');
  const malicious = '<img src=x onerror="window.pwned=true">';
  await page.route('**/api/ask', route => route.fulfill({json:{query_id:'safe-test', answer:malicious+' [S1]', status:'answered', quality:{mode:'extractive'}, citations:[{ref:'S1',title:malicious,platform:'slack',container:'Test',url:'javascript:alert(1)',version:1}]}}));
  await ask('Test safe rendering');
  assert.ok((await page.locator('#answer-body').textContent()).includes(malicious));
  assert.equal(await page.locator('#answer-body img').count(), 0);
  assert.equal(await page.evaluate(() => window.pwned), undefined);
  await page.route('**/api/evidence/**', route => route.fulfill({json:{ref:'S1',title:malicious,platform:'slack',url:'javascript:alert(1)',version:1,passages:[{id:'p1',text:malicious}]}}));
  await page.locator('.inline-citation').first().click();
  await page.locator('.evidence-passage').waitFor();
  assert.equal(await page.locator('.evidence-link').count(), 0);
  assert.equal(await page.locator('#evidence-content img').count(), 0);
  await page.keyboard.press('Escape');
  pass('Model/source HTML is inert text and javascript source URLs are omitted');
  await page.unroute('**/api/ask'); await page.unroute('**/api/evidence/**');
  await signIn('jdoe');
  let delayedRoute;
  await page.route('**/api/ask', route => { delayedRoute = route; });
  await page.locator('#question').fill('Delayed query');
  await page.locator('#ask-button').click();
  await page.locator('#working-state').waitFor();
  await signIn('kim');
  try { await delayedRoute.fulfill({json:{query_id:'old',answer:'RESTRICTED ANSWER FROM PREVIOUS ACCOUNT',status:'answered',citations:[],quality:{mode:'extractive'}}}); } catch (_) {}
  await page.waitForTimeout(100);
  assert.equal(await page.locator('#identity-name').textContent(), 'Kim Lee');
  assert.equal(await page.locator('#answer-section').isVisible(), false);
  assert.equal(await page.locator('body').textContent().then(text => text.includes('RESTRICTED ANSWER FROM PREVIOUS ACCOUNT')), false);
  pass('Delayed previous-user answer cannot render after account switch');
  await page.unroute('**/api/ask');
  await signIn('jdoe');
  await page.route('**/api/ask', route => route.fulfill({status:503, json:{detail:'Source unavailable'}}));
  await page.locator('#question').fill('Force a safe error');
  await page.locator('#ask-button').click();
  await page.locator('#form-error').waitFor({state:'visible'});
  assert.match(await page.locator('#form-error').textContent(), /try again/i);
  assert.equal(await page.locator('#ask-button').isEnabled(), true);
  await page.unroute('**/api/ask');
  pass('Safe source failure is visible and retryable');
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.locator('#mobile-account').isVisible());
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await page.locator('#mobile-account').click();
  await page.locator('#dialog-logout').click();
  assert.equal(await page.locator('#mobile-account').textContent(), 'Sign in');
  assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
  pass('Mobile layout has no horizontal overflow; sign-out available; browser storage empty');
  for (const viewport of [{width:768,height:900},{width:1440,height:1000}]) {
    await page.setViewportSize(viewport);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  }
  pass('390, 768 and 1440 px layouts have no horizontal overflow');
  assert.deepEqual(errors, []);
  pass('No browser JavaScript errors');
} finally { await browser.close(); }

