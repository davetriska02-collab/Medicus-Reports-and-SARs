#!/usr/bin/env node
/**
 * SAR Redact UI screenshot harness.
 *
 * Usage:
 *   export NODE_PATH=$(npm root -g)   # playwright is installed globally
 *   node capture.js <baseUrl> <outDir> [username] [password]
 *
 * Idempotent: completes first-run setup if needed, logs in, seeds a demo SAR
 * if the dashboard is empty, then screenshots every screen at 1440x900.
 * Default credentials admin / Screenshot-Demo-2026! (created on first run).
 */
const { chromium } = require('playwright');
const fs = require('fs');

const [,, baseUrl, outDir, user = 'admin', pass = 'Screenshot-Demo-2026!'] = process.argv;
if (!baseUrl || !outDir) {
  console.error('usage: node capture.js <baseUrl> <outDir> [username] [password]');
  process.exit(1);
}

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const shot = (name) => page.screenshot({ path: `${outDir}/${name}.png` });
  const goto = (path) => page.goto(`${baseUrl}${path}`, { waitUntil: 'networkidle' });

  // ── First-run setup (no-op if already configured) ─────────────────────────
  await goto('/setup');
  if (page.url().includes('/setup')) {
    await shot('01-setup');
    await page.fill('input[name=username]', user);
    await page.fill('input[name=display_name]', 'Dr Triska');
    await page.fill('input[name=password]', pass);
    await page.fill('input[name=confirm_password]', pass);
    await page.click('button[type=submit]');
    await page.waitForLoadState('networkidle');
  }

  // ── Login ─────────────────────────────────────────────────────────────────
  await goto('/login');
  if (page.url().includes('/login')) {
    await shot('02-login');
    await page.fill('input[name=username]', user);
    await page.fill('input[name=password]', pass);
    await page.click('button[type=submit]');
    await page.waitForLoadState('networkidle');
  }

  // ── Seed a demo SAR if the dashboard is empty ─────────────────────────────
  await goto('/');
  if (!(await page.locator('.sar-table-row').count())) {
    try {
      await page.click('#demo-sar-btn', { timeout: 5000 });
      await page.waitForURL('**/review/**', { timeout: 180000 });
      await page.waitForLoadState('networkidle');
    } catch (e) {
      console.error('demo SAR seeding failed:', e.message.split('\n')[0]);
    }
  }

  // ── Screens ───────────────────────────────────────────────────────────────
  await goto('/');            await shot('03-dashboard');
  await goto('/new');         await shot('04-new-sar');
  await goto('/staff');       await shot('05-settings');
  await goto('/reports');     await shot('06-reports');
  await goto('/reports/new'); await shot('07-reports-new');
  await goto('/account');     await shot('08-account');
  await goto('/help');        await shot('09-help');
  await goto('/admin/users'); await shot('10-admin-users');
  await goto('/admin/audit'); await shot('11-admin-audit');
  await goto('/admin/ig-report'); await shot('12-ig-report');

  // Review screen (first SAR on the dashboard), give the PDF time to paint
  await goto('/');
  const review = page.locator('.sar-table-row a[href^="/review/"]').first();
  if (await review.count()) {
    await review.click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    await shot('13-review');
  }

  await browser.close();
  console.log('captured to', outDir);
})();
