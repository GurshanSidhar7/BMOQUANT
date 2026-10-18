// Optional browser QA: npm install --no-save playwright, then node tests/browser.mjs.
// Set PLAYWRIGHT_MODULE to a temporary installation to keep runtime dependencies at zero.
import assert from 'node:assert/strict';
import { mkdirSync } from 'node:fs';
import path from 'node:path';

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.WALKTHROUGH_URL || 'http://127.0.0.1:4173';
const output = process.env.WALKTHROUGH_SCREENSHOTS || '/tmp/research-data-walkthrough-qa';
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({
  ...(process.env.CHROME_EXECUTABLE ? { executablePath: process.env.CHROME_EXECUTABLE } : {}),
  headless: true,
});
const errors = [];
const checks = [];
try {
  const page = await browser.newPage({
    viewport: { width: 1512, height: 1050 },
    deviceScaleFactor: 1,
  });
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  assert.equal((await page.goto(base)).status(), 200);
  await page.waitForFunction(() => document.documentElement.dataset.ready === 'true');
  await page.addStyleTag({ content: 'html { scroll-behavior: auto !important; }' });
  assert.equal(await page.locator('#record-body tr').count(), 34);
  checks.push('Evidence loaded; all selected rows rendered');
  await page.screenshot({ path: path.join(output, 'desktop-overview.png'), fullPage: false });
  await page.locator('[data-record-filter="quarantined"]').click();
  assert.equal(await page.locator('#record-body tr').count(), 7);
  await page.locator('[data-inspect="12"]').click();
  assert.ok(await page.locator('#record-dialog').evaluate((dialog) => dialog.open));
  assert.match(
    await page.locator('#record-dialog-content').textContent(),
    /Duplicate observation key/,
  );
  await page.locator('.record-duplicate-link').click();
  assert.match(await page.locator('#record-dialog-title').textContent(), /65,202/);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#record-dialog').evaluate((dialog) => dialog.open), false);
  checks.push('Both duplicate members inspect correctly; native dialog supports Escape');
  await page.locator('[data-policy="reject"]').click();
  assert.match(await page.locator('#policy-result').textContent(), /0 new rows published/);
  await page.locator('[data-policy="quarantine"]').click();
  assert.match(await page.locator('#policy-result').textContent(), /65,194 rows published/);
  await page.locator('#warning-threshold').selectOption('3');
  assert.match(await page.locator('#threshold-count').textContent(), /65,194 retained/);
  checks.push('Quarantine/reject previews and warning retention remain explicit');
  await page.locator('#current-price').fill('90');
  assert.equal(await page.locator('#simple-result').textContent(), '-10.00%');
  await page.locator('#previous-price').fill('0');
  assert.equal(await page.locator('#simple-result').textContent(), '—');
  await page.locator('#previous-price').fill('100');
  await page.locator('#current-price').fill('110');
  await page.locator('#chart-symbol').selectOption('SYN0001');
  await page.locator('#chart-range').selectOption('2025');
  await page.locator('[data-metric="realized_vol_20"]').click();
  assert.match(await page.locator('#chart-caption').textContent(), /261 retained observations/);
  assert.ok(
    (await page.locator('#history-chart .chart-layer path').getAttribute('d')).length > 100,
  );
  await page.locator('#chart-wrap').focus();
  await page.keyboard.press('ArrowRight');
  assert.equal(await page.locator('#chart-tooltip').evaluate((element) => element.hidden), false);
  const chartDownload = page.waitForEvent('download');
  await page.locator('#download-chart').click();
  assert.match((await chartDownload).suggestedFilename(), /SYN0001-2025-synthetic.csv/);
  checks.push(
    'Return calculator, historical metric chart, keyboard inspection, and CSV export work',
  );
  await page.locator('[data-publication="2"]').click();
  await page.locator('#publication-failure').check();
  assert.match(
    await page.locator('#publication-state').textContent(),
    /Previous version stays active/,
  );
  await page.locator('#publication-failure').uncheck();
  checks.push('Publication-failure illustration preserves the prior active version');
  for (const query of ['daily_returns', 'rolling_volatility', 'security_summary']) {
    await page.locator(`[data-query="${query}"]`).click();
    assert.equal(await page.locator('#query-body tr').count(), 12);
    assert.ok((await page.locator('#sql-code').textContent()).includes('SELECT'));
  }
  checks.push('All three recorded SQL examples show SQL, explanation, and actual results');
  await page.locator('[data-benchmark-metric="rss"]').click();
  assert.match(await page.locator('#benchmark-reading').textContent(), /higher sampled peak/);
  await page.locator('[data-scale="100000"]').click();
  assert.match(
    await page.locator('#benchmark-download').getAttribute('href'),
    /measured-100000.json/,
  );
  await page.locator('[data-benchmark-metric="wall"]').click();
  await page.locator('[data-scale="1000000"]').click();
  checks.push(
    'Both benchmark scales and wall/RSS comparisons use their corresponding measured reports',
  );
  await page.locator('#validate').evaluate(element => element.scrollIntoView({ block: 'start' }));
  await page.waitForFunction(() => document.querySelector('#step-nav a.active')?.dataset.stage === 'validate');
  checks.push('Reading navigation tracks the section at the top of the viewport');
  await page.screenshot({ path: path.join(output, 'desktop-validation.png'), fullPage: false });
  await page.locator('#analytics').evaluate(element => element.scrollIntoView({ block: 'start' }));
  await page.screenshot({ path: path.join(output, 'desktop-analytics.png'), fullPage: false });
  await page.locator('#performance').evaluate(element => element.scrollIntoView({ block: 'start' }));
  await page.screenshot({ path: path.join(output, 'desktop-benchmarks.png'), fullPage: false });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({ path: path.join(output, 'mobile-overview.png'), fullPage: false });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  for (const id of [
    'normalize',
    'validate',
    'analytics',
    'storage',
    'query',
    'performance',
    'evidence',
  ]) {
    await page.locator(`#${id}`).scrollIntoViewIfNeeded();
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
      false,
      `${id} overflows mobile width`,
    );
  }
  await page.locator('#analytics').scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(output, 'mobile-analytics.png'), fullPage: false });
  checks.push('390 px mobile viewport has no page-level horizontal overflow across every section');
  await page.emulateMedia({ media: 'print' });
  await page.pdf({
    path: path.join(output, 'walkthrough.pdf'),
    format: 'A4',
    printBackground: true,
  });
  checks.push('Print/PDF rendering completed');
  assert.deepEqual(errors, [], 'Browser emitted errors');
  console.log(JSON.stringify({ checks, browserErrors: errors, screenshots: output }, null, 2));
} finally {
  await browser.close();
}
