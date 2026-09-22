// S8 TEMPLATE — rewrite against the final UI selectors and fixture helpers.
// Goal: deterministic clinician-manual capture using public/synthetic data only.
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const BASE_URL = process.env.MANUAL_BASE_URL ?? 'http://127.0.0.1:8000/app/';
const OUT = path.resolve('docs/manual/screenshots');

async function main() {
  await fs.mkdir(OUT, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(BASE_URL, { waitUntil: 'networkidle' });
  // TODO S8: load/reset deterministic demo workspace through supported UI/API.
  // TODO S8: replace placeholders with stable data-testid selectors.
  await page.screenshot({ path: path.join(OUT, '01-open-app.png'), fullPage: false });
  // Capture remaining steps only after the final UI is stable.
  await browser.close();
}

main().catch((err) => { console.error(err); process.exit(1); });
